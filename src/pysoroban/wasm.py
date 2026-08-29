import ast
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from .errors import fail
from .frontend import _attribute_path, assigned_names, function_body
from .model import Contract, Function, ValueType
from .xdr import contract_spec, environment_metadata


I32_TAG = 5
VOID_TAG = 2
INSTANCE_STORAGE = 2

# Names and indices are the protocol-25 env.json interface. Every imported
# argument and result is directly marshalled through the Wasm i64 ABI.
HOST_IMPORTS = (
    ("l", "_", 3),  # put_contract_data
    ("l", "0", 2),  # has_contract_data
    ("l", "1", 2),  # get_contract_data
    ("a", "0", 1),  # require_auth
)
PUT_CONTRACT_DATA = 0
HAS_CONTRACT_DATA = 1
GET_CONTRACT_DATA = 2
REQUIRE_AUTH = 3


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


class FunctionEmitter:
    def __init__(self, function: Function):
        self.function = function
        self.locals = self._allocate_locals()

    def _allocate_locals(self) -> Locals:
        param_raw = {param.name: index for index, param in enumerate(self.function.params)}
        names = [param.name for param in self.function.params]
        for item in assigned_names(function_body(self.function)):
            if item not in names:
                names.append(item)
        native = {}
        types = {param.name: param.type for param in self.function.params}
        self._infer_statement_types(function_body(self.function), types)
        first_local = len(self.function.params)
        for offset, item in enumerate(names):
            native[item] = first_local + offset
        local_types = [0x7E if types[item] is ValueType.ADDRESS else 0x7F for item in names]
        return Locals(param_raw, native, types, local_types)

    def _infer_statement_types(self, statements, types):
        for node in statements:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                types[node.target.id] = {
                    "i32": ValueType.I32,
                    "boolean": ValueType.BOOL,
                    "bool": ValueType.BOOL,
                    "Address": ValueType.ADDRESS,
                }[node.annotation.id]
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                types[node.targets[0].id] = self._infer_expr_type(node.value, types)
            elif isinstance(node, ast.If):
                self._infer_statement_types(node.body, types)
                self._infer_statement_types(node.orelse, types)

    def _infer_expr_type(self, node, types):
        if isinstance(node, ast.Name):
            return types[node.id]
        if isinstance(node, ast.Constant):
            return ValueType.BOOL if isinstance(node.value, bool) else ValueType.I32
        if isinstance(node, (ast.Compare, ast.BoolOp)):
            return ValueType.BOOL
        if isinstance(node, ast.Call):
            path = _attribute_path(node.func)
            if path[-1:] == ["get_i32"]:
                return ValueType.I32
            if path[-1:] in (["get_bool"], ["has"]):
                return ValueType.BOOL
        return ValueType.I32

    def emit(self) -> bytes:
        code = bytearray()
        for param in self.function.params:
            code += self._decode_param(param.name, param.type)
            code += b"\x21" + uleb(self.locals.native[param.name])  # local.set
        for statement in function_body(self.function):
            code += self.statement(statement)
        if self.function.result is ValueType.VOID:
            code += b"\x42" + sleb(VOID_TAG)  # i64.const void Val
        code += b"\x0b"

        local_decls = [uleb(1) + bytes([value_type]) for value_type in self.locals.local_types]
        body = vector(local_decls) + code
        return uleb(len(body)) + body

    def _decode_param(self, variable: str, value_type: ValueType) -> bytes:
        raw_index = self.locals.param_raw[variable]
        if value_type is ValueType.I32:
            # Soroban I32Val: [i32 bits:32][minor:24][tag:8].
            return b"\x20" + uleb(raw_index) + b"\x42\x20\x87\xa7"
        if value_type is ValueType.BOOL:
            # False and true are represented by Val tags 0 and 1.
            return b"\x20" + uleb(raw_index) + b"\x42\x01\x51"
        if value_type is ValueType.ADDRESS:
            return b"\x20" + uleb(raw_index)
        raise AssertionError(value_type)

    def statement(self, node: ast.stmt) -> bytes:
        if isinstance(node, ast.Return):
            if node.value is None:
                return b"\x42" + sleb(VOID_TAG) + b"\x0f"
            result_type = self.expr_type(node.value)
            return self.expression(node.value) + self.encode_val(result_type) + b"\x0f"
        if isinstance(node, ast.Assign):
            target = node.targets[0]
            value_type = self.expr_type(node.value)
            self.locals.types[target.id] = value_type
            return self.expression(node.value) + b"\x21" + uleb(self.locals.native[target.id])
        if isinstance(node, ast.AnnAssign):
            value_type = self.expr_type(node.value)
            self.locals.types[node.target.id] = value_type
            return self.expression(node.value) + b"\x21" + uleb(self.locals.native[node.target.id])
        if isinstance(node, ast.If):
            output = bytearray(self.expression(node.test))
            output += b"\x04\x40"  # if, empty block type
            for child in node.body:
                output += self.statement(child)
            if node.orelse:
                output += b"\x05"
                for child in node.orelse:
                    output += self.statement(child)
            output += b"\x0b"
            return bytes(output)
        if isinstance(node, ast.Pass):
            return b""
        if isinstance(node, ast.Expr):
            return self.expression(node.value) + b"\x1a"  # drop Void Val
        fail(node, f"unsupported statement: {type(node).__name__}")

    def expression(self, node: ast.expr) -> bytes:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return b"\x41" + sleb(1 if node.value else 0, 32)
            return b"\x41" + sleb(node.value, 32)
        if isinstance(node, ast.Name):
            return b"\x20" + uleb(self.locals.native[node.id])
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.USub):
                return b"\x41\x00" + self.expression(node.operand) + b"\x6b"
            if isinstance(node.op, ast.Not):
                return self.expression(node.operand) + b"\x45"
        if isinstance(node, ast.BinOp):
            opcodes = {
                ast.Add: 0x6A,
                ast.Sub: 0x6B,
                ast.Mult: 0x6C,
            }
            return self.expression(node.left) + self.expression(node.right) + bytes([opcodes[type(node.op)]])
        if isinstance(node, ast.BoolOp):
            opcode = b"\x71" if isinstance(node.op, ast.And) else b"\x72"
            result = self.expression(node.values[0])
            for value in node.values[1:]:
                result += self.expression(value) + opcode
            return result
        if isinstance(node, ast.Compare):
            opcodes = {
                ast.Eq: 0x46,
                ast.NotEq: 0x47,
                ast.Lt: 0x48,
                ast.Gt: 0x4A,
                ast.LtE: 0x4C,
                ast.GtE: 0x4E,
            }
            return self.expression(node.left) + self.expression(node.comparators[0]) + bytes([opcodes[type(node.ops[0])]])
        if isinstance(node, ast.Call):
            return self.call(node)
        fail(node, f"unsupported expression: {type(node).__name__}")

    def call(self, node: ast.Call) -> bytes:
        path = _attribute_path(node.func)
        if len(path) == 2 and path[1] == "require_auth":
            return self.expression(ast.Name(id=path[0])) + b"\x10" + uleb(REQUIRE_AUTH)
        if path[:2] == ["storage", "instance"]:
            method = path[2]
            if method == "set":
                key, value = node.args
                return (
                    self.expression(key) + self.encode_val(self.expr_type(key))
                    + self.expression(value) + self.encode_val(self.expr_type(value))
                    + b"\x42" + sleb(INSTANCE_STORAGE)
                    + b"\x10" + uleb(PUT_CONTRACT_DATA)
                )
            key = node.args[0]
            prefix = (
                self.expression(key) + self.encode_val(self.expr_type(key))
                + b"\x42" + sleb(INSTANCE_STORAGE)
            )
            if method == "has":
                return prefix + b"\x10" + uleb(HAS_CONTRACT_DATA) + b"\x42\x01\x51"
            raw = prefix + b"\x10" + uleb(GET_CONTRACT_DATA)
            if method == "get_i32":
                return raw + b"\x42\x20\x87\xa7"
            if method == "get_bool":
                return raw + b"\x42\x01\x51"
        fail(node, "unsupported function or method call")

    def expr_type(self, node: ast.expr) -> ValueType:
        if isinstance(node, ast.Constant):
            return ValueType.BOOL if isinstance(node.value, bool) else ValueType.I32
        if isinstance(node, ast.Name):
            return self.locals.types[node.id]
        if isinstance(node, ast.Call):
            path = _attribute_path(node.func)
            if path[-1:] == ["get_i32"]:
                return ValueType.I32
            if path[-1:] in (["get_bool"], ["has"]):
                return ValueType.BOOL
            return ValueType.VOID
        if isinstance(node, (ast.Compare, ast.BoolOp)):
            return ValueType.BOOL
        if isinstance(node, ast.UnaryOp):
            return ValueType.BOOL if isinstance(node.op, ast.Not) else ValueType.I32
        return ValueType.I32

    @staticmethod
    def encode_val(value_type: ValueType) -> bytes:
        if value_type is ValueType.I32:
            # Preserve the i32 bit pattern, shift it into Val.major, add tag 5.
            return b"\xad\x42\x20\x86\x42" + sleb(I32_TAG) + b"\x84"
        if value_type is ValueType.BOOL:
            return b"\xad"  # i64.extend_i32_u; tags are false=0, true=1
        if value_type is ValueType.ADDRESS:
            return b""
        if value_type is ValueType.VOID:
            return b"\x42" + sleb(VOID_TAG)
        raise AssertionError(value_type)


