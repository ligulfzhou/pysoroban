import ast
import re
from typing import Dict, Iterable, List, Optional, Set

from .errors import CompileError, fail
from .model import Contract, Event, EventField, Function, Parameter, ValueType, VEC_ELEMENT_TYPES, VEC_TYPES_BY_ELEMENT


TYPE_NAMES = {
    "Address": ValueType.ADDRESS,
    "i32": ValueType.I32,
    "u32": ValueType.U32,
    "i64": ValueType.I64,
    "u64": ValueType.U64,
    "Symbol": ValueType.SYMBOL,
    "String": ValueType.STRING,
    "Bytes": ValueType.BYTES,
    "boolean": ValueType.BOOL,
    "bool": ValueType.BOOL,
    "None": ValueType.VOID,
}

CONTRACT_CALL_TYPES = {
    "call_i32": ValueType.I32,
    "call_u32": ValueType.U32,
    "call_i64": ValueType.I64,
    "call_u64": ValueType.U64,
    "call_bool": ValueType.BOOL,
    "call_address": ValueType.ADDRESS,
    "call_symbol": ValueType.SYMBOL,
    "call_string": ValueType.STRING,
    "call_bytes": ValueType.BYTES,
}


def _decorator_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _has_decorator(node, name: str) -> bool:
    return any(_decorator_name(item) == name for item in node.decorator_list)


def _integer_literal(node: ast.expr) -> Optional[int]:
    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        if isinstance(node.operand, ast.Constant) and isinstance(node.operand.value, int) and not isinstance(node.operand.value, bool):
            return -node.operand.value
    return None


def _annotation(node: Optional[ast.expr], *, allow_void: bool = False) -> ValueType:
    if node is None:
        if allow_void:
            return ValueType.VOID
        fail(node, "type annotation is required")
    if isinstance(node, ast.Name) and node.id in TYPE_NAMES:
        result = TYPE_NAMES[node.id]
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Vec":
        element = _annotation(node.slice)
        if element not in VEC_TYPES_BY_ELEMENT:
            fail(node, "unsupported Vec element type")
        result = VEC_TYPES_BY_ELEMENT[element]
    elif isinstance(node, ast.Constant) and node.value is None:
        result = ValueType.VOID
    else:
        fail(node, "unsupported contract type")
    if result is ValueType.VOID and not allow_void:
        fail(node, "None is not valid here")
    return result


def _event_annotation(node: ast.expr):
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Topic":
        return _annotation(node.slice), True
    return _annotation(node), False


def _snake_case(name: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def _parse_events(module: ast.Module) -> List[Event]:
    events: List[Event] = []
    names: Set[str] = set()
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or not _has_decorator(node, "event"):
            continue
        if node.name in names:
            fail(node, f"duplicate event {node.name!r}")
        names.add(node.name)
        prefix = _snake_case(node.name)
        raw_prefix = prefix.encode("utf-8")
        if len(raw_prefix) > 32 or not prefix or any(
            not (byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122)
            for byte in raw_prefix
        ):
            fail(node, "event names must produce a Symbol prefix of at most 32 bytes")

        fields: List[EventField] = []
        field_names: Set[str] = set()
        saw_data = False
        for child in _without_docstring(node.body):
            if isinstance(child, ast.Pass):
                continue
            if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name) or child.value is not None:
                fail(child, "event bodies may only contain annotated fields")
            field_name = child.target.id
            if field_name in field_names:
                fail(child, f"duplicate event field {field_name!r}")
            if len(field_name.encode("utf-8")) > 30:
                fail(child, "event field names are limited to 30 UTF-8 bytes")
            field_names.add(field_name)
            value_type, is_topic = _event_annotation(child.annotation)
            if is_topic and value_type in VEC_ELEMENT_TYPES:
                fail(child, "Vec values cannot be event topics")
            if is_topic and saw_data:
                fail(child, "Topic fields must appear before the event data field")
            if not is_topic:
                if saw_data:
                    fail(child, "typed events currently support exactly one data field")
                saw_data = True
            fields.append(EventField(field_name, value_type, is_topic))
        if not saw_data:
            fail(node, "typed events require exactly one data field")
        events.append(Event(node.name, prefix, tuple(fields), ast.get_docstring(node) or ""))
    return events


