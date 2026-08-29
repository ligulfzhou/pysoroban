import ast
from typing import Dict, Iterable, List, Optional, Set

from .errors import CompileError, fail
from .model import Contract, Function, Parameter, ValueType


TYPE_NAMES = {
    "Address": ValueType.ADDRESS,
    "i32": ValueType.I32,
    "boolean": ValueType.BOOL,
    "bool": ValueType.BOOL,
    "None": ValueType.VOID,
}


def _decorator_name(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    return None


def _has_decorator(node, name: str) -> bool:
    return any(_decorator_name(item) == name for item in node.decorator_list)


def _annotation(node: Optional[ast.expr], *, allow_void: bool = False) -> ValueType:
    if node is None:
        if allow_void:
            return ValueType.VOID
        fail(node, "type annotation is required")
    if isinstance(node, ast.Name) and node.id in TYPE_NAMES:
        result = TYPE_NAMES[node.id]
    elif isinstance(node, ast.Constant) and node.value is None:
        result = ValueType.VOID
    else:
        fail(node, "supported types are i32, boolean, and None")
    if result is ValueType.VOID and not allow_void:
        fail(node, "None is not valid here")
    return result


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

    contract = Contract(contract_node.name, tuple(functions), source_name)
    TypeChecker(contract).check()
    return contract


class TypeChecker:
    def __init__(self, contract: Contract):
        self.contract = contract
        self.function: Optional[Function] = None
        self.variables: Dict[str, ValueType] = {}

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
        if isinstance(node, ast.UnaryOp):
            operand = self.check_expr(node.operand)
            if isinstance(node.op, ast.USub) and operand is ValueType.I32:
                return ValueType.I32
            if isinstance(node.op, ast.Not) and operand is ValueType.BOOL:
                return ValueType.BOOL
            fail(node, "invalid unary operator for operand type")
        if isinstance(node, ast.BinOp):
            left, right = self.check_expr(node.left), self.check_expr(node.right)
            if left is not ValueType.I32 or right is not ValueType.I32:
                fail(node, "arithmetic operands must be i32")
            if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
                fail(node, "supported arithmetic operators are +, -, and *")
            return ValueType.I32
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
            if left is ValueType.BOOL and not isinstance(node.ops[0], (ast.Eq, ast.NotEq)):
                fail(node, "booleans only support == and !=")
            return ValueType.BOOL
        if isinstance(node, ast.Call):
            return self._check_call(node)
        fail(node, f"unsupported expression: {type(node).__name__}")

    def _check_call(self, node: ast.Call) -> ValueType:
        if node.keywords:
            fail(node, "keyword arguments are not supported")
        path = _attribute_path(node.func)
        if len(path) == 2 and path[1] == "require_auth":
            owner = path[0]
            if owner not in self.variables or self.variables[owner] is not ValueType.ADDRESS:
                fail(node, "require_auth() is only available on Address values")
            if node.args:
                fail(node, "require_auth() takes no arguments")
            return ValueType.VOID
        if path[:2] == ["storage", "instance"] and len(path) == 3:
            method = path[2]
            if method in {"get_i32", "get_bool", "has"}:
                if len(node.args) != 1:
                    fail(node, f"storage.instance.{method}() takes one key")
                self._check_storage_value(node.args[0])
                return {
                    "get_i32": ValueType.I32,
                    "get_bool": ValueType.BOOL,
                    "has": ValueType.BOOL,
                }[method]
            if method == "set":
                if len(node.args) != 2:
                    fail(node, "storage.instance.set() takes a key and value")
                self._check_storage_value(node.args[0])
                self._check_storage_value(node.args[1])
                return ValueType.VOID
        fail(node, "unsupported function or method call")

    def _check_storage_value(self, node: ast.expr):
        value_type = self.check_expr(node)
        if value_type not in {ValueType.I32, ValueType.BOOL, ValueType.ADDRESS}:
            fail(node, "unsupported storage key or value type")


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
