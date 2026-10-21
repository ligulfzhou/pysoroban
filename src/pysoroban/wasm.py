from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from . import ir
from .model import BytesNType, ContractType, EnumType, StructType, ValueType, is_object_type
from .xdr import contract_spec, environment_metadata


I32_TAG = 5
U32_TAG = 4
U128_SMALL_TAG = 10
I128_SMALL_TAG = 11
U256_SMALL_TAG = 12
U64_SMALL_TAG = 6
I64_SMALL_TAG = 7
VOID_TAG = 2
ERROR_TAG = 3
INSTANCE_STORAGE = 2
PERSISTENT_STORAGE = 1
TEMPORARY_STORAGE = 0

# Names and indices are the protocol-25 env.json interface. Every imported
# argument and result is directly marshalled through the Wasm i64 ABI.
HOST_IMPORTS = (
    ("l", "_", 3),  # put_contract_data
    ("l", "0", 2),  # has_contract_data
    ("l", "1", 2),  # get_contract_data
    ("a", "0", 1),  # require_auth
    ("i", "_", 1),  # obj_from_u64
    ("i", "0", 1),  # obj_to_u64
    ("i", "1", 1),  # obj_from_i64
    ("i", "2", 1),  # obj_to_i64
    ("b", "3", 2),  # bytes_new_from_linear_memory
    ("b", "i", 2),  # string_new_from_linear_memory
    ("b", "j", 2),  # symbol_new_from_linear_memory
    ("v", "g", 2),  # vec_new_from_linear_memory
    ("x", "0", 2),  # obj_cmp
    ("x", "1", 2),  # contract_event
)
CONTRACT_CALL_IMPORT = ("d", "_", 3)
PUT_CONTRACT_DATA = 0
HAS_CONTRACT_DATA = 1
GET_CONTRACT_DATA = 2
REQUIRE_AUTH = 3
OBJ_FROM_U64 = 4
OBJ_TO_U64 = 5
OBJ_FROM_I64 = 6
OBJ_TO_I64 = 7
BYTES_FROM_MEMORY = 8
STRING_FROM_MEMORY = 9
SYMBOL_FROM_MEMORY = 10
VEC_FROM_MEMORY = 11
OBJ_CMP = 12
CONTRACT_EVENT = 13
CONTRACT_CALL = 14

I64_TYPES = {ValueType.I64, ValueType.U64}
WIDE_INTEGER_TYPES = {ValueType.I128, ValueType.U128}


class LiteralPool:
    """Deterministic static UTF-8/byte storage after an event scratch slot."""

    def __init__(self, scratch_size: int = 8):
        self.data = bytearray(b"\x00" * scratch_size)
        self.offsets: Dict[bytes, int] = {}

    def intern(self, value: bytes) -> int:
        if value not in self.offsets:
            self.offsets[value] = len(self.data)
            self.data += value
        return self.offsets[value]


def uleb(value: int) -> bytes:
    if value < 0:
        raise ValueError("unsigned LEB128 cannot encode a negative value")
    output = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            byte |= 0x80
        output.append(byte)
        if not value:
            return bytes(output)


def sleb(value: int, bits: int = 64) -> bytes:
    output = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        sign_set = bool(byte & 0x40)
        more = not ((value == 0 and not sign_set) or (value == -1 and sign_set))
        if more:
            byte |= 0x80
        output.append(byte)
    return bytes(output)


def vector(items: Sequence[bytes]) -> bytes:
    return uleb(len(items)) + b"".join(items)


def name(value: str) -> bytes:
    raw = value.encode("utf-8")
    return uleb(len(raw)) + raw


def section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + uleb(len(payload)) + payload


def custom_section(section_name: str, payload: bytes) -> bytes:
    return section(0, name(section_name) + payload)


@dataclass
class Locals:
    param_raw: Dict[str, int]
    native: Dict[str, int]
    types: Dict[str, ValueType]
    local_types: List[int]
    scratch: int
    wide_scratch: Tuple[Tuple[int, ...], ...]


