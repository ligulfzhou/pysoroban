"""Deterministic Python test environment for compiled PySoroban Typed IR.

This module is intentionally an IR simulator, not a replacement for Soroban's
Wasm host. It gives contract authors fast unit tests for language semantics,
authorization requirements, instance storage, and emitted events. Testnet or a
native Soroban host remains the source of truth for integration testing.
"""

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Iterable, Mapping, Optional, Tuple, Union

from . import ir
from .compiler import CompilationResult, compile_source
from .model import ValueType, VEC_ELEMENT_TYPES


NativeValue = Union[None, bool, int, str, bytes, list, tuple]


class InvocationError(Exception):
    """Base class for deterministic contract-test failures."""


class AuthorizationError(InvocationError):
    """Raised when a contract requires an address absent from invocation auth."""


class StorageMissingError(InvocationError):
    """Raised when a typed storage get references a missing key."""


@dataclass(frozen=True)
class Event:
    topics: Tuple[NativeValue, ...]
    data: NativeValue


class _ReturnSignal(Exception):
    def __init__(self, value: NativeValue):
        self.value = value


class ContractTest:
    """Execute a checked contract's Typed IR with persistent instance state."""

    def __init__(self, compilation: CompilationResult):
        self.compilation = compilation
        self.contract = compilation.ir
        self._storage = {}
        self._events = []
        self._last_events = []
        self._authorized = set()
        self._contracts = {}

    @classmethod
    def from_source(cls, source: str, source_name: Optional[str] = None) -> "ContractTest":
        return cls(compile_source(source, source_name))

    @classmethod
    def from_file(cls, source_path: Union[str, Path]) -> "ContractTest":
        path = Path(source_path)
        return cls.from_source(path.read_text(encoding="utf-8"), str(path))

    @property
    def storage(self) -> Mapping[NativeValue, NativeValue]:
        return MappingProxyType({key: entry[0] for key, entry in self._storage.items()})

    @property
    def events(self) -> Tuple[Event, ...]:
        return tuple(self._events)

    @property
    def last_events(self) -> Tuple[Event, ...]:
        return tuple(self._last_events)

    def clear_events(self) -> None:
        self._events.clear()
        self._last_events.clear()

    def register_contract(self, address: str, contract: "ContractTest") -> None:
        """Link an address to another deterministic test contract."""
        if not isinstance(address, str):
            raise InvocationError("contract address must be a string")
        self._contracts[address] = contract

    def invoke(self, name: str, *args: NativeValue, auth: Iterable[str] = (), **kwargs: NativeValue) -> NativeValue:
        function = next((item for item in self.contract.functions if item.name == name), None)
        if function is None:
            raise InvocationError(f"unknown contract function {name!r}")
        if args and kwargs:
            raise InvocationError("use positional or keyword arguments, not both")
        if kwargs:
            expected = {param.name for param in function.params}
            unknown = set(kwargs) - expected
            missing = expected - set(kwargs)
            if unknown:
                raise InvocationError(f"unknown arguments: {', '.join(sorted(unknown))}")
            if missing:
                raise InvocationError(f"missing arguments: {', '.join(sorted(missing))}")
            values = tuple(kwargs[param.name] for param in function.params)
        else:
            values = args
        if len(values) != len(function.params):
            raise InvocationError(f"{name}() expects {len(function.params)} arguments, got {len(values)}")
        for param, value in zip(function.params, values):
            _validate_native(value, param.type, param.name)

        variables = dict(zip((param.name for param in function.params), values))
        self._authorized = set(auth)
        self._last_events = []
        try:
            self._statements(function.body, variables)
        except _ReturnSignal as returned:
            _validate_native(returned.value, function.result, "return value")
            return returned.value
        finally:
            self._authorized = set()
        if function.result is ValueType.VOID:
            return None
        raise InvocationError(f"{name}() completed without returning a value")

    def _statements(self, statements: Tuple[ir.Statement, ...], variables) -> None:
        for statement in statements:
            if isinstance(statement, ir.Return):
                raise _ReturnSignal(self._expression(statement.value, variables))
            if isinstance(statement, ir.SetLocal):
                variables[statement.name] = self._expression(statement.value, variables)
                continue
            if isinstance(statement, ir.If):
                branch = statement.body if self._expression(statement.test, variables) else statement.otherwise
                self._statements(branch, variables)
                continue
            if isinstance(statement, ir.ForRange):
                start = self._expression(statement.start, variables)
                stop = self._expression(statement.stop, variables)
                variables[statement.stop_local] = stop
                for value in range(start, stop):
                    variables[statement.variable] = value
                    self._statements(statement.body, variables)
                continue
            if isinstance(statement, ir.Drop):
                self._expression(statement.value, variables)
                continue
            raise AssertionError(type(statement).__name__)

    def _expression(self, expression: ir.Expression, variables) -> NativeValue:
        if isinstance(expression, ir.Constant):
            return expression.value
        if isinstance(expression, ir.Local):
            return variables[expression.name]
        if isinstance(expression, ir.Unary):
            value = self._expression(expression.operand, variables)
            if expression.op == "not":
                return not value
            if expression.op == "neg":
                return _wrap_integer(-value, expression.type)
        if isinstance(expression, ir.Binary):
            left = self._expression(expression.left, variables)
            right = self._expression(expression.right, variables)
            if expression.op == "and":
                return left and right
            if expression.op == "or":
                return left or right
            value = {"add": left + right, "sub": left - right, "mul": left * right}[expression.op]
            return _wrap_integer(value, expression.type)
        if isinstance(expression, ir.Compare):
            left = self._expression(expression.left, variables)
            right = self._expression(expression.right, variables)
            return {
                "eq": left == right,
                "ne": left != right,
                "lt": left < right,
                "gt": left > right,
                "le": left <= right,
                "ge": left >= right,
            }[expression.op]
        if isinstance(expression, ir.HostCall):
            return self._host_call(expression, variables)
        raise AssertionError(type(expression).__name__)

    def _host_call(self, call: ir.HostCall, variables) -> NativeValue:
        values = tuple(self._expression(arg, variables) for arg in call.args)
        if call.op == "require_auth":
            if values[0] not in self._authorized:
                raise AuthorizationError(f"missing authorization for {values[0]!r}")
            return None
        if call.op == "storage_set":
            self._storage[values[0]] = (values[1], call.args[1].type)
            return None
        if call.op == "storage_has":
            return values[0] in self._storage
        if call.op.startswith("storage_get_"):
            if values[0] not in self._storage:
                raise StorageMissingError(f"missing instance storage key {values[0]!r}")
            result, stored_type = self._storage[values[0]]
            if stored_type is not call.type:
                raise InvocationError(
                    f"stored value is {stored_type.value}, not the requested {call.type.value}"
                )
            _validate_native(result, call.type, "stored value")
            return result
        if call.op == "event_publish":
            event = Event(tuple(values[:-1]), values[-1])
            self._events.append(event)
            self._last_events.append(event)
            return None
        if call.op == "contract_call":
            address, function, *args = values
            target = self._contracts.get(address)
            if target is None:
                raise InvocationError(f"unregistered contract address {address!r}")
            result = target.invoke(function, *args)
            _validate_native(result, call.type, "cross-contract return value")
            return result
        if call.op == "vec_len":
            return len(values[0])
        if call.op == "vec_get":
            vector, index = values
            if index < 0 or index >= len(vector):
                raise InvocationError(f"Vec index {index} is out of bounds")
            return vector[index]
        raise AssertionError(call.op)


