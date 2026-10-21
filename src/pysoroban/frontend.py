import ast
import re
from typing import Dict, Iterable, List, Optional, Set

from .errors import CompileError, fail
from .model import (
    Contract,
    EnumCase,
    EnumType,
    ErrorCase,
    ErrorEnum,
    Event,
    EventField,
    Function,
    MapType,
    Parameter,
    StructField,
    StructType,
    ValueType,
    VecType,
    VEC_ELEMENT_TYPES,
    VEC_TYPES_BY_ELEMENT,
    is_collection,
    is_integer_type,
    is_map_type,
    is_vec_type,
    vec_element,
)


TYPE_NAMES = {
    "Address": ValueType.ADDRESS,
    "i32": ValueType.I32,
    "u32": ValueType.U32,
    "i64": ValueType.I64,
    "u64": ValueType.U64,
    "i128": ValueType.I128,
    "u128": ValueType.U128,
    "Symbol": ValueType.SYMBOL,
    "String": ValueType.STRING,
    "Bytes": ValueType.BYTES,
    "boolean": ValueType.BOOL,
    "bool": ValueType.BOOL,
    "None": ValueType.VOID,
}

CONTRACT_CALL_TYPES = {
    "call_void": ValueType.VOID,
    "call_i32": ValueType.I32,
    "call_u32": ValueType.U32,
    "call_i64": ValueType.I64,
    "call_u64": ValueType.U64,
    "call_i128": ValueType.I128,
    "call_u128": ValueType.U128,
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


def _annotation(node: Optional[ast.expr], user_types=None, *, allow_void: bool = False):
    if node is None:
        if allow_void:
            return ValueType.VOID
        fail(node, "type annotation is required", "E0201")
    user_types = user_types or {}
    if isinstance(node, ast.Name) and node.id in TYPE_NAMES:
        result = TYPE_NAMES[node.id]
    elif isinstance(node, ast.Name) and node.id in user_types:
        result = user_types[node.id]
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Vec":
        element = _annotation(node.slice, user_types)
        if element in VEC_TYPES_BY_ELEMENT:
            result = VEC_TYPES_BY_ELEMENT[element]
        elif isinstance(element, (StructType, EnumType)):
            result = VecType(element)
        else:
            fail(node, "unsupported Vec element type", "E0202")
    elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Map":
        if not isinstance(node.slice, ast.Tuple) or len(node.slice.elts) != 2:
            fail(node, "Map requires key and value types", "E0203")
        key = _annotation(node.slice.elts[0], user_types)
        value = _annotation(node.slice.elts[1], user_types)
        if is_collection(key):
            fail(node.slice.elts[0], "Map keys must be scalar contract types", "E0204")
        if is_collection(value):
            fail(node.slice.elts[1], "nested collection values are not supported yet", "E0205")
        result = MapType(key, value)
    elif isinstance(node, ast.Constant) and node.value is None:
        result = ValueType.VOID
    else:
        fail(node, "unsupported contract type", "E0206")
    if result is ValueType.VOID and not allow_void:
        fail(node, "None is not valid here", "E0207")
    return result


def _event_annotation(node: ast.expr, user_types=None):
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Topic":
        return _annotation(node.slice, user_types), True
    return _annotation(node, user_types), False


def _snake_case(name: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def _symbol_name(name: str) -> bool:
    raw = name.encode("utf-8")
    return bool(raw) and len(raw) <= 32 and all(
        byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122 for byte in raw
    )


def _user_type_nodes(module: ast.Module):
    structs = []
    enums = []
    for node in module.body:
        if not isinstance(node, ast.ClassDef):
            continue
        is_struct = _has_decorator(node, "struct")
        is_enum = _has_decorator(node, "enum")
        if not is_struct and not is_enum:
            continue
        if is_struct and is_enum or _has_decorator(node, "contract") or _has_decorator(node, "event") or _has_decorator(node, "error"):
            fail(node, "a class cannot combine @struct or @enum with another contract decorator", "E0803")
        if not node.name or len(node.name.encode("utf-8")) > 60:
            fail(node, "struct and enum names are limited to 60 UTF-8 bytes", "E0802")
        (structs if is_struct else enums).append(node)
    return structs, enums


def _parse_user_types(module: ast.Module):
    struct_nodes, enum_nodes = _user_type_nodes(module)
    names: Set[str] = set()
    for node in struct_nodes + enum_nodes:
        if node.name in names or node.name in TYPE_NAMES:
            fail(node, f"duplicate type {node.name!r}", "E0801")
        names.add(node.name)
    enums: Dict[str, EnumType] = {}
    for node in enum_nodes:
        cases: List[EnumCase] = []
        case_names: Set[str] = set()
        case_values: Set[int] = set()
        for child in _without_docstring(node.body):
            if isinstance(child, ast.Pass):
                continue
            if (
                not isinstance(child, ast.Assign)
                or len(child.targets) != 1
                or not isinstance(child.targets[0], ast.Name)
            ):
                fail(child, "enum bodies may only contain NAME = <u32> cases", "E0808")
            case_name = child.targets[0].id
            if case_name in case_names:
                fail(child, f"duplicate enum case {case_name!r}", "E0809")
            if len(case_name.encode("utf-8")) > 60:
                fail(child, "enum case names are limited to 60 UTF-8 bytes", "E0802")
            value = _integer_literal(child.value)
            if value is None:
                fail(child, "enum case values must be integer literals", "E0808")
            if not 0 <= value <= 2**32 - 1:
                fail(child, "enum case values must fit in u32", "E0810")
            if value in case_values:
                fail(child, f"duplicate enum value {value}", "E0811")
            case_names.add(case_name)
            case_values.add(value)
            cases.append(EnumCase(case_name, value))
        if not cases:
            fail(node, "enums must contain at least one case", "E0812")
        enums[node.name] = EnumType(node.name, tuple(cases), ast.get_docstring(node) or "")

    struct_by_name = {node.name: node for node in struct_nodes}
    structs: Dict[str, StructType] = {}
    resolving: Set[str] = set()

    def resolve_struct(name: str) -> StructType:
        if name in structs:
            return structs[name]
        if name in resolving:
            fail(struct_by_name[name], "recursive struct fields are not supported", "E0817")
        resolving.add(name)
        node = struct_by_name[name]
        fields: List[StructField] = []
        field_names: Set[str] = set()
        for child in _without_docstring(node.body):
            if isinstance(child, ast.Pass):
                continue
            if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name) or child.value is not None:
                fail(child, "struct bodies may only contain annotated fields", "E0804")
            field_name = child.target.id
            if field_name in field_names:
                fail(child, f"duplicate struct field {field_name!r}", "E0805")
            if not _symbol_name(field_name) or len(field_name.encode("utf-8")) > 30:
                fail(child, "struct field names must be Symbol-sized identifiers of at most 30 bytes", "E0806")
            field_names.add(field_name)
            field_type = _struct_field_type(child.annotation, enums, structs, struct_by_name, resolve_struct)
            fields.append(StructField(field_name, field_type))
        if not fields:
            fail(node, "structs must contain at least one field", "E0807")
        if len(fields) > 40:
            fail(node, "structs are limited to 40 fields", "E0818")
        resolving.remove(name)
        structs[name] = StructType(node.name, tuple(fields), ast.get_docstring(node) or "")
        return structs[name]

    for node in struct_nodes:
        resolve_struct(node.name)
    ordered_structs = tuple(structs[node.name] for node in struct_nodes)
    ordered_enums = tuple(enums[node.name] for node in enum_nodes)
    return ordered_structs, ordered_enums


def _struct_field_type(node, enums, structs, struct_by_name, resolve_struct):
    if isinstance(node, ast.Name) and node.id in struct_by_name:
        return resolve_struct(node.id)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Vec":
        element = _struct_field_type(node.slice, enums, structs, struct_by_name, resolve_struct)
        if element in VEC_TYPES_BY_ELEMENT:
            return VEC_TYPES_BY_ELEMENT[element]
        if isinstance(element, (StructType, EnumType)):
            return VecType(element)
        fail(node, "unsupported Vec element type", "E0202")
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == "Map":
        if not isinstance(node.slice, ast.Tuple) or len(node.slice.elts) != 2:
            fail(node, "Map requires key and value types", "E0203")
        key = _struct_field_type(node.slice.elts[0], enums, structs, struct_by_name, resolve_struct)
        value = _struct_field_type(node.slice.elts[1], enums, structs, struct_by_name, resolve_struct)
        if is_collection(key):
            fail(node.slice.elts[0], "Map keys must be scalar contract types", "E0204")
        if is_collection(value):
            fail(node.slice.elts[1], "nested collection values are not supported yet", "E0205")
        return MapType(key, value)
    return _annotation(node, {**enums, **structs})


def _parse_events(module: ast.Module, user_types=None) -> List[Event]:
    events: List[Event] = []
    names: Set[str] = set()
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or not _has_decorator(node, "event"):
            continue
        if node.name in names:
            fail(node, f"duplicate event {node.name!r}", "E0301")
        names.add(node.name)
        prefix = _snake_case(node.name)
        raw_prefix = prefix.encode("utf-8")
        if len(raw_prefix) > 32 or not prefix or any(
            not (byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122)
            for byte in raw_prefix
        ):
            fail(node, "event names must produce a Symbol prefix of at most 32 bytes", "E0302")

        fields: List[EventField] = []
        field_names: Set[str] = set()
        saw_data = False
        for child in _without_docstring(node.body):
            if isinstance(child, ast.Pass):
                continue
            if not isinstance(child, ast.AnnAssign) or not isinstance(child.target, ast.Name) or child.value is not None:
                fail(child, "event bodies may only contain annotated fields", "E0303")
            field_name = child.target.id
            if field_name in field_names:
                fail(child, f"duplicate event field {field_name!r}", "E0304")
            if len(field_name.encode("utf-8")) > 30:
                fail(child, "event field names are limited to 30 UTF-8 bytes", "E0305")
            field_names.add(field_name)
            value_type, is_topic = _event_annotation(child.annotation, user_types)
            if is_topic and (is_collection(value_type) or isinstance(value_type, StructType)):
                fail(child, "collection and struct values cannot be event topics", "E0306")
            if is_topic and saw_data:
                fail(child, "Topic fields must appear before the event data field", "E0307")
            if not is_topic:
                if saw_data:
                    fail(child, "typed events currently support exactly one data field", "E0308")
                saw_data = True
            fields.append(EventField(field_name, value_type, is_topic))
        if not saw_data:
            fail(node, "typed events require exactly one data field", "E0309")
        events.append(Event(node.name, prefix, tuple(fields), ast.get_docstring(node) or ""))
    return events


def _parse_errors(module: ast.Module) -> List[ErrorEnum]:
    errors: List[ErrorEnum] = []
    names: Set[str] = set()
    for node in module.body:
        if not isinstance(node, ast.ClassDef) or not _has_decorator(node, "error"):
            continue
        if _has_decorator(node, "contract") or _has_decorator(node, "event"):
            fail(node, "a class cannot combine @error with @contract or @event", "E0712")
        if node.name in names:
            fail(node, f"duplicate error {node.name!r}", "E0701")
        if not node.name or len(node.name.encode("utf-8")) > 60:
            fail(node, "error names are limited to 60 UTF-8 bytes", "E0702")
        names.add(node.name)
        cases: List[ErrorCase] = []
        case_names: Set[str] = set()
        case_values: Set[int] = set()
        for child in _without_docstring(node.body):
            if isinstance(child, ast.Pass):
                continue
            if (
                not isinstance(child, ast.Assign)
                or len(child.targets) != 1
                or not isinstance(child.targets[0], ast.Name)
            ):
                fail(child, "error bodies may only contain NAME = <u32> cases", "E0703")
            case_name = child.targets[0].id
            if case_name in case_names:
                fail(child, f"duplicate error case {case_name!r}", "E0704")
            if len(case_name.encode("utf-8")) > 60:
                fail(child, "error case names are limited to 60 UTF-8 bytes", "E0705")
            value = _integer_literal(child.value)
            if value is None:
                fail(child, "error case values must be integer literals", "E0706")
            if not 0 <= value <= 2**32 - 1:
                fail(child, "error case values must fit in u32", "E0707")
            if value in case_values:
                fail(child, f"duplicate error value {value}", "E0708")
            case_names.add(case_name)
            case_values.add(value)
            cases.append(ErrorCase(case_name, value))
        if not cases:
            fail(node, "error enums must contain at least one case", "E0713")
        errors.append(ErrorEnum(node.name, tuple(cases), ast.get_docstring(node) or ""))
    return errors


def _is_fail_call(node: ast.expr) -> bool:
    return isinstance(node, ast.Call) and _attribute_path(node.func) == ["fail"]


def parse_contract(source: str, source_name: Optional[str] = None) -> Contract:
    try:
        module = ast.parse(source, filename=source_name or "<contract>")
    except SyntaxError as exc:
        raise CompileError(exc.msg, exc.lineno, (exc.offset or 1) - 1, code="E0001") from exc

    classes = [
        node for node in module.body
        if isinstance(node, ast.ClassDef) and _has_decorator(node, "contract")
    ]
    if len(classes) != 1:
        raise CompileError("source must contain exactly one @contract class", code="E0002")
    contract_node = classes[0]

    structs, enums = _parse_user_types(module)
    user_types = {item.name: item for item in structs + enums}
    events = _parse_events(module, user_types)
    errors = _parse_errors(module)
    error_names = {item.name for item in errors}
    for event in events:
        if event.name in error_names or event.name in user_types:
            fail(contract_node, f"error and event names collide: {event.name!r}", "E0714")
    for error in errors:
        if error.name in user_types:
            fail(contract_node, f"error and user-type names collide: {error.name!r}", "E0813")
    functions: List[Function] = []
    names: Set[str] = set()
    for node in contract_node.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not _has_decorator(node, "public"):
            continue
        if isinstance(node, ast.AsyncFunctionDef):
            fail(node, "async contract functions are not supported", "E0101")
        if node.name in names:
            fail(node, f"duplicate contract function {node.name!r}", "E0102")
        names.add(node.name)
        if len(node.name.encode("utf-8")) > 32:
            fail(node, "contract function names are limited to 32 UTF-8 bytes", "E0103")
        if node.args.vararg or node.args.kwarg or node.args.kwonlyargs or node.args.posonlyargs:
            fail(node, "variadic, keyword-only, and positional-only parameters are not supported", "E0104")

        args = list(node.args.args)
        if not args or args[0].arg != "self":
            fail(node, "public methods must declare self as their first parameter", "E0105")
        params = []
        for arg in args[1:]:
            if len(arg.arg.encode("utf-8")) > 30:
                fail(arg, "parameter names are limited to 30 UTF-8 bytes", "E0106")
            params.append(Parameter(arg.arg, _annotation(arg.annotation, user_types)))
        if node.args.defaults:
            fail(node, "default parameter values are not supported", "E0107")
        result = _annotation(node.returns, user_types, allow_void=True)
        functions.append(Function(node.name, tuple(params), result, node, ast.get_docstring(node) or ""))

    if not functions:
        fail(contract_node, "contract must contain at least one @public method", "E0108")

    contract = Contract(
        name=contract_node.name,
        functions=tuple(functions),
        events=tuple(events),
        errors=tuple(errors),
        structs=structs,
        enums=enums,
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
        self.errors = {error.name: error for error in contract.errors}
        self.structs = {item.name: item for item in contract.structs}
        self.enums = {item.name: item for item in contract.enums}
        self.user_types = {**self.structs, **self.enums}

    def check(self):
        for function in self.contract.functions:
            self.function = function
            self.variables = {param.name: param.type for param in function.params}
            body = _without_docstring(function.node.body)
            for statement in body:
                self.check_statement(statement)
            if function.result is not ValueType.VOID and not _always_returns(body):
                fail(function.node, f"function {function.name!r} does not return on every path", "E0109")

    def check_statement(self, node: ast.stmt):
        if isinstance(node, ast.Return):
            actual = ValueType.VOID if node.value is None else self.check_expr(node.value)
            if actual != self.function.result:
                fail(node, f"expected return type {self.function.result.value}, got {actual.value}", "E0110")
            return
        if isinstance(node, ast.AnnAssign):
            if not isinstance(node.target, ast.Name) or node.value is None:
                fail(node, "annotated assignments require a simple name and value", "E0401")
            declared = _annotation(node.annotation, self.user_types)
            if self._is_pop(node.value):
                actual = self._check_pop(node.value)
            elif self._is_empty_collection(node.value):
                actual = self._check_empty_collection(node.value, declared)
            else:
                actual = self.check_expr(node.value)
            if declared != actual:
                fail(node, f"cannot assign {actual.value} to {declared.value}", "E0402")
            self._bind(node.target, declared)
            return
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                fail(node, "only simple single-target assignments are supported", "E0403")
            if self._is_pop(node.value):
                actual = self._check_pop(node.value)
            elif self._is_empty_collection(node.value):
                fail(node.value, "empty Vec() and Map() require an annotated type", "E0647")
            else:
                actual = self.check_expr(node.value)
            target = node.targets[0]
            if target.id in self.variables and self.variables[target.id] != actual:
                fail(node, f"cannot change type of {target.id!r}", "E0404")
            self._bind(target, actual)
            return
        if isinstance(node, ast.If):
            if self.check_expr(node.test) is not ValueType.BOOL:
                fail(node.test, "if condition must be boolean", "E0405")
            before = dict(self.variables)
            for child in node.body:
                self.check_statement(child)
            body_vars = dict(self.variables)
            self.variables = dict(before)
            for child in node.orelse:
                self.check_statement(child)
            else_vars = dict(self.variables)
            for name in set(body_vars) & set(else_vars):
                if body_vars[name] == else_vars[name]:
                    self.variables[name] = body_vars[name]
            return
        if isinstance(node, ast.For):
            if not isinstance(node.target, ast.Name):
                fail(node.target, "for loop targets must be simple names", "E0406")
            if node.orelse:
                fail(node, "for/else is not supported", "E0407")
            start, stop = self._check_range(node.iter)
            before = dict(self.variables)
            if node.target.id in before and before[node.target.id] is not ValueType.I32:
                fail(node.target, "range loop variables must be i32", "E0408")
            self.variables[node.target.id] = ValueType.I32
            for child in node.body:
                self.check_statement(child)
            new_names = set(self.variables) - set(before) - {node.target.id}
            if new_names:
                fail(node, "variables assigned inside a loop must be declared before the loop", "E0409")
            self.variables = before
            return
        if isinstance(node, ast.Pass):
            return
        if isinstance(node, ast.Expr):
            if _is_fail_call(node.value):
                self._check_call(node.value)
                return
            if self._is_pop(node.value):
                fail(node, "Vec.pop() must be assigned", "E0645")
            if self._is_mutation(node.value):
                self._check_mutation(node.value)
                return
            if self.check_expr(node.value) is not ValueType.VOID:
                fail(node, "expression statements must return None", "E0410")
            return
        fail(node, f"unsupported statement: {type(node).__name__}", "E0411")

    def _bind(self, node: ast.Name, value_type: ValueType):
        if node.id == "self":
            fail(node, "self cannot be assigned", "E0412")
        self.variables[node.id] = value_type

    def check_expr(self, node: ast.expr) -> ValueType:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return ValueType.BOOL
            if isinstance(node.value, int) and -(2**31) <= node.value < 2**31:
                return ValueType.I32
            fail(node, "only boolean and signed 32-bit integer constants are supported", "E0501")
        if isinstance(node, ast.Name):
            if node.id not in self.variables:
                fail(node, f"unknown variable {node.id!r}", "E0502")
            return self.variables[node.id]
        if isinstance(node, ast.Subscript):
            if not isinstance(node.value, ast.Name) or node.value.id not in self.variables:
                fail(node, "collection indexing requires a Vec or Map variable", "E0503")
            collection_type = self.variables[node.value.id]
            if isinstance(node.slice, ast.Slice):
                fail(node.slice, "collection slicing is not supported", "E0504")
            index_type = self.check_expr(node.slice)
            if is_vec_type(collection_type):
                if index_type is not ValueType.I32:
                    fail(node.slice, "Vec indices must be i32", "E0505")
                return vec_element(collection_type)
            if isinstance(collection_type, MapType):
                if index_type != collection_type.key:
                    fail(node.slice, f"Map key expects {collection_type.key.value}, got {index_type.value}", "E0506")
                return collection_type.value_type
            fail(node.value, "only Vec and Map values can be indexed", "E0507")
        if isinstance(node, ast.Attribute):
            return self._check_attribute(node)
        if isinstance(node, ast.UnaryOp):
            operand = self.check_expr(node.operand)
            if isinstance(node.op, ast.USub) and operand in {ValueType.I32, ValueType.I64}:
                return operand
            if isinstance(node.op, ast.Not) and operand is ValueType.BOOL:
                return ValueType.BOOL
            fail(node, "invalid unary operator for operand type", "E0508")
        if isinstance(node, ast.BinOp):
            left, right = self.check_expr(node.left), self.check_expr(node.right)
            if left is not right or left not in {
                ValueType.I32, ValueType.U32, ValueType.I64, ValueType.U64,
                ValueType.I128, ValueType.U128,
            }:
                fail(node, "arithmetic operands must have the same numeric type", "E0509")
            if left is ValueType.I128 and isinstance(node.op, ast.FloorDiv):
                fail(node, "i128 division is not supported; use checked u128 // or u128.mul_div_floor", "E0511")
            if left in {ValueType.I128, ValueType.U128} and not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv)):
                fail(node, "i128/u128 arithmetic supports checked +, -, *, and unsigned //", "E0510")
            if isinstance(node.op, ast.FloorDiv):
                if left not in {ValueType.U32, ValueType.U64, ValueType.U128}:
                    fail(node, "floor division is supported for u32, u64, and checked u128", "E0511")
                return left
            if not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
                fail(node, "supported arithmetic operators are +, -, *, and unsigned //", "E0512")
            return left
        if isinstance(node, ast.BoolOp):
            if not all(self.check_expr(value) is ValueType.BOOL for value in node.values):
                fail(node, "and/or operands must be boolean", "E0513")
            return ValueType.BOOL
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                fail(node, "chained comparisons are not supported yet", "E0514")
            left, right = self.check_expr(node.left), self.check_expr(node.comparators[0])
            if left != right:
                fail(node, "comparison operands must have the same type", "E0515")
            if isinstance(left, EnumType):
                return ValueType.BOOL
            if left not in {
                ValueType.I32, ValueType.U32, ValueType.I64, ValueType.U64,
                ValueType.I128, ValueType.U128,
            } and not isinstance(
                node.ops[0], (ast.Eq, ast.NotEq)
            ):
                fail(node, f"{left.value} only supports == and !=", "E0516")
            return ValueType.BOOL
        if isinstance(node, ast.Call):
            if _is_fail_call(node):
                fail(node, "fail() is only valid as an expression statement", "E0715")
            if self._is_pop(node):
                fail(node, "Vec.pop() must be assigned", "E0645")
            if self._is_mutation(node):
                fail(node, "collection updates must be statements", "E0644")
            return self._check_call(node)
        fail(node, f"unsupported expression: {type(node).__name__}", "E0517")

    def _check_attribute(self, node: ast.Attribute):
        if isinstance(node.value, ast.Name) and node.value.id in self.enums:
            enum = self.enums[node.value.id]
            if not any(case.name == node.attr for case in enum.cases):
                fail(node, f"unknown enum case {node.value.id}.{node.attr}", "E0816")
            return enum
        owner = self.variables.get(node.value.id) if isinstance(node.value, ast.Name) else None
        if owner is None:
            owner = self.check_expr(node.value)
        if isinstance(owner, StructType):
            field = next((item for item in owner.fields if item.name == node.attr), None)
            if field is None:
                fail(node, f"unknown field {node.attr!r} on {owner.name}", "E0814")
            return field.type
        fail(node, "unsupported attribute", "E0517")

    def _check_call(self, node: ast.Call) -> ValueType:
        if node.keywords:
            fail(node, "keyword arguments are not supported", "E0601")
        path = _attribute_path(node.func)
        service = self._check_service(node, path)
        if service is not None:
            return service
        if path == ["fail"]:
            if len(node.args) != 1:
                fail(node, "fail() takes one @error case", "E0709")
            self._check_error_case(node.args[0])
            return ValueType.VOID
        if path == ["len"]:
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
                fail(node, "len() requires one Vec, Map, String, or Bytes variable", "E0602")
            value_type = self.variables.get(node.args[0].id)
            if (
                not is_vec_type(value_type)
                and not isinstance(value_type, MapType)
                and value_type not in {ValueType.STRING, ValueType.BYTES}
            ):
                fail(node.args[0], "len() is only supported for Vec, Map, String, and Bytes values", "E0603")
            return ValueType.I32
        if len(path) == 2 and path[1] == "has":
            owner = path[0]
            map_type = self.variables.get(owner)
            if not isinstance(map_type, MapType):
                fail(node, "has() is only available on Map values", "E0604")
            if len(node.args) != 1:
                fail(node, "Map.has() takes one key", "E0605")
            actual = self.check_expr(node.args[0])
            if actual != map_type.key:
                fail(node.args[0], f"Map key expects {map_type.key.value}, got {actual.value}", "E0606")
            return ValueType.BOOL
        if path == ["u128", "mul_div_floor"]:
            if len(node.args) != 3:
                fail(node, "u128.mul_div_floor() takes left, right, and denominator", "E0607")
            for argument in node.args:
                actual = self.check_expr(argument)
                if actual is not ValueType.U128:
                    fail(argument, f"u128.mul_div_floor() expects u128 arguments, got {actual.value}", "E0608")
            return ValueType.U128
        if len(path) == 1 and path[0] in {"i32", "u32", "i64", "u64", "i128", "u128"}:
            value = _integer_literal(node.args[0]) if len(node.args) == 1 else None
            if value is None:
                fail(node, f"{path[0]}() requires one integer literal", "E0609")
            bounds = {
                "i32": (-(2**31), 2**31 - 1),
                "u32": (0, 2**32 - 1),
                "i64": (-(2**63), 2**63 - 1),
                "u64": (0, 2**64 - 1),
                "i128": (-(2**127), 2**127 - 1),
                "u128": (0, 2**128 - 1),
            }
            lower, upper = bounds[path[0]]
            if not lower <= value <= upper:
                fail(node.args[0], f"literal is outside the {path[0]} range", "E0610")
            return TYPE_NAMES[path[0]]
        if len(path) == 1 and path[0] in {"Symbol", "String", "Bytes"}:
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Constant):
                fail(node, f"{path[0]}() requires one literal", "E0611")
            value = node.args[0].value
            expected = bytes if path[0] == "Bytes" else str
            if not isinstance(value, expected):
                fail(node.args[0], f"{path[0]}() requires a {expected.__name__} literal", "E0612")
            if path[0] == "Symbol":
                raw = value.encode("utf-8")
                if len(raw) > 32 or any(not (byte == 95 or 48 <= byte <= 57 or 65 <= byte <= 90 or 97 <= byte <= 122) for byte in raw):
                    fail(node.args[0], "Symbol literals must be at most 32 bytes using only [a-zA-Z0-9_]", "E0613")
            return TYPE_NAMES[path[0]]
        if len(path) == 2 and path[1] == "require_auth":
            owner = path[0]
            if owner not in self.variables or self.variables[owner] is not ValueType.ADDRESS:
                fail(node, "require_auth() is only available on Address values", "E0614")
            if node.args:
                fail(node, "require_auth() takes no arguments", "E0615")
            return ValueType.VOID
        if len(path) == 2 and path[1] in CONTRACT_CALL_TYPES:
            target = path[0]
            if target not in self.variables or self.variables[target] is not ValueType.ADDRESS:
                fail(node, "cross-contract calls are only available on Address values", "E0616")
            if not node.args:
                fail(node, f"{path[1]}() requires a Symbol function name", "E0617")
            if self.check_expr(node.args[0]) is not ValueType.SYMBOL:
                fail(node.args[0], "cross-contract function name must be a Symbol", "E0618")
            for argument in node.args[1:]:
                if self.check_expr(argument) is ValueType.VOID:
                    fail(argument, "cross-contract arguments cannot be None", "E0619")
            return CONTRACT_CALL_TYPES[path[1]]
        if len(path) == 1 and path[0] in self.structs:
            struct = self.structs[path[0]]
            if len(node.args) != len(struct.fields):
                fail(node, f"{struct.name}() expects {len(struct.fields)} arguments, got {len(node.args)}", "E0815")
            for field, argument in zip(struct.fields, node.args):
                actual = self.check_expr(argument)
                if actual != field.type:
                    fail(argument, f"field {field.name!r} expects {field.type.value}, got {actual.value}", "E0815")
            return struct
        if path[:1] == ["storage"] and len(path) == 3 and path[1] in {"instance", "persistent", "temporary"}:
            return self._check_storage(node, path[1], path[2])
        if path == ["events", "publish"]:
            if len(node.args) == 1 and isinstance(node.args[0], ast.Call):
                constructor = node.args[0]
                event_path = _attribute_path(constructor.func)
                event = self.events.get(event_path[0]) if len(event_path) == 1 else None
                if event is None:
                    fail(constructor, "events.publish() requires a declared @event value", "E0622")
                if constructor.keywords:
                    fail(constructor, "event constructors do not support keyword arguments", "E0623")
                if len(constructor.args) != len(event.fields):
                    fail(constructor, f"{event.name}() expects {len(event.fields)} arguments, got {len(constructor.args)}", "E0624")
                for field, value in zip(event.fields, constructor.args):
                    actual = self.check_expr(value)
                    if actual != field.type:
                        fail(value, f"event field {field.name!r} expects {field.type.value}, got {actual.value}", "E0625")
                return ValueType.VOID
            if len(node.args) != 2:
                fail(node, "events.publish() takes an @event value, or one Symbol topic and one data value", "E0626")
            if self.check_expr(node.args[0]) is not ValueType.SYMBOL:
                fail(node.args[0], "event topic must be a Symbol", "E0627")
            if self.check_expr(node.args[1]) is ValueType.VOID:
                fail(node.args[1], "event data cannot be None", "E0628")
            return ValueType.VOID
        fail(node, "unsupported function or method call", "E0629")

    def _check_storage(self, node: ast.Call, tier: str, method: str):
        legacy_getters = {
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
        label = f"storage.{tier}.{method}()"
        if method in legacy_getters or method == "has":
            if len(node.args) != 1:
                fail(node, f"{label} takes one key", "E0620")
            self._check_storage_value(node.args[0])
            return ValueType.BOOL if method == "has" else legacy_getters[method]
        if method == "get":
            if len(node.args) != 2:
                fail(node, f"{label} takes a key and a type", "E0641")
            self._check_storage_value(node.args[0])
            value_type = _annotation(node.args[1], self.user_types)
            if value_type is ValueType.VOID:
                fail(node.args[1], "storage values cannot be None", "E0641")
            return value_type
        if method == "set":
            if len(node.args) != 2:
                fail(node, f"{label} takes a key and value", "E0621")
            self._check_storage_value(node.args[0])
            self._check_storage_value(node.args[1])
            return ValueType.VOID
        if method == "remove":
            if len(node.args) != 1:
                fail(node, f"{label} takes one key", "E0642")
            self._check_storage_value(node.args[0])
            return ValueType.VOID
        if method == "extend_ttl":
            if tier == "instance":
                if len(node.args) != 2:
                    fail(node, "storage.instance.extend_ttl() takes threshold and extend_to", "E0643")
                for argument in node.args:
                    if self.check_expr(argument) is not ValueType.U32:
                        fail(argument, "TTL bounds must be u32", "E0643")
                return ValueType.VOID
            if len(node.args) != 3:
                fail(node, f"{label} takes a key, threshold, and extend_to", "E0643")
            self._check_storage_value(node.args[0])
            for argument in node.args[1:]:
                if self.check_expr(argument) is not ValueType.U32:
                    fail(argument, "TTL bounds must be u32", "E0643")
            return ValueType.VOID
        fail(node, "unsupported function or method call", "E0629")

    def _is_empty_collection(self, node: ast.expr) -> bool:
        return (
            isinstance(node, ast.Call)
            and not node.args
            and not node.keywords
            and _attribute_path(node.func) in (["Vec"], ["Map"])
        )

    def _check_empty_collection(self, node: ast.Call, declared):
        name = _attribute_path(node.func)[0]
        if name == "Vec" and is_vec_type(declared):
            return declared
        if name == "Map" and isinstance(declared, MapType):
            return declared
        fail(node, f"{name}() does not match the annotated type", "E0648")

    def _receiver(self, node: ast.Call):
        if not isinstance(node.func, ast.Attribute) or not isinstance(node.func.value, ast.Name):
            return None
        name = node.func.value.id
        if name not in self.variables:
            return None
        return name, self.variables[name], node.func.attr

    def _is_pop(self, node: ast.expr) -> bool:
        if not isinstance(node, ast.Call) or node.args or node.keywords:
            return False
        receiver = self._receiver(node)
        return receiver is not None and receiver[2] == "pop" and is_vec_type(receiver[1])

    def _is_mutation(self, node: ast.expr) -> bool:
        if not isinstance(node, ast.Call) or node.keywords:
            return False
        receiver = self._receiver(node)
        if receiver is None:
            return False
        _name, value_type, method = receiver
        if is_vec_type(value_type) and method in {"push", "set", "insert", "remove"}:
            return True
        if value_type is ValueType.BYTES and method == "append":
            return True
        return isinstance(value_type, MapType) and method in {"set", "remove"}

    def _check_pop(self, node: ast.Call):
        receiver = self._receiver(node)
        if receiver is None or not self._is_pop(node):
            fail(node, "Vec.pop() requires a Vec local", "E0645")
        return vec_element(receiver[1])

    def _check_mutation(self, node: ast.Call):
        name, value_type, method = self._receiver(node)
        if is_vec_type(value_type):
            element = vec_element(value_type)
            if method == "push":
                if len(node.args) != 1:
                    fail(node, "Vec.push() takes one element", "E0644")
                actual = self.check_expr(node.args[0])
                if actual != element:
                    fail(node.args[0], f"Vec element expects {element.value}, got {actual.value}", "E0644")
                return
            if method in {"set", "insert"}:
                if len(node.args) != 2:
                    fail(node, f"Vec.{method}() takes an i32 index and an element", "E0644")
                if self.check_expr(node.args[0]) is not ValueType.I32:
                    fail(node.args[0], "Vec indices must be i32", "E0644")
                actual = self.check_expr(node.args[1])
                if actual != element:
                    fail(node.args[1], f"Vec element expects {element.value}, got {actual.value}", "E0644")
                return
            if method == "remove":
                if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.I32:
                    fail(node, "Vec.remove() takes one i32 index", "E0644")
                return
        if value_type is ValueType.BYTES and method == "append":
            if len(node.args) != 1:
                fail(node, "Bytes.append() takes one Bytes value", "E0644")
            actual = self.check_expr(node.args[0])
            if actual is not ValueType.BYTES:
                fail(node.args[0], f"Bytes.append() expects Bytes, got {actual.value}", "E0644")
            return
        if isinstance(value_type, MapType):
            if method == "set":
                if len(node.args) != 2:
                    fail(node, "Map.set() takes a key and a value", "E0644")
                key = self.check_expr(node.args[0])
                actual = self.check_expr(node.args[1])
                if key != value_type.key:
                    fail(node.args[0], f"Map key expects {value_type.key.value}, got {key.value}", "E0644")
                if actual != value_type.value_type:
                    fail(node.args[1], f"Map value expects {value_type.value_type.value}, got {actual.value}", "E0644")
                return
            if method == "remove":
                if len(node.args) != 1:
                    fail(node, "Map.remove() takes one key", "E0644")
                key = self.check_expr(node.args[0])
                if key != value_type.key:
                    fail(node.args[0], f"Map key expects {value_type.key.value}, got {key.value}", "E0644")
                return
        fail(node, "unsupported collection update", "E0644")

    def _check_service(self, node: ast.Call, path):
        if path == ["ledger", "sequence"] and not node.args:
            return ValueType.U32
        if path == ["ledger", "timestamp"] and not node.args:
            return ValueType.U64
        if path == ["ledger", "version"] and not node.args:
            return ValueType.U32
        if path == ["ledger", "network_id"] and not node.args:
            return ValueType.BYTES
        if path == ["env", "current_contract_address"] and not node.args:
            return ValueType.ADDRESS
        if path == ["crypto", "sha256"] or path == ["crypto", "keccak256"]:
            if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.BYTES:
                fail(node, f"{path[1]}() takes one Bytes value", "E0651")
            return ValueType.BYTES
        if path == ["crypto", "ed25519_verify"]:
            if len(node.args) != 3 or any(self.check_expr(arg) is not ValueType.BYTES for arg in node.args):
                fail(node, "ed25519_verify() takes a public key, message, and signature", "E0651")
            return ValueType.VOID
        if path == ["log"]:
            if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.STRING:
                fail(node, "log() takes one String value", "E0653")
            return ValueType.VOID
        if path == ["prng", "bytes"]:
            if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.U32:
                fail(node, "prng.bytes() takes one u32 length", "E0654")
            return ValueType.BYTES
        if path == ["prng", "u64"]:
            if len(node.args) != 2 or any(self.check_expr(arg) is not ValueType.U64 for arg in node.args):
                fail(node, "prng.u64() takes an inclusive u64 range", "E0654")
            return ValueType.U64
        if path == ["deploy", "contract"]:
            if len(node.args) != 2 or any(self.check_expr(arg) is not ValueType.BYTES for arg in node.args):
                fail(node, "deploy.contract() takes a Wasm hash and a salt", "E0652")
            return ValueType.ADDRESS
        if path == ["deploy", "with_constructor"]:
            if len(node.args) < 2 or any(self.check_expr(arg) is not ValueType.BYTES for arg in node.args[:2]):
                fail(node, "deploy.with_constructor() takes a Wasm hash, a salt, and constructor arguments", "E0652")
            for argument in node.args[2:]:
                if self.check_expr(argument) is ValueType.VOID:
                    fail(argument, "constructor arguments cannot be None", "E0652")
            return ValueType.ADDRESS
        if path == ["deploy", "upload"]:
            if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.BYTES:
                fail(node, "deploy.upload() takes one Bytes Wasm payload", "E0652")
            return ValueType.BYTES
        if path == ["deploy", "upgrade"]:
            if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.BYTES:
                fail(node, "deploy.upgrade() takes one Wasm hash", "E0652")
            return ValueType.VOID
        if path == ["deploy", "asset"]:
            if len(node.args) != 1 or self.check_expr(node.args[0]) is not ValueType.BYTES:
                fail(node, "deploy.asset() takes one serialized Stellar asset", "E0652")
            return ValueType.ADDRESS
        if len(path) == 2 and path[1] == "require_auth_for":
            if path[0] not in self.variables or self.variables[path[0]] is not ValueType.ADDRESS:
                fail(node, "require_auth_for() is only available on Address values", "E0614")
            if not node.args:
                fail(node, "require_auth_for() takes the authorized arguments", "E0655")
            for argument in node.args:
                if self.check_expr(argument) is ValueType.VOID:
                    fail(argument, "authorization arguments cannot be None", "E0655")
            return ValueType.VOID
        if len(path) == 2 and path[1] in {"to_bytes", "to_string", "slice"}:
            owner = self.variables.get(path[0])
            if path[1] == "to_bytes" and owner is ValueType.STRING and not node.args:
                return ValueType.BYTES
            if path[1] == "to_string" and owner is ValueType.BYTES and not node.args:
                return ValueType.STRING
            if path[1] == "slice" and owner is ValueType.BYTES:
                if len(node.args) != 2 or any(self.check_expr(arg) is not ValueType.U32 for arg in node.args):
                    fail(node, "Bytes.slice() takes u32 start and end positions", "E0656")
                return ValueType.BYTES
        return None

    def _check_error_case(self, node: ast.expr):
        path = _attribute_path(node)
        if len(path) != 2 or path[0] not in self.errors:
            fail(node, "fail() requires a declared @error case", "E0710")
        error = self.errors[path[0]]
        if not any(case.name == path[1] for case in error.cases):
            fail(node, f"unknown error case {path[0]}.{path[1]}", "E0711")

    def _check_storage_value(self, node: ast.expr):
        value_type = self.check_expr(node)
        if value_type is ValueType.VOID:
            fail(node, "unsupported storage key or value type", "E0630")

    def _check_range(self, node: ast.expr):
        if not isinstance(node, ast.Call) or _attribute_path(node.func) != ["range"] or node.keywords:
            fail(node, "for loops require range(stop) or range(start, stop)", "E0631")
        if len(node.args) == 1:
            start, stop = ast.Constant(value=0), node.args[0]
        elif len(node.args) == 2:
            start, stop = node.args
        else:
            fail(node, "range() supports one or two arguments", "E0632")
        if self.check_expr(start) is not ValueType.I32 or self.check_expr(stop) is not ValueType.I32:
            fail(node, "range() bounds must be i32", "E0633")
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
        if isinstance(statement, ast.Expr) and _is_fail_call(statement.value):
            return True
        if isinstance(statement, ast.If) and statement.orelse:
            if _always_returns(statement.body) and _always_returns(statement.orelse):
                return True
    return False
