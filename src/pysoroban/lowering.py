"""Lower the checked Python AST into the typed PySoroban IR."""

import ast
from typing import Dict, List, Tuple

from . import ir
from .errors import fail
from .frontend import (
    CONTRACT_CALL_TYPES,
    _annotation,
    _attribute_path,
    _integer_literal,
    _is_fail_call,
    function_body,
)
from .model import (
    Contract,
    EnumType,
    ErrorEnum,
    Event,
    Function,
    MapType,
    Parameter,
    StructType,
    ValueType,
    is_vec_type,
    vec_element,
)


ANNOTATIONS = {
    "i32": ValueType.I32,
    "u32": ValueType.U32,
    "i64": ValueType.I64,
    "u64": ValueType.U64,
    "i128": ValueType.I128,
    "u128": ValueType.U128,
    "boolean": ValueType.BOOL,
    "bool": ValueType.BOOL,
    "Address": ValueType.ADDRESS,
    "Symbol": ValueType.SYMBOL,
    "String": ValueType.STRING,
    "Bytes": ValueType.BYTES,
}

BINARY_OPS = {
    ast.Add: "add",
    ast.Sub: "sub",
    ast.Mult: "mul",
    ast.FloorDiv: "div",
}

COMPARE_OPS = {
    ast.Eq: "eq",
    ast.NotEq: "ne",
    ast.Lt: "lt",
    ast.Gt: "gt",
    ast.LtE: "le",
    ast.GtE: "ge",
}


def lower_contract(contract: Contract) -> ir.Contract:
    return ir.Contract(
        name=contract.name,
        functions=tuple(
            FunctionLowerer(function, contract.events, contract.errors, contract.structs, contract.enums).lower()
            for function in contract.functions
        ),
        events=contract.events,
        errors=contract.errors,
        structs=contract.structs,
        enums=contract.enums,
        source_name=contract.source_name,
    )