class FunctionEmitter:
    """Emit Wasm from typed IR; this backend has no dependency on Python AST."""

    def __init__(self, function: ir.Function, literals: LiteralPool, host_indices=None):
        self.function = function
        self.literals = literals
        self.host_indices = host_indices or {}
        self.wide_scratch_depth = 0
        self.locals = self._allocate_locals()

    def _allocate_locals(self) -> Locals:
        param_raw = {param.name: index for index, param in enumerate(self.function.params)}
        values = list(self.function.params) + list(self.function.locals)
        names = [value.name for value in values]
        native = {}
        types = {value.name: value.type for value in values}
        first_local = len(self.function.params)
        for offset, item in enumerate(names):
            native[item] = first_local + offset
        local_types = [0x7E if types[item] in I64_TYPES or is_object_type(types[item]) else 0x7F for item in names]
        scratch = len(self.function.params) + len(local_types)
        local_types.append(0x7E)
        frame_count = max(1, _wide_expression_depth(self.function))
        wide_scratch = tuple(
            tuple(scratch + 1 + frame * 9 + offset for offset in range(9))
            for frame in range(frame_count)
        )
        local_types.extend([0x7E] * (frame_count * 9))
        return Locals(param_raw, native, types, local_types, scratch, wide_scratch)

    def _claim_wide_scratch(self) -> Tuple[int, ...]:
        frame = self.locals.wide_scratch[self.wide_scratch_depth]
        self.wide_scratch_depth += 1
        return frame

    def _release_wide_scratch(self) -> None:
        self.wide_scratch_depth -= 1

    def emit(self) -> bytes:
        code = bytearray()
        for param in self.function.params:
            code += self._decode_param(param.name, param.type)
            code += b"\x21" + uleb(self.locals.native[param.name])  # local.set
        for statement in self.function.body:
            code += self.statement(statement)
        if self.function.result is ValueType.VOID:
            code += b"\x42" + sleb(VOID_TAG)  # i64.const void Val
        code += b"\x0b"

        local_decls = [uleb(1) + bytes([value_type]) for value_type in self.locals.local_types]
        body = vector(local_decls) + code
        return uleb(len(body)) + body

    def _decode_param(self, variable: str, value_type: ContractType) -> bytes:
        raw_index = self.locals.param_raw[variable]
        raw = b"\x20" + uleb(raw_index)
        if value_type is ValueType.I32:
            # Soroban I32Val: [i32 bits:32][minor:24][tag:8].
            return raw + b"\x42\x20\x87\xa7"
        if value_type is ValueType.U32 or isinstance(value_type, EnumType):
            return raw + b"\x42\x20\x88\xa7"
        if value_type is ValueType.BOOL:
            # False and true are represented by Val tags 0 and 1.
            return raw + b"\x42\x01\x51"
        if value_type in {ValueType.I64, ValueType.U64}:
            return raw + self._decode_i64_val(value_type)
        if is_object_type(value_type):
            return raw
        raise AssertionError(value_type)

    def _decode_i64_val(self, value_type: ValueType) -> bytes:
        tag = I64_SMALL_TAG if value_type is ValueType.I64 else U64_SMALL_TAG
        shift = b"\x87" if value_type is ValueType.I64 else b"\x88"
        object_call = OBJ_TO_I64 if value_type is ValueType.I64 else OBJ_TO_U64
        scratch = uleb(self.locals.scratch)
        return b"".join([
            b"\x22", scratch,  # local.tee scratch
            b"\x42", sleb(0xFF), b"\x83",  # mask tag byte
            b"\x42", sleb(tag), b"\x51",  # i64.eq
            b"\x04\x7e",  # if (result i64)
            b"\x20", scratch, b"\x42\x08", shift,
            b"\x05",
            b"\x20", scratch, b"\x10", uleb(object_call),
            b"\x0b",
        ])

    def statement(self, node: ir.Statement) -> bytes:
        if isinstance(node, ir.Return):
            return self.expression(node.value) + self.encode_val(node.value.type) + b"\x0f"
        if isinstance(node, ir.SetLocal):
            return self.expression(node.value) + b"\x21" + uleb(self.locals.native[node.name])
        if isinstance(node, ir.If):
            output = bytearray(self.expression(node.test))
            output += b"\x04\x40"  # if, empty block type
            for child in node.body:
                output += self.statement(child)
            if node.otherwise:
                output += b"\x05"
                for child in node.otherwise:
                    output += self.statement(child)
            output += b"\x0b"
            return bytes(output)
        if isinstance(node, ir.ForRange):
            variable = uleb(self.locals.native[node.variable])
            stop_local = uleb(self.locals.native[node.stop_local])
            output = bytearray()
            output += self.expression(node.start) + b"\x21" + variable
            output += self.expression(node.stop) + b"\x21" + stop_local
            output += b"\x02\x40\x03\x40"  # block; loop
            output += b"\x20" + variable + b"\x20" + stop_local + b"\x4e"  # i32.ge_s
            output += b"\x0d\x01"  # br_if out of block
            for child in node.body:
                output += self.statement(child)
            output += b"\x20" + variable + b"\x41\x01\x6a\x21" + variable
            output += b"\x0c\x00\x0b\x0b"  # br loop; end; end
            return bytes(output)
        if isinstance(node, ir.Drop):
            if isinstance(node.value, ir.Constant) and node.value.type is ValueType.VOID:
                return b""
            return self.expression(node.value) + b"\x1a"  # drop Void Val
        if isinstance(node, ir.PopBack):
            collection = uleb(self.locals.native[node.collection])
            target = uleb(self.locals.native[node.target])
            element_type = self.locals.types[node.target]
            return b"".join([
                b"\x20", collection,
                b"\x10", uleb(self.host_indices[("v", "9")]),
                self._decode_call_result(element_type),
                b"\x21", target,
                b"\x20", collection,
                b"\x10", uleb(self.host_indices[("v", "7")]),
                b"\x21", collection,
            ])
        if isinstance(node, ir.Fail):
            # Error Val: major = contract code, minor = ScErrorType::Contract (0), tag = 3.
            # fail_with_error traps; unreachable keeps the Wasm type checker satisfied.
            error_val = (node.code << 32) | ERROR_TAG
            if error_val >= 2**63:
                error_val -= 2**64
            return (
                b"\x42" + sleb(error_val)
                + b"\x10" + uleb(self.host_indices[("x", "5")])
                + b"\x1a\x00"
            )
        raise AssertionError(type(node).__name__)

    def expression(self, node: ir.Expression) -> bytes:
        if isinstance(node, ir.Constant):
            if node.type is ValueType.VOID:
                return b""
            if isinstance(node.value, bool):
                return b"\x41" + sleb(1 if node.value else 0, 32)
            if node.type in {ValueType.SYMBOL, ValueType.STRING, ValueType.BYTES}:
                raw = node.value if isinstance(node.value, bytes) else node.value.encode("utf-8")
                offset = self.literals.intern(raw)
                constructor = {
                    ValueType.BYTES: BYTES_FROM_MEMORY,
                    ValueType.STRING: STRING_FROM_MEMORY,
                    ValueType.SYMBOL: SYMBOL_FROM_MEMORY,
                }[node.type]
                return self._u32_val(offset) + self._u32_val(len(raw)) + b"\x10" + uleb(constructor)
            if node.type is ValueType.U256:
                parts = bytearray()
                for shift in (192, 128, 64, 0):
                    part = (node.value >> shift) & (2**64 - 1)
                    if part >= 2**63:
                        part -= 2**64
                    parts += b"\x42" + sleb(part)
                return bytes(parts) + b"\x10" + uleb(self.host_indices[("i", "9")])
            if node.type in WIDE_INTEGER_TYPES:
                bits = node.value % (2**128)
                hi = bits >> 64
                lo = bits & (2**64 - 1)
                signed_hi = hi if hi < 2**63 else hi - 2**64
                signed_lo = lo if lo < 2**63 else lo - 2**64
                constructor = ("i", "6") if node.type is ValueType.I128 else ("i", "3")
                return b"".join([
                    b"\x42", sleb(signed_hi),
                    b"\x42", sleb(signed_lo),
                    b"\x10", uleb(self.host_indices[constructor]),
                ])
            if node.type in {ValueType.I64, ValueType.U64}:
                value = node.value if node.value < 2**63 else node.value - 2**64
                return b"\x42" + sleb(value)
            value = node.value if node.value < 2**31 else node.value - 2**32
            return b"\x41" + sleb(value, 32)
        if isinstance(node, ir.Local):
            return b"\x20" + uleb(self.locals.native[node.name])
        if isinstance(node, ir.Unary):
            if node.op == "neg":
                zero = b"\x42\x00" if node.type is ValueType.I64 else b"\x41\x00"
                subtract = b"\x7d" if node.type is ValueType.I64 else b"\x6b"
                return zero + self.expression(node.operand) + subtract
            if node.op == "not":
                return self.expression(node.operand) + b"\x45"
        if isinstance(node, ir.Binary):
            if node.type is ValueType.U256:
                export = {"add": "n", "sub": "o", "mul": "p", "div": "q"}[node.op]
                return (
                    self.expression(node.left)
                    + self.expression(node.right)
                    + b"\x10" + uleb(self.host_indices[("i", export)])
                )
            if node.type in WIDE_INTEGER_TYPES:
                return self._wide_binary(node)
            i32_opcodes = {
                "add": 0x6A,
                "sub": 0x6B,
                "mul": 0x6C,
                "and": 0x71,
                "or": 0x72,
            }
            i64_opcodes = {"add": 0x7C, "sub": 0x7D, "mul": 0x7E}
            if node.type is ValueType.U32:
                i32_opcodes["div"] = 0x6E  # i32.div_u
            if node.type is ValueType.U64:
                i64_opcodes["div"] = 0x80  # i64.div_u
            opcodes = i64_opcodes if node.type in {ValueType.I64, ValueType.U64} else i32_opcodes
            return self.expression(node.left) + self.expression(node.right) + bytes([opcodes[node.op]])
        if isinstance(node, ir.Compare):
            operand_type = node.left.type
            if operand_type in WIDE_INTEGER_TYPES:
                return self._wide_compare(node)
            if is_object_type(operand_type):
                compared = self.expression(node.left) + self.expression(node.right) + b"\x10" + uleb(OBJ_CMP)
                if node.op == "eq":
                    return compared + b"\x50"  # i64.eqz
                if node.op == "ne":
                    return compared + b"\x50\x45"  # !(i64.eqz)
                order_opcodes = {"lt": 0x53, "gt": 0x55, "le": 0x57, "ge": 0x59}
                return compared + b"\x42\x00" + bytes([order_opcodes[node.op]])
            i32_opcodes = {
                "eq": 0x46,
                "ne": 0x47,
                "lt": 0x48,
                "gt": 0x4A,
                "le": 0x4C,
                "ge": 0x4E,
            }
            if operand_type is ValueType.U32 or isinstance(operand_type, EnumType):
                i32_opcodes.update({"lt": 0x49, "gt": 0x4B, "le": 0x4D, "ge": 0x4F})
            i64_opcodes = {"eq": 0x51, "ne": 0x52, "lt": 0x53, "gt": 0x55, "le": 0x57, "ge": 0x59}
            if operand_type is ValueType.U64:
                i64_opcodes.update({"lt": 0x54, "gt": 0x56, "le": 0x58, "ge": 0x5A})
            opcodes = i64_opcodes if operand_type in {ValueType.I64, ValueType.U64} else i32_opcodes
            return self.expression(node.left) + self.expression(node.right) + bytes([opcodes[node.op]])
        if isinstance(node, ir.HostCall):
            return self.call(node)
        raise AssertionError(type(node).__name__)

    def _normalized_wide_values(
        self, left: ir.Expression, right: ir.Expression, scratch: Tuple[int, ...]
    ):
        lhs_val, rhs_val, lhs_hi, lhs_lo, rhs_hi, rhs_lo, *_ = scratch
        output = bytearray()
        output += self.expression(left) + b"\x21" + uleb(lhs_val)
        output += self.expression(right) + b"\x21" + uleb(rhs_val)
        for value_local, hi_local, lo_local in (
            (lhs_val, lhs_hi, lhs_lo),
            (rhs_val, rhs_hi, rhs_lo),
        ):
            output += self._wide_part(value_local, left.type, high=True) + b"\x21" + uleb(hi_local)
            output += self._wide_part(value_local, left.type, high=False) + b"\x21" + uleb(lo_local)
        constructor = "6" if left.type is ValueType.I128 else "3"
        for value_local, hi_local, lo_local in (
            (lhs_val, lhs_hi, lhs_lo),
            (rhs_val, rhs_hi, rhs_lo),
        ):
            output += b"\x20" + uleb(hi_local) + b"\x20" + uleb(lo_local)
            output += b"\x10" + uleb(self.host_indices[("i", constructor)])
            output += b"\x21" + uleb(value_local)
        return output

    def _wide_compare(self, node: ir.Compare) -> bytes:
        scratch = self._claim_wide_scratch()
        try:
            lhs_val, rhs_val, *_ = scratch
            output = self._normalized_wide_values(node.left, node.right, scratch)
            output += b"\x20" + uleb(lhs_val) + b"\x20" + uleb(rhs_val)
            output += b"\x10" + uleb(OBJ_CMP)
            if node.op == "eq":
                return bytes(output) + b"\x50"
            if node.op == "ne":
                return bytes(output) + b"\x50\x45"
            order_opcodes = {"lt": 0x53, "gt": 0x55, "le": 0x57, "ge": 0x59}
            return bytes(output) + b"\x42\x00" + bytes([order_opcodes[node.op]])
        finally:
            self._release_wide_scratch()

    def _wide_part(self, value_local: int, value_type: ValueType, *, high: bool) -> bytes:
        small_tag = I128_SMALL_TAG if value_type is ValueType.I128 else U128_SMALL_TAG
        object_export = {
            (ValueType.I128, False): "7",
            (ValueType.I128, True): "8",
            (ValueType.U128, False): "4",
            (ValueType.U128, True): "5",
        }[(value_type, high)]
        if high:
            small_value = (
                b"\x20" + uleb(value_local) + b"\x42\x3f\x87"
                if value_type is ValueType.I128 else b"\x42\x00"
            )
        else:
            small_value = b"\x20" + uleb(value_local)
            small_value += b"\x42\x08" + (b"\x87" if value_type is ValueType.I128 else b"\x88")
        return b"".join([
            b"\x20", uleb(value_local), b"\x42", sleb(0xFF), b"\x83",
            b"\x42", sleb(small_tag), b"\x51",
            b"\x04\x7e",
            small_value,
            b"\x05",
            b"\x20", uleb(value_local), b"\x10", uleb(self.host_indices[("i", object_export)]),
            b"\x0b",
        ])

    def _wide_binary(self, node: ir.Binary) -> bytes:
        scratch = self._claim_wide_scratch()
        try:
            if node.op == "mul" and node.type is ValueType.U128:
                return self._u128_mul(node, scratch)
            if node.op == "div" and node.type is ValueType.U128:
                return self._u128_div(node, scratch)
            if node.op == "mul" and node.type is ValueType.I128:
                return self._i128_mul(node, scratch)
            if node.op == "div" and node.type is ValueType.I128:
                return self._i128_div(node, scratch)
            return self._wide_binary_with_scratch(node, scratch)
        finally:
            self._release_wide_scratch()

    def _wide_binary_with_scratch(self, node: ir.Binary, scratch: Tuple[int, ...]) -> bytes:
        lhs_val, rhs_val, lhs_hi, lhs_lo, rhs_hi, rhs_lo, result_hi, result_lo, result_val = scratch
        output = self._normalized_wide_values(node.left, node.right, scratch)

        if node.op == "add":
            output += b"\x20" + uleb(lhs_lo) + b"\x20" + uleb(rhs_lo) + b"\x7c\x21" + uleb(result_lo)
            output += b"\x20" + uleb(lhs_hi) + b"\x20" + uleb(rhs_hi) + b"\x7c"
            output += b"\x20" + uleb(result_lo) + b"\x20" + uleb(lhs_lo) + b"\x54\xad\x7c"
            output += b"\x21" + uleb(result_hi)
        else:
            output += b"\x20" + uleb(lhs_lo) + b"\x20" + uleb(rhs_lo) + b"\x7d\x21" + uleb(result_lo)
            output += b"\x20" + uleb(lhs_hi) + b"\x20" + uleb(rhs_hi) + b"\x7d"
            output += b"\x20" + uleb(lhs_lo) + b"\x20" + uleb(rhs_lo) + b"\x54\xad\x7d"
            output += b"\x21" + uleb(result_hi)

        constructor = "6" if node.type is ValueType.I128 else "3"
        output += b"\x20" + uleb(result_hi) + b"\x20" + uleb(result_lo)
        output += b"\x10" + uleb(self.host_indices[("i", constructor)]) + b"\x21" + uleb(result_val)

        if node.type is ValueType.U128:
            left, right = (result_val, lhs_val) if node.op == "add" else (lhs_val, rhs_val)
            output += b"\x20" + uleb(left) + b"\x20" + uleb(right) + b"\x10" + uleb(OBJ_CMP)
            output += b"\x42\x00\x53"
        else:
            sign = lambda local: b"\x20" + uleb(local) + b"\x42\x00\x53"
            lhs_sign, rhs_sign, result_sign = sign(lhs_hi), sign(rhs_hi), sign(result_hi)
            if node.op == "add":
                output += lhs_sign + rhs_sign + b"\x46" + result_sign + lhs_sign + b"\x47\x71"
            else:
                output += lhs_sign + rhs_sign + b"\x47" + result_sign + lhs_sign + b"\x47\x71"
        output += b"\x04\x40\x00\x0b"
        output += b"\x20" + uleb(result_val)
        return bytes(output)

    def call(self, node: ir.HostCall) -> bytes:
        if node.op in {
            "option_none", "option_some", "option_is_some", "option_unwrap",
            "result_ok", "result_err", "result_is_ok", "result_unwrap", "result_unwrap_err",
            "tuple_new", "union_new", "union_is", "union_unwrap", "try_call",
        }:
            return self._sum(node)
        if node.op == "u128_mul_div_floor":
            return self._u128_mul_div_floor(node)
        if node.op == "require_auth":
            return self.expression(node.args[0]) + b"\x10" + uleb(REQUIRE_AUTH)
        if node.op.startswith("storage_"):
            if node.op == "storage_set":
                key, value = node.args
                return (
                    self.expression(key) + self.encode_val(key.type)
                    + self.expression(value) + self.encode_val(value.type)
                    + b"\x42" + sleb(INSTANCE_STORAGE)
                    + b"\x10" + uleb(PUT_CONTRACT_DATA)
                )
            key = node.args[0]
            prefix = (
                self.expression(key) + self.encode_val(key.type)
                + b"\x42" + sleb(INSTANCE_STORAGE)
            )
            if node.op == "storage_has":
                return prefix + b"\x10" + uleb(HAS_CONTRACT_DATA) + b"\x42\x01\x51"
            raw = prefix + b"\x10" + uleb(GET_CONTRACT_DATA)
            if node.op == "storage_get_i32":
                return raw + b"\x42\x20\x87\xa7"
            if node.op == "storage_get_u32":
                return raw + b"\x42\x20\x88\xa7"
            if node.op in {"storage_get_i64", "storage_get_u64"}:
                value_type = ValueType.I64 if node.op.endswith("i64") else ValueType.U64
                return raw + self._decode_i64_val(value_type)
            if node.op == "storage_get_bool":
                return raw + b"\x42\x01\x51"
            if node.op in {
                "storage_get_i128", "storage_get_u128", "storage_get_u256",
                "storage_get_symbol", "storage_get_string", "storage_get_bytes",
            }:
                return raw
            if node.op == "storage_get":
                return raw + self._decode_call_result(node.type)
            if node.op == "storage_del":
                return prefix + b"\x10" + uleb(self.host_indices[("l", "2")])
        if node.op.startswith("pstorage_") or node.op.startswith("tstorage_"):
            return self._tier_storage(node)
        if node.op == "extend_instance":
            threshold, extend_to = node.args
            return b"".join([
                self.expression(threshold), self.encode_val(ValueType.U32),
                self.expression(extend_to), self.encode_val(ValueType.U32),
                b"\x10", uleb(self.host_indices[("l", "8")]),
            ])
        if node.op == "vec_new":
            return b"\x10" + uleb(self.host_indices[("v", "_")])
        if node.op == "map_new":
            return b"\x10" + uleb(self.host_indices[("m", "_")])
        if node.op == "vec_push":
            vector, item = node.args
            return b"".join([
                self.expression(vector),
                self.expression(item), self.encode_val(item.type),
                b"\x10", uleb(self.host_indices[("v", "6")]),
            ])
        if node.op == "vec_put":
            vector, index, item = node.args
            return b"".join([
                self.expression(vector),
                self.expression(index), self.encode_val(ValueType.U32),
                self.expression(item), self.encode_val(item.type),
                b"\x10", uleb(self.host_indices[("v", "0")]),
            ])
        if node.op == "vec_insert":
            vector, index, item = node.args
            return b"".join([
                self.expression(vector),
                self.expression(index), self.encode_val(ValueType.U32),
                self.expression(item), self.encode_val(item.type),
                b"\x10", uleb(self.host_indices[("v", "a")]),
            ])
        if node.op == "vec_del":
            vector, index = node.args
            return b"".join([
                self.expression(vector),
                self.expression(index), self.encode_val(ValueType.U32),
                b"\x10", uleb(self.host_indices[("v", "2")]),
            ])
        if node.op == "map_put":
            map_value, key, item = node.args
            return b"".join([
                self.expression(map_value),
                self.expression(key), self.encode_val(key.type),
                self.expression(item), self.encode_val(item.type),
                b"\x10", uleb(self.host_indices[("m", "0")]),
            ])
        if node.op == "map_del":
            map_value, key = node.args
            return b"".join([
                self.expression(map_value),
                self.expression(key), self.encode_val(key.type),
                b"\x10", uleb(self.host_indices[("m", "2")]),
            ])
        if node.op == "struct_new":
            return self._struct_new(node)
        if node.op in {
            "ledger_sequence", "ledger_version", "ledger_timestamp", "ledger_network",
            "current_contract", "sha256", "keccak256", "ed25519_verify", "log",
            "prng_bytes", "prng_u64", "string_len", "bytes_len", "string_to_bytes",
            "bytes_to_string", "bytes_slice",             "bytes_append", "upload_wasm", "upgrade",
            "deploy_asset", "to_xdr", "bytesn", "u256_to_be_bytes",
            "u256_from_be_bytes", "address_to_strkey",
        }:
            return self._simple_host(node)
        if node.op == "require_auth_for":
            address, *args = node.args
            return self.expression(address) + self._pack_values(args) + b"\x10" + uleb(self.host_indices[("a", "_")])
        if node.op in {"deploy", "deploy_constructor"}:
            return self._deploy(node)
        if node.op == "struct_field":
            owner, field = node.args
            raw = b"".join([
                self.expression(owner),
                self.expression(field), self.encode_val(ValueType.SYMBOL),
                b"\x10", uleb(self.host_indices[("m", "1")]),
            ])
            return raw + self._decode_call_result(node.type)
        if node.op == "event_publish":
            topics, data = node.args[:-1], node.args[-1]
            stored_topics = bytearray()
            for index, topic in enumerate(topics):
                stored_topics += b"\x41" + sleb(index * 8, 32)
                stored_topics += self.expression(topic) + self.encode_val(topic.type)
                stored_topics += b"\x37\x03\x00"  # i64.store align=8
            return b"".join([
                bytes(stored_topics),
                self._u32_val(0), self._u32_val(len(topics)),
                b"\x10", uleb(VEC_FROM_MEMORY),
                self.expression(data), self.encode_val(data.type),
                b"\x10", uleb(CONTRACT_EVENT),
            ])
        if node.op == "contract_call":
            target, function, *args = node.args
            stored_args = bytearray()
            for index, argument in enumerate(args):
                stored_args += b"\x41" + sleb(index * 8, 32)
                stored_args += self.expression(argument) + self.encode_val(argument.type)
                stored_args += b"\x37\x03\x00"
            called = b"".join([
                self.expression(target),
                self.expression(function),
                bytes(stored_args),
                self._u32_val(0), self._u32_val(len(args)),
                b"\x10", uleb(VEC_FROM_MEMORY),
                b"\x10", uleb(self.host_indices[("d", "_")]),
            ])
            return called + self._decode_call_result(node.type)
        if node.op == "vec_len":
            return (
                self.expression(node.args[0])
                + b"\x10" + uleb(self.host_indices[("v", "3")])
                + b"\x42\x20\x88\xa7"
            )
        if node.op == "vec_get":
            vector, index = node.args
            raw = b"".join([
                self.expression(vector),
                self.expression(index), self.encode_val(ValueType.U32),
                b"\x10", uleb(self.host_indices[("v", "1")]),
            ])
            return raw + self._decode_call_result(node.type)
        if node.op == "map_len":
            return (
                self.expression(node.args[0])
                + b"\x10" + uleb(self.host_indices[("m", "3")])
                + b"\x42\x20\x88\xa7"
            )
        if node.op in {"map_get", "map_has"}:
            map_value, key = node.args
            raw = b"".join([
                self.expression(map_value),
                self.expression(key), self.encode_val(key.type),
                b"\x10", uleb(self.host_indices[("m", "1" if node.op == "map_get" else "4")]),
            ])
            return raw + self._decode_call_result(node.type)
        raise AssertionError(node.op)

    def _tier_storage(self, node: ir.HostCall) -> bytes:
        durability = PERSISTENT_STORAGE if node.op.startswith("pstorage_") else TEMPORARY_STORAGE
        action = node.op.split("_", 1)[1]
        key = node.args[0]
        prefix = self.expression(key) + self.encode_val(key.type) + b"\x42" + sleb(durability)
        if action == "set":
            value = node.args[1]
            return (
                self.expression(key) + self.encode_val(key.type)
                + self.expression(value) + self.encode_val(value.type)
                + b"\x42" + sleb(durability)
                + b"\x10" + uleb(PUT_CONTRACT_DATA)
            )
        if action == "has":
            return prefix + b"\x10" + uleb(HAS_CONTRACT_DATA) + b"\x42\x01\x51"
        if action == "get":
            return prefix + b"\x10" + uleb(GET_CONTRACT_DATA) + self._decode_call_result(node.type)
        if action == "del":
            return prefix + b"\x10" + uleb(self.host_indices[("l", "2")])
        if action == "extend":
            _key, threshold, extend_to = node.args
            return b"".join([
                prefix,
                self.expression(threshold), self.encode_val(ValueType.U32),
                self.expression(extend_to), self.encode_val(ValueType.U32),
                b"\x10", uleb(self.host_indices[("l", "7")]),
            ])
        raise AssertionError(node.op)

    def _struct_new(self, node: ir.HostCall) -> bytes:
        slot = self._claim_wide_scratch()[0]
        try:
            struct = node.type
            output = bytearray()
            output += b"\x10" + uleb(self.host_indices[("m", "_")]) + b"\x21" + uleb(slot)
            for field, argument in zip(struct.fields, node.args):
                output += b"\x20" + uleb(slot)
                output += self.expression(ir.Constant(field.name, ValueType.SYMBOL))
                output += self.encode_val(ValueType.SYMBOL)
                output += self.expression(argument)
                output += self.encode_val(argument.type)
                output += b"\x10" + uleb(self.host_indices[("m", "0")])
                output += b"\x21" + uleb(slot)
            output += b"\x20" + uleb(slot)
            return bytes(output)
        finally:
            self._release_wide_scratch()

    def _simple_host(self, node: ir.HostCall) -> bytes:
        if node.op == "log":
            return self._log(node.args[0])
        if node.op == "prng_u64":
            return (
                self.expression(node.args[0])
                + self.expression(node.args[1])
                + b"\x10" + uleb(self.host_indices[("p", "1")])
            )
        direct = {
            "ledger_sequence": ("x", "3"),
            "ledger_version": ("x", "2"),
            "ledger_timestamp": ("x", "4"),
            "ledger_network": ("x", "6"),
            "current_contract": ("x", "7"),
            "sha256": ("c", "_"),
            "keccak256": ("c", "1"),
            "ed25519_verify": ("c", "0"),
            "string_len": ("b", "k"),
            "bytes_len": ("b", "8"),
            "string_to_bytes": ("b", "n"),
            "bytes_to_string": ("b", "o"),
            "bytes_append": ("b", "e"),
            "bytes_slice": ("b", "f"),
            "to_xdr": ("b", "_"),
            "u256_to_be_bytes": ("i", "b"),
            "u256_from_be_bytes": ("i", "a"),
            "address_to_strkey": ("a", "2"),
            "prng_bytes": ("p", "0"),
            "upload_wasm": ("l", "5"),
            "upgrade": ("l", "6"),
            "deploy_asset": ("l", "4"),
        }
        if node.op == "bytesn":
            return self._bytesn(node)
        output = bytearray()
        for argument in node.args:
            output += self.expression(argument)
            if not (node.op == "bytes_slice" and argument.type is ValueType.U32):
                output += self.encode_val(argument.type)
            else:
                output += self.encode_val(ValueType.U32)
        if node.op == "bytes_slice":
            output = bytearray()
            value, start, end = node.args
            output += self.expression(value)
            output += self.expression(start) + self.encode_val(ValueType.U32)
            output += self.expression(end) + self.encode_val(ValueType.U32)
        output += b"\x10" + uleb(self.host_indices[direct[node.op]])
        output += self._decode_call_result(node.type)
        return bytes(output)

    def _log(self, value: ir.Expression) -> bytes:
        if isinstance(value, ir.Constant) and isinstance(value.value, str):
            raw = value.value.encode("utf-8")
            offset = self.literals.intern(raw)
            return b"".join([
                self._u32_val(offset), self._u32_val(len(raw)),
                self._u32_val(0), self._u32_val(0),
                b"\x10", uleb(self.host_indices[("x", "_")]),
            ])
        string_slot, length_slot = self._claim_wide_scratch()[:2]
        try:
            return b"".join([
                self.expression(value), b"\x21", uleb(string_slot),
                b"\x20", uleb(string_slot),
                b"\x10", uleb(self.host_indices[("b", "k")]),
                b"\x21", uleb(length_slot),
                b"\x20", uleb(string_slot),
                self._u32_val(0), self._u32_val(0),
                b"\x20", uleb(length_slot),
                b"\x10", uleb(self.host_indices[("b", "g")]),
                b"\x1a",
                self._u32_val(0), b"\x20", uleb(length_slot),
                self._u32_val(0), self._u32_val(0),
                b"\x10", uleb(self.host_indices[("x", "_")]),
            ])
        finally:
            self._release_wide_scratch()

    def _tag_compare(self, value: bytes, tag: int, *, equal: bool) -> bytes:
        opcode = b"\x51" if equal else b"\x52"
        return value + b"\x42" + sleb(0xFF) + b"\x83" + b"\x42" + sleb(tag) + opcode

    def _guard_tag(self, value: bytes, tag: int, *, trap_if_equal: bool) -> bytes:
        scratch = uleb(self.locals.scratch)
        return b"".join([
            value,
            b"\x22", scratch,
            self._tag_compare(b"\x20" + scratch, tag, equal=trap_if_equal),
            b"\x04\x40\x00\x0b",
            b"\x20", scratch,
        ])

    def _sum(self, node: ir.HostCall) -> bytes:
        if node.op == "option_none":
            return b"\x42" + sleb(VOID_TAG)
        if node.op == "option_some":
            return self.expression(node.args[0]) + self.encode_val(node.args[0].type)
        if node.op == "option_is_some":
            return self._tag_compare(self.expression(node.args[0]), VOID_TAG, equal=False)
        if node.op == "option_unwrap":
            guarded = self._guard_tag(self.expression(node.args[0]), VOID_TAG, trap_if_equal=True)
            return guarded + self._decode_call_result(node.type)
        if node.op == "result_ok":
            return self.expression(node.args[0]) + self.encode_val(node.args[0].type)
        if node.op == "result_err":
            error_val = (node.args[0].value << 32) | ERROR_TAG
            if error_val >= 2**63:
                error_val -= 2**64
            return b"\x42" + sleb(error_val)
        if node.op == "result_is_ok":
            return self._tag_compare(self.expression(node.args[0]), ERROR_TAG, equal=False)
        if node.op == "result_unwrap":
            guarded = self._guard_tag(self.expression(node.args[0]), ERROR_TAG, trap_if_equal=True)
            return guarded + self._decode_call_result(node.type)
        if node.op == "result_unwrap_err":
            guarded = self._guard_tag(self.expression(node.args[0]), ERROR_TAG, trap_if_equal=False)
            return guarded + b"\x42\x20\x88\xa7"
        if node.op == "tuple_new":
            return self._pack_values(node.args)
        if node.op == "union_new":
            if len(node.args) == 1:
                return self.expression(node.args[0])
            return self._pack_values(node.args)
        if node.op == "union_is":
            value, symbol, flag = node.args
            if flag.value == 0:
                compared = self.expression(value) + self.expression(symbol) + b"\x10" + uleb(OBJ_CMP)
                return compared + b"\x50"
            raw = b"".join([
                self.expression(value),
                self._u32_val(0),
                b"\x10", uleb(self.host_indices[("v", "1")]),
                self.expression(symbol),
                b"\x10", uleb(OBJ_CMP),
                b"\x50",
            ])
            return raw
        if node.op == "union_unwrap":
            value, symbol = node.args
            scratch = uleb(self.locals.scratch)
            raw = b"".join([
                self.expression(value),
                b"\x22", scratch,
                self._u32_val(0),
                b"\x10", uleb(self.host_indices[("v", "1")]),
                self.expression(symbol),
                b"\x10", uleb(OBJ_CMP),
                b"\x50",  # i64.eqz
                b"\x45",  # i32.eqz: 1 when the case symbol differs
                b"\x04\x40\x00\x0b",
                b"\x20", scratch,
                self._u32_val(1),
                b"\x10", uleb(self.host_indices[("v", "1")]),
            ])
            return raw + self._decode_call_result(node.type)
        if node.op == "try_call":
            target, function, *args = node.args
            stored_args = bytearray()
            for index, argument in enumerate(args):
                stored_args += b"\x41" + sleb(index * 8, 32)
                stored_args += self.expression(argument) + self.encode_val(argument.type)
                stored_args += b"\x37\x03\x00"
            return b"".join([
                self.expression(target),
                self.expression(function),
                bytes(stored_args),
                self._u32_val(0), self._u32_val(len(args)),
                b"\x10", uleb(VEC_FROM_MEMORY),
                b"\x10", uleb(self.host_indices[("d", "0")]),
            ])
        raise AssertionError(node.op)

    def _bytesn(self, node: ir.HostCall) -> bytes:
        size = node.type.size
        scratch = uleb(self.locals.scratch)
        return b"".join([
            self.expression(node.args[0]),
            self.encode_val(node.args[0].type),
            b"\x22", scratch,
            b"\x10", uleb(self.host_indices[("b", "8")]),
            b"\x42\x20\x88\xa7",
            b"\x41", sleb(size, 32),
            b"\x47",
            b"\x04\x40\x00\x0b",
            b"\x20", scratch,
        ])

    def _pack_values(self, args) -> bytes:
        stored = bytearray()
        for index, argument in enumerate(args):
            stored += b"\x41" + sleb(index * 8, 32)
            stored += self.expression(argument) + self.encode_val(argument.type)
            stored += b"\x37\x03\x00"
        return bytes(stored) + self._u32_val(0) + self._u32_val(len(args)) + b"\x10" + uleb(VEC_FROM_MEMORY)

    def _deploy(self, node: ir.HostCall) -> bytes:
        addr, wasm_hash, salt = self._claim_wide_scratch()[:3]
        try:
            wasm_arg, salt_arg, *rest = node.args
            output = bytearray()
            output += self.expression(wasm_arg) + b"\x21" + uleb(wasm_hash)
            output += self.expression(salt_arg) + b"\x21" + uleb(salt)
            output += b"\x10" + uleb(self.host_indices[("x", "7")]) + b"\x21" + uleb(addr)
            output += b"\x20" + uleb(addr) + b"\x20" + uleb(wasm_hash) + b"\x20" + uleb(salt)
            if node.op == "deploy_constructor":
                output += self._pack_values(rest)
            export = "e" if node.op == "deploy_constructor" else "3"
            output += b"\x10" + uleb(self.host_indices[("l", export)])
            return bytes(output)
        finally:
            self._release_wide_scratch()

    def _u128_product(self, node: ir.Binary, scratch: Tuple[int, ...], *, divide: bool) -> bytes:
        lhs_val, rhs_val, lhs_hi, lhs_lo, rhs_hi, rhs_lo, result_hi, result_lo, _result_val = scratch
        output = self._normalized_wide_values(node.left, node.right, scratch)
        for value_local, hi_local, lo_local in ((lhs_val, lhs_hi, lhs_lo), (rhs_val, rhs_hi, rhs_lo)):
            output += b"\x42\x00\x42\x00\x20" + uleb(hi_local) + b"\x20" + uleb(lo_local)
            output += b"\x10" + uleb(self.host_indices[("i", "9")]) + b"\x21" + uleb(value_local)
        output += b"\x20" + uleb(lhs_val) + b"\x20" + uleb(rhs_val)
        output += b"\x10" + uleb(self.host_indices[("i", "q" if divide else "p")])
        output += b"\x21" + uleb(lhs_val)
        if not divide:
            output += self._u256_part(lhs_val, 0) + b"\x21" + uleb(result_hi)
            output += self._u256_part(lhs_val, 1) + b"\x21" + uleb(result_lo)
            output += b"\x20" + uleb(result_hi) + b"\x20" + uleb(result_lo) + b"\x84\x50\x45"
            output += b"\x04\x40\x00\x0b"
        output += self._u256_part(lhs_val, 2) + b"\x21" + uleb(result_hi)
        output += self._u256_part(lhs_val, 3) + b"\x21" + uleb(result_lo)
        output += b"\x20" + uleb(result_hi) + b"\x20" + uleb(result_lo)
        output += b"\x10" + uleb(self.host_indices[("i", "3")])
        return bytes(output)

    def _u128_mul(self, node: ir.Binary, scratch: Tuple[int, ...]) -> bytes:
        return self._u128_product(node, scratch, divide=False)

    def _u128_div(self, node: ir.Binary, scratch: Tuple[int, ...]) -> bytes:
        return self._u128_product(node, scratch, divide=True)

    def _i128_mul(self, node: ir.Binary, scratch: Tuple[int, ...]) -> bytes:
        lhs_val, rhs_val, lhs_hi, lhs_lo, rhs_hi, rhs_lo, result_hi, result_lo, sign = scratch
        output = self._normalized_wide_values(node.left, node.right, scratch)

        def widen(value_local: int, hi_local: int, lo_local: int) -> bytes:
            return b"".join([
                b"\x20", uleb(hi_local), b"\x42", sleb(63), b"\x87", b"\x21", uleb(sign),
                b"\x20", uleb(sign), b"\x20", uleb(sign),
                b"\x20", uleb(hi_local), b"\x20", uleb(lo_local),
                b"\x10", uleb(self.host_indices[("i", "g")]),
                b"\x21", uleb(value_local),
            ])

        output += widen(lhs_val, lhs_hi, lhs_lo)
        output += widen(rhs_val, rhs_hi, rhs_lo)
        output += b"\x20" + uleb(lhs_val) + b"\x20" + uleb(rhs_val)
        output += b"\x10" + uleb(self.host_indices[("i", "x")]) + b"\x21" + uleb(lhs_val)
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "l")])
        output += b"\x21" + uleb(result_lo)
        output += b"\x20" + uleb(result_lo) + b"\x42" + sleb(63) + b"\x87" + b"\x21" + uleb(sign)
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "j")])
        output += b"\x20" + uleb(sign) + b"\x52"
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "k")])
        output += b"\x20" + uleb(sign) + b"\x52\x72"
        output += b"\x04\x40\x00\x0b"
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "m")])
        output += b"\x21" + uleb(result_hi)
        output += b"\x20" + uleb(result_lo) + b"\x20" + uleb(result_hi)
        output += b"\x10" + uleb(self.host_indices[("i", "6")])
        return bytes(output)

    def _i128_div(self, node: ir.Binary, scratch: Tuple[int, ...]) -> bytes:
        """Python floor division on top of truncating host i256 division.

        q = trunc(a / b). When the division is inexact and the signs differ,
        q -= 1. A zero divisor traps inside i.y. A quotient that is not a
        valid i128, including i128 min // -1, traps with unreachable.
        """
        lhs_val, rhs_val, lhs_hi, lhs_lo, rhs_hi, rhs_lo, dividend, product, sign = scratch
        output = self._normalized_wide_values(node.left, node.right, scratch)

        def widen(value_local: int, hi_local: int, lo_local: int) -> bytes:
            return b"".join([
                b"\x20", uleb(hi_local), b"\x42", sleb(63), b"\x87", b"\x21", uleb(sign),
                b"\x20", uleb(sign), b"\x20", uleb(sign),
                b"\x20", uleb(hi_local), b"\x20", uleb(lo_local),
                b"\x10", uleb(self.host_indices[("i", "g")]),
                b"\x21", uleb(value_local),
            ])

        output += widen(lhs_val, lhs_hi, lhs_lo)
        output += widen(rhs_val, rhs_hi, rhs_lo)
        output += b"\x20" + uleb(lhs_val) + b"\x21" + uleb(dividend)
        output += b"\x20" + uleb(lhs_val) + b"\x20" + uleb(rhs_val)
        output += b"\x10" + uleb(self.host_indices[("i", "y")]) + b"\x21" + uleb(lhs_val)
        output += b"\x20" + uleb(lhs_val) + b"\x20" + uleb(rhs_val)
        output += b"\x10" + uleb(self.host_indices[("i", "x")]) + b"\x21" + uleb(product)
        # inexact (obj_cmp != 0) and the operand signs differ
        output += b"\x20" + uleb(product) + b"\x20" + uleb(dividend)
        output += b"\x10" + uleb(self.host_indices[("x", "0")]) + b"\x50\x45"
        output += b"\x20" + uleb(lhs_hi) + b"\x42\x00\x53"
        output += b"\x20" + uleb(rhs_hi) + b"\x42\x00\x53\x73\x71"
        output += b"\x04\x40"
        output += b"\x20" + uleb(lhs_val)
        output += b"\x42\x00\x42\x00\x42\x00\x42\x01"
        output += b"\x10" + uleb(self.host_indices[("i", "g")])
        output += b"\x10" + uleb(self.host_indices[("i", "w")])
        output += b"\x21" + uleb(lhs_val)
        output += b"\x0b"
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "l")])
        output += b"\x21" + uleb(product)
        output += b"\x20" + uleb(product) + b"\x42" + sleb(63) + b"\x87" + b"\x21" + uleb(sign)
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "j")])
        output += b"\x20" + uleb(sign) + b"\x52"
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "k")])
        output += b"\x20" + uleb(sign) + b"\x52\x72"
        output += b"\x04\x40\x00\x0b"
        output += b"\x20" + uleb(lhs_val) + b"\x10" + uleb(self.host_indices[("i", "m")])
        output += b"\x21" + uleb(dividend)
        output += b"\x20" + uleb(product) + b"\x20" + uleb(dividend)
        output += b"\x10" + uleb(self.host_indices[("i", "6")])
        return bytes(output)

    def _u256_part(self, value_local: int, part: int) -> bytes:
        object_export = ("c", "d", "e", "f")[part]
        small_value = (
            b"\x20" + uleb(value_local) + b"\x42\x08\x88"
            if part == 3 else b"\x42\x00"
        )
        return b"".join([
            b"\x20", uleb(value_local), b"\x42", sleb(0xFF), b"\x83",
            b"\x42", sleb(U256_SMALL_TAG), b"\x51",
            b"\x04\x7e",
            small_value,
            b"\x05",
            b"\x20", uleb(value_local), b"\x10", uleb(self.host_indices[("i", object_export)]),
            b"\x0b",
        ])

    def _u128_mul_div_floor(self, node: ir.HostCall) -> bytes:
        scratch = self._claim_wide_scratch()
        try:
            return self._u128_mul_div_floor_with_scratch(node, scratch)
        finally:
            self._release_wide_scratch()

    def _u128_mul_div_floor_with_scratch(self, node: ir.HostCall, scratch: Tuple[int, ...]) -> bytes:
        left, right, denominator = node.args
        left_val, right_val, denominator_val, high, low, upper_hi, upper_lo, result_hi, result_lo = scratch
        output = bytearray()
        for expression, value_local in (
            (left, left_val),
            (right, right_val),
            (denominator, denominator_val),
        ):
            output += self.expression(expression) + b"\x21" + uleb(value_local)
            output += self._wide_part(value_local, ValueType.U128, high=True) + b"\x21" + uleb(high)
            output += self._wide_part(value_local, ValueType.U128, high=False) + b"\x21" + uleb(low)
            output += b"\x42\x00\x42\x00\x20" + uleb(high) + b"\x20" + uleb(low)
            output += b"\x10" + uleb(self.host_indices[("i", "9")]) + b"\x21" + uleb(value_local)

        output += b"\x20" + uleb(left_val) + b"\x20" + uleb(right_val)
        output += b"\x10" + uleb(self.host_indices[("i", "p")])
        output += b"\x20" + uleb(denominator_val)
        output += b"\x10" + uleb(self.host_indices[("i", "q")]) + b"\x21" + uleb(left_val)

        output += self._u256_part(left_val, 0) + b"\x21" + uleb(upper_hi)
        output += self._u256_part(left_val, 1) + b"\x21" + uleb(upper_lo)
        output += b"\x20" + uleb(upper_hi) + b"\x20" + uleb(upper_lo) + b"\x84\x50\x45"
        output += b"\x04\x40\x00\x0b"
        output += self._u256_part(left_val, 2) + b"\x21" + uleb(result_hi)
        output += self._u256_part(left_val, 3) + b"\x21" + uleb(result_lo)
        output += b"\x20" + uleb(result_hi) + b"\x20" + uleb(result_lo)
        output += b"\x10" + uleb(self.host_indices[("i", "3")])
        return bytes(output)

    def _decode_call_result(self, value_type: ContractType) -> bytes:
        if value_type is ValueType.VOID:
            # Soroban host functions still return a Void Val. Leave it on the
            # stack so the enclosing IR Drop consumes it like other Void calls.
            return b""
        if value_type is ValueType.I32:
            return b"\x42\x20\x87\xa7"
        if value_type is ValueType.U32 or isinstance(value_type, EnumType):
            return b"\x42\x20\x88\xa7"
        if value_type is ValueType.BOOL:
            return b"\x42\x01\x51"
        if value_type in {ValueType.I64, ValueType.U64}:
            return self._decode_i64_val(value_type)
        if is_object_type(value_type):
            return b""
        raise AssertionError(value_type)

    @staticmethod
    def _u32_val(value: int) -> bytes:
        signed = value if value < 2**31 else value - 2**32
        return b"\x41" + sleb(signed, 32) + FunctionEmitter.encode_val(ValueType.U32)

    @staticmethod
    def encode_val(value_type: ContractType) -> bytes:
        if value_type is ValueType.I32:
            # Preserve the i32 bit pattern, shift it into Val.major, add tag 5.
            return b"\xad\x42\x20\x86\x42" + sleb(I32_TAG) + b"\x84"
        if value_type is ValueType.U32 or isinstance(value_type, EnumType):
            return b"\xad\x42\x20\x86\x42" + sleb(U32_TAG) + b"\x84"
        if value_type is ValueType.I64:
            return b"\x10" + uleb(OBJ_FROM_I64)
        if value_type is ValueType.U64:
            return b"\x10" + uleb(OBJ_FROM_U64)
        if value_type is ValueType.BOOL:
            return b"\xad"  # i64.extend_i32_u; tags are false=0, true=1
        if is_object_type(value_type):
            return b""
        if value_type is ValueType.VOID:
            return b"\x42" + sleb(VOID_TAG)
        raise AssertionError(value_type)