def _wrap_integer(value: int, value_type: ValueType) -> int:
    bits = 64 if value_type in {ValueType.I64, ValueType.U64} else 32
    value %= 2**bits
    if value_type in {ValueType.I32, ValueType.I64} and value >= 2 ** (bits - 1):
        value -= 2**bits
    return value


def _validate_native(value: NativeValue, value_type: ValueType, label: str) -> None:
    if value_type is ValueType.VOID:
        valid = value is None
    elif value_type is ValueType.BOOL:
        valid = isinstance(value, bool)
    elif value_type in {ValueType.I32, ValueType.U32, ValueType.I64, ValueType.U64}:
        valid = isinstance(value, int) and not isinstance(value, bool)
        if valid:
            bounds = {
                ValueType.I32: (-(2**31), 2**31 - 1),
                ValueType.U32: (0, 2**32 - 1),
                ValueType.I64: (-(2**63), 2**63 - 1),
                ValueType.U64: (0, 2**64 - 1),
            }
            lower, upper = bounds[value_type]
            valid = lower <= value <= upper
    elif value_type in {ValueType.ADDRESS, ValueType.STRING, ValueType.SYMBOL}:
        valid = isinstance(value, str)
    elif value_type is ValueType.BYTES:
        valid = isinstance(value, bytes)
    elif value_type in VEC_ELEMENT_TYPES:
        valid = isinstance(value, (list, tuple))
        if valid:
            try:
                for index, item in enumerate(value):
                    _validate_native(item, VEC_ELEMENT_TYPES[value_type], f"{label}[{index}]")
            except InvocationError:
                raise
    else:
        valid = False
    if not valid:
        raise InvocationError(f"{label} is not a valid {value_type.value}")