def emit_module(contract: Contract, protocol: int = 25) -> bytes:
    emitters = [FunctionEmitter(function) for function in contract.functions]

    # Every exported Soroban function receives and returns 64-bit Val values.
    type_entries = []
    signature_indices: Dict[Tuple[int, int], int] = {}
    for _, _, arity in HOST_IMPORTS:
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
        for module, field, arity in HOST_IMPORTS
    ]
    exports = [
        name(fn.name) + b"\x00" + uleb(len(HOST_IMPORTS) + index)
        for index, fn in enumerate(contract.functions)
    ]
    code_section = vector([emitter.emit() for emitter in emitters])

    return b"".join([
        b"\x00asm\x01\x00\x00\x00",
        custom_section("contractenvmetav0", environment_metadata(protocol)),
        custom_section("contractspecv0", contract_spec(contract)),
        custom_section("contractmetav0", _contract_metadata(contract)),
        section(1, vector(type_entries)),
        section(2, vector(imports)),
        section(3, function_section),
        section(7, vector(exports)),
        section(10, code_section),
    ])


def _contract_metadata(contract: Contract) -> bytes:
    # SCMetaEntry::ScMetaV0 { key, val }, encoded as an XDR stream.
    from .xdr import u32, xdr_string
    return b"".join([
        u32(0) + xdr_string("name") + xdr_string(contract.name),
        u32(0) + xdr_string("source_lang") + xdr_string("pysoroban"),
    ])