def _wide_expression_depth(function: ir.Function) -> int:
    def expression(node: ir.Expression) -> int:
        if isinstance(node, ir.HostCall):
            child = max((expression(arg) for arg in node.args), default=0)
            return child + (1 if node.op in {
                "u128_mul_div_floor", "struct_new", "log", "deploy", "deploy_constructor",
            } else 0)
        if isinstance(node, ir.Unary):
            return expression(node.operand)
        if isinstance(node, (ir.Binary, ir.Compare)):
            child = max(expression(node.left), expression(node.right))
            uses_frame = (
                isinstance(node, ir.Binary) and node.type in WIDE_INTEGER_TYPES
            ) or (
                isinstance(node, ir.Compare) and node.left.type in WIDE_INTEGER_TYPES
            )
            return child + (1 if uses_frame else 0)
        return 0

    def statement(node: ir.Statement) -> int:
        if isinstance(node, (ir.Return, ir.SetLocal, ir.Drop)):
            return expression(node.value)
        if isinstance(node, ir.If):
            return max(
                expression(node.test),
                *(statement(child) for child in node.body + node.otherwise),
            )
        if isinstance(node, ir.ForRange):
            return max(
                expression(node.start), expression(node.stop),
                *(statement(child) for child in node.body),
            )
        return 0

    return max((statement(item) for item in function.body), default=0)


