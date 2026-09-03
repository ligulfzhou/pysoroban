"""Lower the checked Python AST into the typed PySoroban IR."""

import ast
from typing import Dict, List, Tuple

from . import ir
from .errors import fail
from .frontend import CONTRACT_CALL_TYPES, _attribute_path, _integer_literal, function_body
from .model import Contract, Event, Function, Parameter, ValueType, VEC_ELEMENT_TYPES


ANNOTATIONS = {
    "i32": ValueType.I32,
    "u32": ValueType.U32,
    "i64": ValueType.I64,
    "u64": ValueType.U64,
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
        functions=tuple(FunctionLowerer(function, contract.events).lower() for function in contract.functions),
        events=contract.events,
        source_name=contract.source_name,
    )


class FunctionLowerer:
    def __init__(self, function: Function, events: Tuple[Event, ...] = ()):
        self.function = function
        self.events = {event.name: event for event in events}
        self.types: Dict[str, ValueType] = {param.name: param.type for param in function.params}
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
            value_type = ANNOTATIONS[node.annotation.id]
            self._declare(node.target.id, value_type)
            return ir.SetLocal(node.target.id, self.expression(node.value))
        if isinstance(node, ast.Assign):
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
            return ir.Drop(self.expression(node.value))
        if isinstance(node, ast.Pass):
            # A no-op is represented as an empty conditional-free statement list.
            return ir.Drop(ir.Constant(None, ValueType.VOID))
        fail(node, f"cannot lower statement: {type(node).__name__}")

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
            vector = ir.Local(node.value.id, self.types[node.value.id])
            return ir.HostCall("vec_get", (vector, self.expression(node.slice)), VEC_ELEMENT_TYPES[vector.type])
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
        fail(node, f"cannot lower expression: {type(node).__name__}")

    def call(self, node: ast.Call) -> ir.HostCall:
        path = _attribute_path(node.func)
        if path == ["len"]:
            value = node.args[0]
            return ir.HostCall("vec_len", (ir.Local(value.id, self.types[value.id]),), ValueType.I32)
        if len(path) == 1 and path[0] in ANNOTATIONS:
            value = _integer_literal(node.args[0]) if path[0] in {"i32", "u32", "i64", "u64"} else node.args[0].value
            return ir.Constant(value, ANNOTATIONS[path[0]])
        if len(path) == 2 and path[1] == "require_auth":
            return ir.HostCall("require_auth", (ir.Local(path[0], ValueType.ADDRESS),), ValueType.VOID)
        if len(path) == 2 and path[1] in CONTRACT_CALL_TYPES:
            args = (ir.Local(path[0], ValueType.ADDRESS),) + tuple(
                self.expression(value) for value in node.args
            )
            return ir.HostCall("contract_call", args, CONTRACT_CALL_TYPES[path[1]])
        if path[:2] == ["storage", "instance"]:
            method = path[2]
            args = tuple(self.expression(value) for value in node.args)
            operations = {
                "set": ("storage_set", ValueType.VOID),
                "has": ("storage_has", ValueType.BOOL),
                "get_i32": ("storage_get_i32", ValueType.I32),
                "get_u32": ("storage_get_u32", ValueType.U32),
                "get_i64": ("storage_get_i64", ValueType.I64),
                "get_u64": ("storage_get_u64", ValueType.U64),
                "get_bool": ("storage_get_bool", ValueType.BOOL),
                "get_symbol": ("storage_get_symbol", ValueType.SYMBOL),
                "get_string": ("storage_get_string", ValueType.STRING),
                "get_bytes": ("storage_get_bytes", ValueType.BYTES),
            }
            op, result = operations[method]
            return ir.HostCall(op, args, result)
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
        fail(node, "cannot lower unsupported call")