def parse_contract(source: str, source_name: Optional[str] = None) -> Contract:
    try:
        module = ast.parse(source, filename=source_name or "<contract>")
    except SyntaxError as exc:
        raise CompileError(exc.msg, exc.lineno, (exc.offset or 1) - 1) from exc

    classes = [
        node for node in module.body
        if isinstance(node, ast.ClassDef) and _has_decorator(node, "contract")
    ]
    if len(classes) != 1:
        raise CompileError("source must contain exactly one @contract class")
    contract_node = classes[0]

    events = _parse_events(module)
    functions: List[Function] = []
    names: Set[str] = set()
    for node in contract_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _has_decorator(node, "public"):
            continue
        if isinstance(node, ast.AsyncFunctionDef):
            fail(node, "async contract functions are not supported")
        if node.name in names:
            fail(node, f"duplicate contract function {node.name!r}")
        names.add(node.name)
        if len(node.name.encode("utf-8")) > 32:
            fail(node, "contract function names are limited to 32 UTF-8 bytes")
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.posonlyargs:
            fail(node, "variadic, keyword-only, and positional-only parameters are not supported")

        args = list(node.args.args)
        if not args or args[0].arg != "self":
            fail(node, "public methods must declare self as their first parameter")
        params = []
        for arg in args[1:]:
            if len(arg.arg.encode("utf-8")) > 30:
                fail(arg, "parameter names are limited to 30 UTF-8 bytes")
            params.append(Parameter(arg.arg, _annotation(arg.annotation)))
        if node.args.defaults:
            fail(node, "default parameter values are not supported")
        result = _annotation(node.returns, allow_void=True)
        functions.append(Function(node.name, tuple(params), result, node, ast.get_docstring(node) or ""))

    if not functions:
        fail(contract_node, "contract must contain at least one @public method")

    contract = Contract(
        name=contract_node.name,
        functions=tuple(functions),
        events=tuple(events),
        source_name=source_name,
    )
    TypeChecker(contract).check()
    return contract


