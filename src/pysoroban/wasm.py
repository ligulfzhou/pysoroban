from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from . import ir
from .model import ValueType, VEC_ELEMENT_TYPES
from .xdr import contract_spec, environment_metadata


I32_TAG = 5
U32_TAG = 4
U64_SMALL_TAG = 6
I64_SMALL_TAG = 7
VOID_TAG = 2
INSTANCE_STORAGE = 2

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

OBJECT_TYPES = {
    ValueType.ADDRESS,
    ValueType.BYTES,
    ValueType.STRING,
    ValueType.SYMBOL,
} | set(VEC_ELEMENT_TYPES)
I64_TYPES = OBJECT_TYPES | {ValueType.I64, ValueType.U64}


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


class FunctionEmitter:
    """Emit Wasm from typed IR; this backend has no dependency on Python AST."""

    def __init__(self, function: ir.Function, literals: LiteralPool, host_indices=None):
        self.function = function
        self.literals = literals
        self.host_indices = host_indices or {}
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
        local_types = [0x7E if types[item] in I64_TYPES else 0x7F for item in names]
        scratch = len(self.function.params) + len(local_types)
        local_types.append(0x7E)
        return Locals(param_raw, native, types, local_types, scratch)

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

    def _decode_param(self, variable: str, value_type: ValueType) -> bytes:
        raw_index = self.locals.param_raw[variable]
        raw = b"\x20" + uleb(raw_index)
        if value_type is ValueType.I32:
            # Soroban I32Val: [i32 bits:32][minor:24][tag:8].
            return raw + b"\x42\x20\x87\xa7"
        if value_type is ValueType.U32:
            return raw + b"\x42\x20\x88\xa7"
        if value_type is ValueType.BOOL:
            # False and true are represented by Val tags 0 and 1.
            return raw + b"\x42\x01\x51"
        if value_type in {ValueType.I64, ValueType.U64}:
            return raw + self._decode_i64_val(value_type)
        if value_type in OBJECT_TYPES:
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
            i32_opcodes = {
                "add": 0x6A,
                "sub": 0x6B,
                "mul": 0x6C,
                "and": 0x71,
                "or": 0x72,
            }
            i64_opcodes = {"add": 0x7C, "sub": 0x7D, "mul": 0x7E}
            opcodes = i64_opcodes if node.type in {ValueType.I64, ValueType.U64} else i32_opcodes
            return self.expression(node.left) + self.expression(node.right) + bytes([opcodes[node.op]])
        if isinstance(node, ir.Compare):
            operand_type = node.left.type
            if operand_type in OBJECT_TYPES:
                compared = self.expression(node.left) + self.expression(node.right) + b"\x10" + uleb(OBJ_CMP)
                return compared + b"\x50" + (b"" if node.op == "eq" else b"\x45")
            i32_opcodes = {
                "eq": 0x46,
                "ne": 0x47,
                "lt": 0x48,
                "gt": 0x4A,
                "le": 0x4C,
                "ge": 0x4E,
            }
            if operand_type is ValueType.U32:
                i32_opcodes.update({"lt": 0x49, "gt": 0x4B, "le": 0x4D, "ge": 0x4F})
            i64_opcodes = {"eq": 0x51, "ne": 0x52, "lt": 0x53, "gt": 0x55, "le": 0x57, "ge": 0x59}
            if operand_type is ValueType.U64:
                i64_opcodes.update({"lt": 0x54, "gt": 0x56, "le": 0x58, "ge": 0x5A})
            opcodes = i64_opcodes if operand_type in {ValueType.I64, ValueType.U64} else i32_opcodes
            return self.expression(node.left) + self.expression(node.right) + bytes([opcodes[node.op]])
        if isinstance(node, ir.HostCall):
            return self.call(node)
        raise AssertionError(type(node).__name__)

    def call(self, node: ir.HostCall) -> bytes:
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
            if node.op in {"storage_get_symbol", "storage_get_string", "storage_get_bytes"}:
                return raw
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
        raise AssertionError(node.op)

    def _decode_call_result(self, value_type: ValueType) -> bytes:
        if value_type is ValueType.I32:
            return b"\x42\x20\x87\xa7"
        if value_type is ValueType.U32:
            return b"\x42\x20\x88\xa7"
        if value_type is ValueType.BOOL:
            return b"\x42\x01\x51"
        if value_type in {ValueType.I64, ValueType.U64}:
            return self._decode_i64_val(value_type)
        if value_type in OBJECT_TYPES:
            return b""
        raise AssertionError(value_type)

    @staticmethod
    def _u32_val(value: int) -> bytes:
        signed = value if value < 2**31 else value - 2**32
        return b"\x41" + sleb(signed, 32) + FunctionEmitter.encode_val(ValueType.U32)

    @staticmethod
    def encode_val(value_type: ValueType) -> bytes:
        if value_type is ValueType.I32:
            # Preserve the i32 bit pattern, shift it into Val.major, add tag 5.
            return b"\xad\x42\x20\x86\x42" + sleb(I32_TAG) + b"\x84"
        if value_type is ValueType.U32:
            return b"\xad\x42\x20\x86\x42" + sleb(U32_TAG) + b"\x84"
        if value_type is ValueType.I64:
            return b"\x10" + uleb(OBJ_FROM_I64)
        if value_type is ValueType.U64:
            return b"\x10" + uleb(OBJ_FROM_U64)
        if value_type is ValueType.BOOL:
            return b"\xad"  # i64.extend_i32_u; tags are false=0, true=1
        if value_type in OBJECT_TYPES:
            return b""
        if value_type is ValueType.VOID:
            return b"\x42" + sleb(VOID_TAG)
        raise AssertionError(value_type)


def emit_module(contract: ir.Contract, protocol: int = 25) -> bytes:
    literals = LiteralPool(max(8, _max_linear_values(contract) * 8))
    optional_imports = []
    if _uses_host_op(contract, "vec_get"):
        optional_imports.append(("v", "1", 2))
    if _uses_host_op(contract, "vec_len"):
        optional_imports.append(("v", "3", 1))
    if _uses_host_op(contract, "contract_call"):
        optional_imports.append(CONTRACT_CALL_IMPORT)
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
            elif node.op == "contract_call":
                maximum = max(maximum, len(node.args) - 2)
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


def _contract_metadata(contract: ir.Contract) -> bytes:
    # SCMetaEntry::ScMetaV0 { key, val }, encoded as an XDR stream.
    from .xdr import u32, xdr_string
    return b"".join([
        u32(0) + xdr_string("name") + xdr_string(contract.name),
        u32(0) + xdr_string("source_lang") + xdr_string("pysoroban"),
    ])