class FunctionLowerer:
    def __init__(
        self,
        function: Function,
        events: Tuple[Event, ...] = (),
        errors: Tuple[ErrorEnum, ...] = (),
        structs: Tuple[StructType, ...] = (),
        enums: Tuple[EnumType, ...] = (),
    ):
        self.function = function
        self.events = {event.name: event for event in events}
        self.errors = {error.name: error for error in errors}
        self.structs = {item.name: item for item in structs}
        self.enums = {item.name: item for item in enums}
        self.user_types = {**self.structs, **self.enums}
        self.types: Dict[str, object] = {param.name: param.type for param in function.params}
        self.local_order: List[str] = []
        self.range_counter = 0

    def lower(self) -> ir.Function:
        body = tuple(self.statement(node) for node in function_body(self.function))
        locals_ = tuple(Parameter(name, self.types[name]) for name in self.local_order)
        return ir.Function(
            name=self.function.name,
            params=self.function.params,
            result=self.function.result,
            locals=locals_,
            body=body,
            doc=self.function.doc,
        )

    def statement(self, node: ast.stmt) -> ir.Statement:
        if isinstance(node, ast.Return):
            value = ir.Constant(None, ValueType.VOID) if node.value is None else self.expression(node.value)
            return ir.Return(value)
        if isinstance(node, ast.AnnAssign):
            value_type = _annotation(node.annotation, self.user_types)
            self._declare(node.target.id, value_type)
            if self._is_pop(node.value):
                return ir.PopBack(node.value.func.value.id, node.target.id)
            return ir.SetLocal(node.target.id, self._assigned_value(node.value, value_type))
        if isinstance(node, ast.Assign):
            if self._is_pop(node.value):
                self._declare(node.targets[0].id, vec_element(self.types[node.value.func.value.id]))
                return ir.PopBack(node.value.func.value.id, node.targets[0].id)
            value = self.expression(node.value)
            self._declare(node.targets[0].id, value.type)
            return ir.SetLocal(node.targets[0].id, value)
        if isinstance(node, ast.If):
            before = dict(self.types)
            test = self.expression(node.test)
            body = tuple(self.statement(child) for child in node.body)
            body_types = dict(self.types)
            self.types = dict(before)
            otherwise = tuple(self.statement(child) for child in node.orelse)
            otherwise_types = dict(self.types)
            self.types = dict(before)
            for name in set(body_types) & set(otherwise_types):
                if body_types[name] is otherwise_types[name]:
                    self.types[name] = body_types[name]
            return ir.If(test, body, otherwise)
        if isinstance(node, ast.For):
            args = node.iter.args
            start_node, stop_node = (ast.Constant(value=0), args[0]) if len(args) == 1 else args
            self._declare(node.target.id, ValueType.I32)
            stop_local = f"__pysoroban_range_stop_{self.range_counter}"
            self.range_counter += 1
            self._declare(stop_local, ValueType.I32)
            start = self.expression(start_node)
            stop = self.expression(stop_node)
            body = tuple(self.statement(child) for child in node.body)
            return ir.ForRange(node.target.id, start, stop, stop_local, body)
        if isinstance(node, ast.Expr):
            if _is_fail_call(node.value):
                return self._fail(node.value)
            if self._is_mutation(node.value):
                return self._mutation(node.value)
            return ir.Drop(self.expression(node.value))
        if isinstance(node, ast.Pass):
            # A no-op is represented as an empty conditional-free statement list.
            return ir.Drop(ir.Constant(None, ValueType.VOID))
        fail(node, f"cannot lower statement: {type(node).__name__}", "E9001")

    def _declare(self, name: str, value_type: ValueType):
        if name not in self.types and name not in self.local_order:
            self.local_order.append(name)
        self.types[name] = value_type

    def expression(self, node: ast.expr) -> ir.Expression:
        if isinstance(node, ast.Constant):
            value_type = ValueType.BOOL if isinstance(node.value, bool) else ValueType.I32
            return ir.Constant(node.value, value_type)
        if isinstance(node, ast.Name):
            return ir.Local(node.id, self.types[node.id])
        if isinstance(node, ast.Subscript):
            collection = ir.Local(node.value.id, self.types[node.value.id])
            if isinstance(collection.type, MapType):
                return ir.HostCall("map_get", (collection, self.expression(node.slice)), collection.type.value_type)
            return ir.HostCall("vec_get", (collection, self.expression(node.slice)), vec_element(collection.type))
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id in self.enums:
                enum = self.enums[node.value.id]
                case = next(item for item in enum.cases if item.name == node.attr)
                return ir.Constant(case.value, enum)
            owner = self.expression(node.value)
            field = next(item for item in owner.type.fields if item.name == node.attr)
            return ir.HostCall(
                "struct_field",
                (owner, ir.Constant(field.name, ValueType.SYMBOL)),
                field.type,
            )
        if isinstance(node, ast.UnaryOp):
            operand = self.expression(node.operand)
            if isinstance(node.op, ast.USub):
                return ir.Unary("neg", operand, operand.type)
            return ir.Unary("not", operand, ValueType.BOOL)
        if isinstance(node, ast.BinOp):
            left = self.expression(node.left)
            return ir.Binary(BINARY_OPS[type(node.op)], left, self.expression(node.right), left.type)
        if isinstance(node, ast.BoolOp):
            op = "and" if isinstance(node.op, ast.And) else "or"
            result = self.expression(node.values[0])
            for value in node.values[1:]:
                result = ir.Binary(op, result, self.expression(value), ValueType.BOOL)
            return result
        if isinstance(node, ast.Compare):
            return ir.Compare(
                COMPARE_OPS[type(node.ops[0])],
                self.expression(node.left),
                self.expression(node.comparators[0]),
            )
        if isinstance(node, ast.Call):
            return self.call(node)
        fail(node, f"cannot lower expression: {type(node).__name__}", "E9002")

    def call(self, node: ast.Call) -> ir.HostCall:
        path = _attribute_path(node.func)
        if path == ["len"]:
            value = node.args[0]
            collection = ir.Local(value.id, self.types[value.id])
            if isinstance(collection.type, MapType):
                op = "map_len"
            elif collection.type is ValueType.STRING:
                op = "string_len"
            elif collection.type is ValueType.BYTES:
                op = "bytes_len"
            else:
                op = "vec_len"
            return ir.HostCall(op, (collection,), ValueType.I32)
        if len(path) == 1 and path[0] in self.structs:
            struct = self.structs[path[0]]
            return ir.HostCall(
                "struct_new",
                tuple(self.expression(value) for value in node.args),
                struct,
            )
        if len(path) == 2 and path[1] == "has":
            return ir.HostCall(
                "map_has",
                (ir.Local(path[0], self.types[path[0]]), self.expression(node.args[0])),
                ValueType.BOOL,
            )
        if path == ["u128", "mul_div_floor"]:
            return ir.HostCall(
                "u128_mul_div_floor",
                tuple(self.expression(value) for value in node.args),
                ValueType.U128,
            )
        if len(path) == 1 and path[0] in ANNOTATIONS:
            value = _integer_literal(node.args[0]) if path[0] in {
                "i32", "u32", "i64", "u64", "i128", "u128"
            } else node.args[0].value
            return ir.Constant(value, ANNOTATIONS[path[0]])
        if len(path) == 2 and path[1] == "require_auth":
            return ir.HostCall("require_auth", (ir.Local(path[0], ValueType.ADDRESS),), ValueType.VOID)
        if len(path) == 2 and path[1] in CONTRACT_CALL_TYPES:
            args = (ir.Local(path[0], ValueType.ADDRESS),) + tuple(
                self.expression(value) for value in node.args
            )
            return ir.HostCall("contract_call", args, CONTRACT_CALL_TYPES[path[1]])
        if path[:1] == ["storage"] and len(path) == 3:
            return self._storage(node, path[1], path[2])
        service = self._service(node, path)
        if service is not None:
            return service
        if path == ["events", "publish"]:
            if len(node.args) == 1 and isinstance(node.args[0], ast.Call):
                constructor = node.args[0]
                event = self.events[_attribute_path(constructor.func)[0]]
                topics = [ir.Constant(event.prefix, ValueType.SYMBOL)]
                data = None
                for field, value in zip(event.fields, constructor.args):
                    lowered = self.expression(value)
                    if field.topic:
                        topics.append(lowered)
                    else:
                        data = lowered
                return ir.HostCall("event_publish", tuple(topics + [data]), ValueType.VOID)
            return ir.HostCall("event_publish", tuple(self.expression(value) for value in node.args), ValueType.VOID)
        fail(node, "cannot lower unsupported call", "E9003")

    def _assigned_value(self, node: ast.expr, declared) -> ir.Expression:
        if (
            isinstance(node, ast.Call)
            and not node.args
            and _attribute_path(node.func) in (["Vec"], ["Map"])
        ):
            op = "vec_new" if _attribute_path(node.func) == ["Vec"] else "map_new"
            return ir.HostCall(op, (), declared)
        return self.expression(node)

    def _is_pop(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.attr == "pop"
            and not node.args
            and is_vec_type(self.types.get(node.func.value.id))
        )

    def _is_mutation(self, node: ast.expr) -> bool:
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            return False
        if not isinstance(node.func.value, ast.Name):
            return False
        value_type = self.types.get(node.func.value.id)
        if is_vec_type(value_type) and node.func.attr in {"push", "set", "insert", "remove"}:
            return True
        if value_type is ValueType.BYTES and node.func.attr == "append":
            return True
        return isinstance(value_type, MapType) and node.func.attr in {"set", "remove"}

    def _mutation(self, node: ast.Call) -> ir.SetLocal:
        name = node.func.value.id
        value_type = self.types[name]
        local = ir.Local(name, value_type)
        method = node.func.attr
        args = tuple(self.expression(value) for value in node.args)
        if is_vec_type(value_type):
            op = {"push": "vec_push", "set": "vec_put", "insert": "vec_insert", "remove": "vec_del"}[method]
        elif value_type is ValueType.BYTES:
            op = "bytes_append"
        else:
            op = "map_put" if method == "set" else "map_del"
        return ir.SetLocal(name, ir.HostCall(op, (local,) + args, value_type))

    def _storage(self, node: ast.Call, tier: str, method: str) -> ir.HostCall:
        legacy = {
            "set": ("storage_set", ValueType.VOID),
            "has": ("storage_has", ValueType.BOOL),
            "get_i32": ("storage_get_i32", ValueType.I32),
            "get_u32": ("storage_get_u32", ValueType.U32),
            "get_i64": ("storage_get_i64", ValueType.I64),
            "get_u64": ("storage_get_u64", ValueType.U64),
            "get_i128": ("storage_get_i128", ValueType.I128),
            "get_u128": ("storage_get_u128", ValueType.U128),
            "get_bool": ("storage_get_bool", ValueType.BOOL),
            "get_symbol": ("storage_get_symbol", ValueType.SYMBOL),
            "get_string": ("storage_get_string", ValueType.STRING),
            "get_bytes": ("storage_get_bytes", ValueType.BYTES),
        }
        prefix = {"instance": "storage", "persistent": "pstorage", "temporary": "tstorage"}[tier]
        if tier == "instance" and method in legacy:
            op, result = legacy[method]
            return ir.HostCall(op, tuple(self.expression(value) for value in node.args), result)
        if method == "extend_ttl" and tier == "instance":
            return ir.HostCall(
                "extend_instance",
                tuple(self.expression(value) for value in node.args),
                ValueType.VOID,
            )
        if method == "extend_ttl":
            return ir.HostCall(
                f"{prefix}_extend",
                tuple(self.expression(value) for value in node.args),
                ValueType.VOID,
            )
        if method == "set":
            return ir.HostCall(f"{prefix}_set", tuple(self.expression(value) for value in node.args), ValueType.VOID)
        if method == "has":
            return ir.HostCall(f"{prefix}_has", (self.expression(node.args[0]),), ValueType.BOOL)
        if method == "remove":
            return ir.HostCall(f"{prefix}_del", (self.expression(node.args[0]),), ValueType.VOID)
        getters = {
            "get_i32": ValueType.I32,
            "get_u32": ValueType.U32,
            "get_i64": ValueType.I64,
            "get_u64": ValueType.U64,
            "get_i128": ValueType.I128,
            "get_u128": ValueType.U128,
            "get_bool": ValueType.BOOL,
            "get_symbol": ValueType.SYMBOL,
            "get_string": ValueType.STRING,
            "get_bytes": ValueType.BYTES,
            "get_address": ValueType.ADDRESS,
        }
        if method == "get":
            result = _annotation(node.args[1], self.user_types)
            return ir.HostCall(f"{prefix}_get", (self.expression(node.args[0]),), result)
        return ir.HostCall(f"{prefix}_get", (self.expression(node.args[0]),), getters[method])

    def _service(self, node: ast.Call, path):
        operations = {
            ("ledger", "sequence"): ("ledger_sequence", ValueType.U32),
            ("ledger", "timestamp"): ("ledger_timestamp", ValueType.U64),
            ("ledger", "version"): ("ledger_version", ValueType.U32),
            ("ledger", "network_id"): ("ledger_network", ValueType.BYTES),
            ("env", "current_contract_address"): ("current_contract", ValueType.ADDRESS),
            ("crypto", "sha256"): ("sha256", ValueType.BYTES),
            ("crypto", "keccak256"): ("keccak256", ValueType.BYTES),
            ("crypto", "ed25519_verify"): ("ed25519_verify", ValueType.VOID),
            ("log",): ("log", ValueType.VOID),
            ("prng", "bytes"): ("prng_bytes", ValueType.BYTES),
            ("prng", "u64"): ("prng_u64", ValueType.U64),
            ("deploy", "contract"): ("deploy", ValueType.ADDRESS),
            ("deploy", "with_constructor"): ("deploy_constructor", ValueType.ADDRESS),
            ("deploy", "upload"): ("upload_wasm", ValueType.BYTES),
            ("deploy", "upgrade"): ("upgrade", ValueType.VOID),
            ("deploy", "asset"): ("deploy_asset", ValueType.ADDRESS),
        }
        if tuple(path) in operations:
            op, result = operations[tuple(path)]
            args = tuple(self.expression(value) for value in node.args)
            return ir.HostCall(op, args, result)
        if len(path) == 2 and path[1] == "require_auth_for":
            args = tuple(self.expression(value) for value in node.args)
            return ir.HostCall(
                "require_auth_for",
                (ir.Local(path[0], ValueType.ADDRESS),) + args,
                ValueType.VOID,
            )
        if len(path) == 2 and path[1] in {"to_bytes", "to_string", "slice"}:
            owner = ir.Local(path[0], self.types[path[0]])
            result = {
                "to_bytes": ValueType.BYTES,
                "to_string": ValueType.STRING,
                "slice": ValueType.BYTES,
            }[path[1]]
            op = {"to_bytes": "string_to_bytes", "to_string": "bytes_to_string", "slice": "bytes_slice"}[path[1]]
            args = tuple(self.expression(value) for value in node.args)
            return ir.HostCall(op, (owner,) + args, result)
        return None

    def _fail(self, node: ast.Call) -> ir.Fail:
        error_name, case_name = _attribute_path(node.args[0])
        error = self.errors[error_name]
        case = next(item for item in error.cases if item.name == case_name)
        return ir.Fail(case.value, error.name, case.name)