class TypeChecker:
    def __init__(self, contract: Contract):
        self.contract = contract
        self.function: Optional[Function] = None
        self.variables: Dict[str, ValueType] = {}
        self.events = {event.name: event for event in contract.events}

    def check(self):
        for function in self.contract.functions:
            self.function = function
            self.variables = {param.name: param.type for param in function.params}
            body = _without_docstring(function.node.body)
            for statement in body:
                self.check_statement(statement)
            if function.result is not ValueType.VOID and not _always_returns(body):
                fail(function.node, f"function {function.name!r} does not return on every path")

    def check_statement(self, node: ast.stmt):
        if isinstance(node, ast.Return):
            actual = ValueType.VOID if node.value is None else self.check_expr(node.value)
            if actual is not self.function.result:
                fail(node, f"expected return type {self.function.result.value}, got {actual.value}")
            return
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.value is None:
                fail(node, "annotated assignments require a simple name and value")
            declared = _annotation(node.annotation)
            actual = self.check_expr(node.value)
            if declared is not actual:
                fail(node, f"cannot assign {actual.value} to {declared.value}")
            self._bind(node.target, declared)
            return
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                fail(node, "only simple single-target assignments are supported")
            actual = self.check_expr(node.value)
            target = node.targets[0]
            if target.id in self.variables and self.variables[target.id] is not actual:
                fail(node, f"cannot change type of {target.id!r}")
            self._bind(target, actual)
            return
        if isinstance(node, ast.If):
            if self.check_expr(node.test) is not ValueType.BOOL:
                fail(node.test, "if condition must be boolean")
            before = dict(self.variables)
            for child in node.body:
                self.check_statement(child)
            body_vars = dict(self.variables)
            self.variables = dict(before)
            for child in node.orelse:
                self.check_statement(child)
            else_vars = dict(self.variables)
            for name in set(body_vars) & set(else_vars):
                if body_vars[name] is else_vars[name]:
                    self.variables[name] = body_vars[name]
            return
        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name):
                fail(node.target, "for loop targets must be simple names")
            if node.orelse:
                fail(node, "for/else is not supported")
            start, stop = self._check_range(node.iter)
            before = dict(self.variables)
            if node.target.id in before and before[node.target.id] is not ValueType.I32:
                fail(node.target, "range loop variables must be i32")
            self.variables[node.target.id] = ValueType.I32
            for child in node.body:
                self.check_statement(child)
            new_names = set(self.variables) - set(before) - {node.target.id}
            if new_names:
                fail(node, "variables assigned inside a loop must be declared before the loop")
            self.variables = before
            return
        if isinstance(node, ast.Pass):
            return
        if isinstance(node, ast.Expr):
            if self.check_expr(node.value) is not ValueType.VOID:
                fail(node, "expression statements must return None")
            return
        fail(node, f"unsupported statement: {type(node).__name__}")

    def _bind(self, node: ast.Name, value_type: ValueType):
        if node.id == "self":
            fail(node, "self cannot be assigned")
        self.variables[node.id] = value_type

    def check_expr(self, node: ast.expr) -> ValueType:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return ValueType.BOOL
            if isinstance(node.value, int) and -(2**31) <= node.value < 2**31:
                return ValueType.I32
            fail(node, "only boolean and signed 32-bit integer constants are supported")
        if isinstance(node, ast.Name):
            if node.id not in self.variables:
                fail(node, f"unknown variable {node.id!r}")
            return self.variables[node.id]
        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name) or node.value.id not in self.variables:
                fail(node, "vector indexing requires a Vec variable")
            vector_type = self.variables[node.value.id]
            if vector_type not in VEC_ELEMENT_TYPES:
                fail(node.value, "only Vec values can be indexed")
            if isinstance(node.slice, ast.Slice):
                fail(node.slice, "Vec slicing is not supported yet")
            if self.check_expr(node.slice) is not ValueType.I32:
                fail(node.slice, "Vec indices must be i32")
            return VEC_ELEMENT_TYPES[vector_type]
        if isinstance(node, ast.UnaryOp):
            operand = self.check_expr(node.operand)
            if isinstance(node.op, ast.USub) and operand in {ValueType.I32, ValueType.I64}:
                return operand
            if isinstance(node.op, ast.Not) and operand is ValueType.BOOL:
                return ValueType.BOOL
            fail(node, "invalid unary operator for operand type")
        if isinstance(node, ast.BinOp):
            left, right = self.check_expr(node.left), self.check_expr(node.right)
            if left is not right or left not in {
                ValueType.I32, ValueType.U32, ValueType.I64, ValueType.U64
            }:
                fail(node, "arithmetic operands must have the same numeric type")
            if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
                fail(node, "supported arithmetic operators are +, -, and *")
            return left
        if isinstance(node, ast.BoolOp):
            if not all(self.check_expr(value) is ValueType.BOOL for value in node.values):
                fail(node, "and/or operands must be boolean")
            return ValueType.BOOL
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                fail(node, "chained comparisons are not supported yet")
            left, right = self.check_expr(node.left), self.check_expr(node.comparators[0])
            if left is not right:
                fail(node, "comparison operands must have the same type")
            if left not in {ValueType.I32, ValueType.U32, ValueType.I64, ValueType.U64} and not isinstance(
                node.ops[0], (ast.Eq, ast.NotEq)
            ):
                fail(node, f"{left.value} only supports == and !=")
            return ValueType.BOOL
        if isinstance(node, ast.Call):
            return self._check_call(node)
        fail(node, f"unsupported expression: {type(node).__name__}")

    def _check_call(self, node: ast.Call) -> ValueType:
        if node.keywords:
            fail(node, "keyword arguments are not supported")
        path = _attribute_path(node.func)
        if path == ["len"]:
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
                fail(node, "len() requires one Vec variable")
            value_type = self.variables.get(node.args[0].id)
            if value_type not in VEC_ELEMENT_TYPES:
                fail(node.args[0], "len() is only supported for Vec values")
            return ValueType.I32
        if len(path) == 1 and path[0] in {"i32", "u32", "i64", "u64"}:
            value = _integer_literal(node.args[0]) if len(node.args) == 1 else None
            if value is None:
                fail(node, f"{path[0]}() requires one integer literal")
            bounds = {
                "i32": (-(2**31), 2**31 - 1),
                "u32": (0, 2**32 - 1),
                "i64": (-(2**63), 2**63 - 1),
                "u64": (0, 2**64 - 1),
            }
            lower, upper = bounds[path[0]]
            if not lower <= value <= upper:
                fail(node.args[0], f"literal is outside the {path[0]} range")
            return TYPE_NAMES[path[0]]
        if len(path) == 1 and path[0] in {"Symbol", "String", "Bytes"}:
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                fail(node, f"{path[0]}() requires one literal")
            value = node.args[0].value
            expected = bytes if path[0] == "Bytes" else str
            if not isinstance(value, expected):
                fail(node.args[0], f"{path[0]}() requires a {expected.__name__} literal")
            if path[0] == "Symbol":
                raw = value.encode("utf-8")
                if len(raw) > 32 or any(not (byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122) for byte in raw):
                    fail(node.args[0], "Symbol literals must be at most 32 bytes using only [a-zA-Z0-9_]")
            return TYPE_NAMES[path[0]]
        if len(path) == 2 and path[1] == "require_auth":
            owner = path[0]
            if owner not in self.variables or self.variables[owner] is not ValueType.ADDRESS:
                fail(node, "require_auth() is only available on Address values")
            if node.args:
                fail(node, "require_auth() takes no arguments")
            return ValueType.VOID
        if len(path) == 2 and path[1] in CONTRACT_CALL_TYPES:
            target = path[0]
            if target not in self.variables or self.variables[target] is not ValueType.ADDRESS:
                fail(node, "cross-contract calls are only available on Address values")
            if not node.args:
                fail(node, f"{path[1]}() requires a Symbol function name")
            if self.check_expr(node.args[0]) is not ValueType.SYMBOL:
                fail(node.args[0], "cross-contract function name must be a Symbol")
            for argument in node.args[1:]:
                if self.check_expr(argument) is ValueType.VOID:
                    fail(argument, "cross-contract arguments cannot be None")
            return CONTRACT_CALL_TYPES[path[1]]
        if path[:2] == ["storage", "instance"] and len(path) == 3:
            method = path[2]
            getters = {
                "get_i32": ValueType.I32,
                "get_u32": ValueType.U32,
                "get_i64": ValueType.I64,
                "get_u64": ValueType.U64,
                "get_bool": ValueType.BOOL,
                "get_symbol": ValueType.SYMBOL,
                "get_string": ValueType.STRING,
                "get_bytes": ValueType.BYTES,
            }
            if method in set(getters) | {"has"}:
                if len(node.args) != 1:
                    fail(node, f"storage.instance.{method}() takes one key")
                self._check_storage_value(node.args[0])
                return ValueType.BOOL if method == "has" else getters[method]
            if method == "set":
                if len(node.args) != 2:
                    fail(node, "storage.instance.set() takes a key and value")
                self._check_storage_value(node.args[0])
                self._check_storage_value(node.args[1])
                return ValueType.VOID
        if path == ["events", "publish"]:
            if len(node.args) == 1 and isinstance(node.args[0], ast.Call):
                constructor = node.args[0]
                event_path = _attribute_path(constructor.func)
                event = self.events.get(event_path[0]) if len(event_path) == 1 else None
                if event is None:
                    fail(constructor, "events.publish() requires a declared @event value")
                if constructor.keywords:
                    fail(constructor, "event constructors do not support keyword arguments")
                if len(constructor.args) != len(event.fields):
                    fail(constructor, f"{event.name}() expects {len(event.fields)} arguments, got {len(constructor.args)}")
                for field, value in zip(event.fields, constructor.args):
                    actual = self.check_expr(value)
                    if actual is not field.type:
                        fail(value, f"event field {field.name!r} expects {field.type.value}, got {actual.value}")
                return ValueType.VOID
            if len(node.args) != 2:
                fail(node, "events.publish() takes an @event value, or one Symbol topic and one data value")
            if self.check_expr(node.args[0]) is not ValueType.SYMBOL:
                fail(node.args[0], "event topic must be a Symbol")
            if self.check_expr(node.args[1]) is ValueType.VOID:
                fail(node.args[1], "event data cannot be None")
            return ValueType.VOID
        fail(node, "unsupported function or method call")

    def _check_storage_value(self, node: ast.expr):
        value_type = self.check_expr(node)
        if value_type is ValueType.VOID:
            fail(node, "unsupported storage key or value type")

    def _check_range(self, node: ast.expr):
        if not isinstance(node, ast.Call) or _attribute_path(node.func) != ["range"] or node.keywords:
            fail(node, "for loops require range(stop) or range(start, stop)")
        if len(node.args) == 1:
            start, stop = ast.Constant(value=0), node.args[0]
        elif len(node.args) == 2:
            start, stop = node.args
        else:
            fail(node, "range() supports one or two arguments")
        if self.check_expr(start) is not ValueType.I32 or self.check_expr(stop) is not ValueType.I32:
            fail(node, "range() bounds must be i32")
        return start, stop


def assigned_names(statements: Iterable[ast.stmt]) -> List[str]:
    result: List[str] = []

    def visit(statement: ast.stmt):
        target = None
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
        elif isinstance(statement, ast.AnnAssign):
            target = statement.target
        if isinstance(target, ast.Name) and target.id not in result:
            result.append(target.id)
        if isinstance(statement, ast.If):
            for child in statement.body + statement.orelse:
                visit(child)
        if isinstance(statement, ast.For):
            for child in statement.body + statement.orelse:
                visit(child)

    for item in statements:
        visit(item)
    return result


def _attribute_path(node: ast.expr) -> List[str]:
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return list(reversed(parts))
    return []


def _without_docstring(body: List[ast.stmt]) -> List[ast.stmt]:
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str):
        return body[1:]
    return body


def function_body(function: Function) -> List[ast.stmt]:
    return _without_docstring(function.node.body)


def _always_returns(body: List[ast.stmt]) -> bool:
    for statement in body:
        if isinstance(statement, ast.Return):
            return True
        if isinstance(statement, ast.If) and statement.orelse:
            if _always_returns(statement.body) and _always_returns(statement.orelse):
                return True
    return False