def emit_module(contract: ir.Contract, protocol: int = 25) -> bytes:
    literals = LiteralPool(max(8, _max_linear_values(contract) * 8))
    optional_imports = []
    def optional(host_import):
        if host_import not in optional_imports and host_import not in HOST_IMPORTS:
            optional_imports.append(host_import)

    if _uses_host_op(contract, "vec_get"):
        optional_imports.append(("v", "1", 2))
    if _uses_host_op(contract, "vec_len"):
        optional_imports.append(("v", "3", 1))
    if _uses_host_op(contract, "map_get"):
        optional_imports.append(("m", "1", 2))
    if _uses_host_op(contract, "map_len"):
        optional_imports.append(("m", "3", 1))
    if _uses_host_op(contract, "map_has"):
        optional_imports.append(("m", "4", 2))
    if _uses_host_op(contract, "contract_call"):
        optional(CONTRACT_CALL_IMPORT)
    if _uses_constant_type(contract, ValueType.U128):
        optional(("i", "3", 2))
    if _uses_constant_type(contract, ValueType.U256):
        optional(("i", "9", 4))
    if _uses_constant_type(contract, ValueType.I128):
        optional(("i", "6", 2))
    wide_operations = _wide_operation_types(contract)
    if ValueType.U128 in wide_operations:
        for host_import in (("i", "3", 2), ("i", "4", 1), ("i", "5", 1)):
            optional(host_import)
    if ValueType.I128 in wide_operations:
        for host_import in (("i", "6", 2), ("i", "7", 1), ("i", "8", 1)):
            optional(host_import)
    if _contains_fail(contract):
        optional(("x", "5", 1))  # fail_with_error
    if _uses_host_op(contract, "u128_mul_div_floor"):
        for host_import in (
            ("i", "3", 2), ("i", "4", 1), ("i", "5", 1),
            ("i", "9", 4), ("i", "c", 1), ("i", "d", 1),
            ("i", "e", 1), ("i", "f", 1), ("i", "p", 2), ("i", "q", 2),
        ):
            optional(host_import)
    for host_import in _collection_imports(contract):
        optional(host_import)
    for host_import in _service_imports(contract):
        optional(host_import)
    host_imports = HOST_IMPORTS + tuple(optional_imports)
    host_indices = {(module, field): index for index, (module, field, _) in enumerate(host_imports)}
    emitters = [FunctionEmitter(function, literals, host_indices) for function in contract.functions]

    # Every exported Soroban function receives and returns 64-bit Val values.
    type_entries = []
    signature_indices: Dict[Tuple[int, int], int] = {}
    for _, _, arity in host_imports:
        signature = (arity, 1)
        if signature not in signature_indices:
            signature_indices[signature] = len(type_entries)
            type_entries.append(b"\x60" + vector([b"\x7e"] * arity) + vector([b"\x7e"]))
    type_indices: Dict[int, int] = {}
    for function in contract.functions:
        arity = len(function.params)
        signature = (arity, 1)
        if signature not in signature_indices:
            signature_indices[signature] = len(type_entries)
            type_entries.append(b"\x60" + vector([b"\x7e"] * arity) + vector([b"\x7e"]))
        type_indices[arity] = signature_indices[signature]

    function_section = vector([uleb(type_indices[len(fn.params)]) for fn in contract.functions])
    imports = [
        name(module) + name(field) + b"\x00" + uleb(signature_indices[(arity, 1)])
        for module, field, arity in host_imports
    ]
    exports = [
        name(fn.name) + b"\x00" + uleb(len(host_imports) + index)
        for index, fn in enumerate(contract.functions)
    ]
    code_section = vector([emitter.emit() for emitter in emitters])
    exports.append(name("memory") + b"\x02\x00")
    memory_pages = max(1, (len(literals.data) + 65535) // 65536)
    memory_section = vector([b"\x00" + uleb(memory_pages)])
    data_segment = b"\x00\x41\x00\x0b" + uleb(len(literals.data)) + bytes(literals.data)

    return b"".join([
        b"\x00asm\x01\x00\x00\x00",
        custom_section("contractenvmetav0", environment_metadata(protocol)),
        custom_section("contractspecv0", contract_spec(contract)),
        custom_section("contractmetav0", _contract_metadata(contract)),
        section(1, vector(type_entries)),
        section(2, vector(imports)),
        section(3, function_section),
        section(5, memory_section),
        section(7, vector(exports)),
        section(10, code_section),
        section(11, vector([data_segment])),
    ])


def _max_linear_values(contract: ir.Contract) -> int:
    maximum = 1

    def expression(node: ir.Expression):
        nonlocal maximum
        if isinstance(node, ir.HostCall):
            if node.op == "event_publish":
                maximum = max(maximum, len(node.args) - 1)
            elif node.op in {"contract_call", "try_call"}:
                maximum = max(maximum, len(node.args) - 2)
            elif node.op == "require_auth_for":
                maximum = max(maximum, len(node.args) - 1)
            elif node.op == "deploy_constructor":
                maximum = max(maximum, max(0, len(node.args) - 2))
            for arg in node.args:
                expression(arg)
        elif isinstance(node, ir.Unary):
            expression(node.operand)
        elif isinstance(node, (ir.Binary, ir.Compare)):
            expression(node.left)
            expression(node.right)

    def statement(node: ir.Statement):
        if isinstance(node, ir.Return):
            expression(node.value)
        elif isinstance(node, ir.SetLocal):
            expression(node.value)
        elif isinstance(node, ir.If):
            expression(node.test)
            for child in node.body + node.otherwise:
                statement(child)
        elif isinstance(node, ir.ForRange):
            expression(node.start)
            expression(node.stop)
            for child in node.body:
                statement(child)
        elif isinstance(node, ir.Drop):
            expression(node.value)

    for function in contract.functions:
        for item in function.body:
            statement(item)
    return maximum


def _collection_imports(contract: ir.Contract):
    """Host imports introduced by structs, collection updates, and storage tiers."""
    needed = {
        "vec_new": ("v", "_", 0),
        "vec_push": ("v", "6", 2),
        "vec_put": ("v", "0", 3),
        "vec_insert": ("v", "a", 3),
        "vec_del": ("v", "2", 2),
        "vec_back": ("v", "9", 1),
        "vec_pop": ("v", "7", 1),
        "map_new": ("m", "_", 0),
        "map_put": ("m", "0", 3),
        "map_del": ("m", "2", 2),
        "struct_new": ("m", "_", 0),
        "struct_field": ("m", "1", 2),
        "storage_del": ("l", "2", 2),
        "pstorage_del": ("l", "2", 2),
        "tstorage_del": ("l", "2", 2),
        "pstorage_extend": ("l", "7", 4),
        "tstorage_extend": ("l", "7", 4),
        "extend_instance": ("l", "8", 2),
    }
    found = set()

    def expression(node: ir.Expression):
        if isinstance(node, ir.HostCall):
            if node.op in needed:
                found.add(node.op)
            if node.op == "struct_new":
                found.add("struct_new")
                found.add("map_put")
            for arg in node.args:
                expression(arg)
        elif isinstance(node, ir.Unary):
            expression(node.operand)
        elif isinstance(node, (ir.Binary, ir.Compare)):
            expression(node.left)
            expression(node.right)

    def statement(node: ir.Statement):
        if isinstance(node, ir.PopBack):
            found.add("vec_back")
            found.add("vec_pop")
        elif isinstance(node, (ir.Return, ir.SetLocal, ir.Drop)):
            expression(node.value)
        elif isinstance(node, ir.If):
            expression(node.test)
            for child in node.body + node.otherwise:
                statement(child)
        elif isinstance(node, ir.ForRange):
            expression(node.start)
            expression(node.stop)
            for child in node.body:
                statement(child)

    for function in contract.functions:
        for item in function.body:
            statement(item)
    imports = []
    for op in (
        "vec_new", "vec_push", "vec_put", "vec_insert", "vec_del", "vec_back", "vec_pop",
        "map_new", "map_put", "map_del", "struct_field", "storage_del", "pstorage_del",
        "tstorage_del", "pstorage_extend", "tstorage_extend", "extend_instance",
    ):
        if op in found and needed[op] not in imports:
            imports.append(needed[op])
    if "struct_new" in found:
        for op in ("map_new", "map_put"):
            if needed[op] not in imports:
                imports.append(needed[op])
    return imports


def _service_imports(contract: ir.Contract):
    needed = {
        "ledger_sequence": ("x", "3", 0),
        "ledger_version": ("x", "2", 0),
        "ledger_timestamp": ("x", "4", 0),
        "ledger_network": ("x", "6", 0),
        "current_contract": ("x", "7", 0),
        "sha256": ("c", "_", 1),
        "keccak256": ("c", "1", 1),
        "ed25519_verify": ("c", "0", 3),
        "log": ("x", "_", 4),
        "string_len": ("b", "k", 1),
        "bytes_len": ("b", "8", 1),
        "string_to_bytes": ("b", "n", 1),
        "bytes_to_string": ("b", "o", 1),
        "bytes_slice": ("b", "f", 3),
        "bytes_append": ("b", "e", 2),
        "to_xdr": ("b", "_", 1),
        "bytesn": ("b", "8", 1),
        "u256_to_be_bytes": ("i", "b", 1),
        "u256_from_be_bytes": ("i", "a", 1),
        "address_to_strkey": ("a", "2", 1),
        "try_call": ("d", "0", 3),
        "union_is": ("v", "1", 2),
        "union_unwrap": ("v", "1", 2),
        "prng_bytes": ("p", "0", 1),
        "prng_u64": ("p", "1", 2),
        "upload_wasm": ("l", "5", 1),
        "upgrade": ("l", "6", 1),
        "deploy_asset": ("l", "4", 1),
        "require_auth_for": ("a", "_", 2),
        "deploy": ("l", "3", 3),
        "deploy_constructor": ("l", "e", 4),
    }
    found = set()
    dynamic_log = False
    wide = set()

    def expression(node: ir.Expression):
        nonlocal dynamic_log
        if isinstance(node, ir.Binary) and node.type in WIDE_INTEGER_TYPES | {ValueType.U256} and node.op in {"add", "sub", "mul", "div"}:
            wide.add((node.type, node.op))
        if isinstance(node, ir.HostCall):
            if node.op in needed:
                found.add(node.op)
            if node.op == "log" and not isinstance(node.args[0], ir.Constant):
                dynamic_log = True
            for arg in node.args:
                expression(arg)
        elif isinstance(node, ir.Unary):
            expression(node.operand)
        elif isinstance(node, (ir.Binary, ir.Compare)):
            expression(node.left)
            expression(node.right)

    def statement(node: ir.Statement):
        if isinstance(node, (ir.Return, ir.SetLocal, ir.Drop)):
            expression(node.value)
        elif isinstance(node, ir.If):
            expression(node.test)
            for child in node.body + node.otherwise:
                statement(child)
        elif isinstance(node, ir.ForRange):
            expression(node.start)
            expression(node.stop)
            for child in node.body:
                statement(child)

    for function in contract.functions:
        for item in function.body:
            statement(item)
    imports = []

    def add(item):
        if item not in imports:
            imports.append(item)

    for op in needed:
        if op in found:
            add(needed[op])
    if dynamic_log:
        add(("b", "k", 1))
        add(("b", "g", 4))
    if "deploy" in found or "deploy_constructor" in found:
        add(("x", "7", 0))
    if (ValueType.U128, "mul") in wide or (ValueType.U128, "div") in wide:
        for item in (("i", "9", 4), ("i", "c", 1), ("i", "d", 1), ("i", "e", 1), ("i", "f", 1), ("i", "3", 2)):
            add(item)
        if (ValueType.U128, "mul") in wide:
            add(("i", "p", 2))
        if (ValueType.U128, "div") in wide:
            add(("i", "q", 2))
    if (ValueType.I128, "mul") in wide or (ValueType.I128, "div") in wide:
        for item in (("i", "g", 4), ("i", "x", 2), ("i", "j", 1), ("i", "k", 1), ("i", "l", 1), ("i", "m", 1), ("i", "6", 2)):
            add(item)
    if (ValueType.I128, "div") in wide:
        add(("i", "y", 2))
        add(("i", "w", 2))
    u256_exports = {"add": ("i", "n", 2), "sub": ("i", "o", 2), "mul": ("i", "p", 2), "div": ("i", "q", 2)}
    for op, item in u256_exports.items():
        if (ValueType.U256, op) in wide:
            add(item)
    return imports


def _contains_fail(contract: ir.Contract) -> bool:
    def statement(node: ir.Statement) -> bool:
        if isinstance(node, ir.Fail):
            return True
        if isinstance(node, ir.If):
            return any(statement(child) for child in node.body + node.otherwise)
        if isinstance(node, ir.ForRange):
            return any(statement(child) for child in node.body)
        return False

    return any(statement(item) for function in contract.functions for item in function.body)


def _uses_host_op(contract: ir.Contract, op: str) -> bool:
    def expression(node: ir.Expression) -> bool:
        if isinstance(node, ir.HostCall):
            return node.op == op or any(expression(arg) for arg in node.args)
        if isinstance(node, ir.Unary):
            return expression(node.operand)
        if isinstance(node, (ir.Binary, ir.Compare)):
            return expression(node.left) or expression(node.right)
        return False

    def statement(node: ir.Statement) -> bool:
        if isinstance(node, (ir.Return, ir.SetLocal, ir.Drop)):
            value = node.value
            return expression(value)
        if isinstance(node, ir.If):
            return expression(node.test) or any(statement(child) for child in node.body + node.otherwise)
        if isinstance(node, ir.ForRange):
            return expression(node.start) or expression(node.stop) or any(statement(child) for child in node.body)
        return False

    return any(statement(item) for function in contract.functions for item in function.body)


def _uses_constant_type(contract: ir.Contract, value_type: ValueType) -> bool:
    def expression(node: ir.Expression) -> bool:
        if isinstance(node, ir.Constant):
            return node.type is value_type
        if isinstance(node, ir.HostCall):
            return any(expression(arg) for arg in node.args)
        if isinstance(node, ir.Unary):
            return expression(node.operand)
        if isinstance(node, (ir.Binary, ir.Compare)):
            return expression(node.left) or expression(node.right)
        return False

    def statement(node: ir.Statement) -> bool:
        if isinstance(node, (ir.Return, ir.SetLocal, ir.Drop)):
            return expression(node.value)
        if isinstance(node, ir.If):
            return expression(node.test) or any(statement(child) for child in node.body + node.otherwise)
        if isinstance(node, ir.ForRange):
            return expression(node.start) or expression(node.stop) or any(statement(child) for child in node.body)
        return False

    return any(statement(item) for function in contract.functions for item in function.body)


def _wide_operation_types(contract: ir.Contract) -> set:
    found = set()

    def expression(node: ir.Expression) -> None:
        if isinstance(node, ir.Binary) and node.type in WIDE_INTEGER_TYPES:
            found.add(node.type)
        if isinstance(node, ir.Compare) and node.left.type in WIDE_INTEGER_TYPES:
            found.add(node.left.type)
        if isinstance(node, ir.HostCall):
            for arg in node.args:
                expression(arg)
        elif isinstance(node, ir.Unary):
            expression(node.operand)
        elif isinstance(node, (ir.Binary, ir.Compare)):
            expression(node.left)
            expression(node.right)

    def statement(node: ir.Statement) -> None:
        if isinstance(node, (ir.Return, ir.SetLocal, ir.Drop)):
            expression(node.value)
        elif isinstance(node, ir.If):
            expression(node.test)
            for child in node.body + node.otherwise:
                statement(child)
        elif isinstance(node, ir.ForRange):
            expression(node.start)
            expression(node.stop)
            for child in node.body:
                statement(child)

    for function in contract.functions:
        for item in function.body:
            statement(item)
    return found


def _contract_metadata(contract: ir.Contract) -> bytes:
    # SCMetaEntry::ScMetaV0 { key, val }, encoded as an XDR stream.
    from .xdr import u32, xdr_string
    return b"".join([
        u32(0) + xdr_string("name") + xdr_string(contract.name),
        u32(0) + xdr_string("source_lang") + xdr_string("pysoroban"),
    ])
