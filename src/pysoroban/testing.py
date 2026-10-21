"""Deterministic Python test environment for compiled PySoroban Typed IR.

This module is intentionally an IR simulator, not a replacement for Soroban's
Wasm host. It gives contract authors fast unit tests for language semantics,
authorization requirements, instance storage, and emitted events. A failed
invocation restores storage and events, including linked contracts from that
call. Testnet or a native Soroban host remains the source of truth for
integration testing.
"""

import copy
import hashlib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Dict, Iterable, List, Mapping, Optional, Tuple, Union

from . import ir
from .compiler import CompilationResult, compile_source
from .model import (
    EnumType,
    MapType,
    StructType,
    ValueType,
    VecType,
    VEC_ELEMENT_TYPES,
    is_vec_type,
    vec_element,
)


NativeValue = Union[None, bool, int, str, bytes, list, tuple, Dict]


class InvocationError(Exception):
    """Base class for deterministic contract-test failures."""


class AuthorizationError(InvocationError):
    """Raised when a contract requires an address absent from invocation auth."""


class StorageMissingError(InvocationError):
    """Raised when a typed storage get references a missing key."""


class ContractError(InvocationError):
    """Raised when a contract aborts with fail(). Storage and events roll back."""

    def __init__(self, code: int, error: str, case: str):
        self.code = code
        self.error = error
        self.case = case
        super().__init__(f"contract error {error}.{case} ({code})")


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
        self._persistent = {}
        self._temporary = {}
        self._ttl = []
        self.ledger_sequence = 1
        self.ledger_timestamp = 0
        self.ledger_version = 25
        self.network_id = bytes(32)
        self.contract_address = "CSELF"
        self.logs = []
        self.deployments = []
        self.uploads = []
        self.upgraded = None
        self._signatures = set()
        self._prng = 0x123456789ABCDEF
        self._events = []
        self._last_events = []
        self._authorized = set()
        self._contracts = {}
        self._transaction = None

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
    def persistent(self) -> Mapping[NativeValue, NativeValue]:
        return MappingProxyType({key: entry[0] for key, entry in self._persistent.items()})

    @property
    def temporary(self) -> Mapping[NativeValue, NativeValue]:
        return MappingProxyType({key: entry[0] for key, entry in self._temporary.items()})

    @property
    def ttl_extensions(self) -> Tuple[dict, ...]:
        return tuple(self._ttl)

    @property
    def events(self) -> Tuple[Event, ...]:
        return tuple(self._events)

    @property
    def last_events(self) -> Tuple[Event, ...]:
        return tuple(self._last_events)

    def allow_signature(self, key: bytes, message: bytes, signature: bytes) -> None:
        """Accept one ed25519 triple. The test host does not implement the curve."""
        self._signatures.add((key, message, signature))

    def clear_events(self) -> None:
        self._events.clear()
        self._last_events.clear()

    def register_contract(self, address: str, contract: "ContractTest") -> None:
        """Link an address to another deterministic test contract."""
        if not isinstance(address, str):
            raise InvocationError("contract address must be a string")
        self._contracts[address] = contract

    def invoke(self, name: str, *args: NativeValue, auth: Iterable[str] = (), **kwargs: NativeValue) -> NativeValue:
        return self._invoke(name, args, kwargs, auth, None)

    def _invoke(
        self,
        name: str,
        args: Tuple[NativeValue, ...],
        kwargs: Dict[str, NativeValue],
        auth: Iterable[str],
        transaction: Optional[List[tuple]],
    ) -> NativeValue:
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
        root = transaction is None
        if root:
            transaction = []
        self._authorized = set(auth)
        self._last_events = []
        self._transaction = transaction
        # Snapshot after clearing this call's event window so a failure restores
        # prior ledger state and drops events published by the aborted call.
        transaction.append((
            self,
            copy.deepcopy(self._storage),
            copy.deepcopy(self._persistent),
            copy.deepcopy(self._temporary),
            list(self._ttl),
            list(self._events),
            list(self._last_events),
            list(self.logs),
            list(self.deployments),
            list(self.uploads),
            self.upgraded,
        ))
        try:
            try:
                self._statements(function.body, variables)
            except _ReturnSignal as returned:
                _validate_native(returned.value, function.result, "return value")
                return returned.value
            if function.result is ValueType.VOID:
                return None
            raise InvocationError(f"{name}() completed without returning a value")
        except InvocationError:
            if root:
                _restore_transaction(transaction)
            raise
        finally:
            self._authorized = set()

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
            if isinstance(statement, ir.PopBack):
                vector = variables[statement.collection]
                if not isinstance(vector, (list, tuple)) or not vector:
                    raise InvocationError("Vec.pop() on an empty vector")
                variables[statement.target] = vector[-1]
                variables[statement.collection] = list(vector[:-1])
                continue
            if isinstance(statement, ir.Fail):
                raise ContractError(statement.code, statement.error, statement.case)
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
            if expression.op == "div":
                if right == 0:
                    raise InvocationError("integer division by zero")
                value = left // right
            else:
                value = {"add": left + right, "sub": left - right, "mul": left * right}[expression.op]
            if expression.type in {ValueType.I128, ValueType.U128}:
                try:
                    _validate_native(value, expression.type, "arithmetic result")
                except InvocationError as exc:
                    raise InvocationError(f"{expression.type.value} arithmetic overflow") from exc
                return value
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
            self._storage[_storage_key(values[0])] = (values[1], call.args[1].type)
            return None
        if call.op == "storage_has":
            return _storage_key(values[0]) in self._storage
        if call.op.startswith("storage_get"):
            return self._storage_get(self._storage, _storage_key(values[0]), call.type, "instance")
        if call.op == "storage_del":
            return self._storage_delete(self._storage, _storage_key(values[0]), "instance")
        tier = _storage_tier(call.op)
        if tier is not None:
            bucket, label, action = tier
            bucket = {"persistent": self._persistent, "temporary": self._temporary}[label]
            key = _storage_key(values[0])
            if action == "set":
                bucket[key] = (values[1], call.args[1].type)
                return None
            if action == "has":
                return key in bucket
            if action == "get":
                return self._storage_get(bucket, key, call.type, label)
            if action == "del":
                return self._storage_delete(bucket, key, label)
            if action == "extend":
                self._ttl.append({
                    "tier": label,
                    "key": key,
                    "threshold": values[1],
                    "extend_to": values[2],
                })
                return None
        if call.op == "extend_instance":
            self._ttl.append({"tier": "instance", "threshold": values[0], "extend_to": values[1]})
            return None
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
            result = target._invoke(function, tuple(args), {}, (), self._transaction)
            _validate_native(result, call.type, "cross-contract return value")
            return result
        if call.op == "u128_mul_div_floor":
            left, right, denominator = values
            if denominator == 0:
                raise InvocationError("u128.mul_div_floor division by zero")
            result = left * right // denominator
            if result > 2**128 - 1:
                raise InvocationError("u128.mul_div_floor result overflow")
            return result
        if call.op == "vec_len":
            return len(values[0])
        if call.op == "vec_get":
            vector, index = values
            if index < 0 or index >= len(vector):
                raise InvocationError(f"Vec index {index} is out of bounds")
            return vector[index]
        if call.op == "map_len":
            return len(values[0])
        if call.op == "map_has":
            return _storage_key(values[1]) in values[0]
        if call.op == "map_get":
            map_value, key = values
            key = _storage_key(key)
            if key not in map_value:
                raise InvocationError(f"Map key {key!r} was not found")
            return map_value[key]
        if call.op == "vec_new":
            return []
        if call.op == "map_new":
            return {}
        if call.op == "vec_push":
            _validate_native(values[1], vec_element(call.type), "Vec element")
            return list(values[0]) + [values[1]]
        if call.op == "vec_put":
            vector, index, item = values
            if index < 0 or index >= len(vector):
                raise InvocationError(f"Vec index {index} is out of bounds")
            _validate_native(item, vec_element(call.type), "Vec element")
            updated = list(vector)
            updated[index] = item
            return updated
        if call.op == "vec_insert":
            vector, index, item = values
            if index < 0 or index > len(vector):
                raise InvocationError(f"Vec index {index} is out of bounds")
            _validate_native(item, vec_element(call.type), "Vec element")
            updated = list(vector)
            updated.insert(index, item)
            return updated
        if call.op == "vec_del":
            vector, index = values
            if index < 0 or index >= len(vector):
                raise InvocationError(f"Vec index {index} is out of bounds")
            updated = list(vector)
            del updated[index]
            return updated
        if call.op == "map_put":
            updated = dict(values[0])
            updated[_storage_key(values[1])] = values[2]
            return updated
        if call.op == "map_del":
            key = _storage_key(values[1])
            if key not in values[0]:
                raise InvocationError(f"Map key {key!r} was not found")
            updated = dict(values[0])
            del updated[key]
            return updated
        if call.op == "struct_new":
            struct = call.type
            return {field.name: value for field, value in zip(struct.fields, values)}
        if call.op == "struct_field":
            field_name = values[1]
            if field_name not in values[0]:
                raise InvocationError(f"missing struct field {field_name!r}")
            return values[0][field_name]
        if call.op == "ledger_sequence":
            return self.ledger_sequence
        if call.op == "ledger_timestamp":
            return self.ledger_timestamp
        if call.op == "ledger_version":
            return self.ledger_version
        if call.op == "ledger_network":
            return self.network_id
        if call.op == "current_contract":
            return self.contract_address
        if call.op == "sha256":
            return hashlib.sha256(values[0]).digest()
        if call.op == "keccak256":
            return _keccak256(values[0])
        if call.op == "ed25519_verify":
            if tuple(values) not in self._signatures:
                raise InvocationError("ed25519 signature was not accepted by the test host")
            return None
        if call.op == "log":
            self.logs.append(values[0])
            return None
        if call.op == "string_len":
            return len(values[0].encode("utf-8"))
        if call.op == "bytes_len":
            return len(values[0])
        if call.op == "string_to_bytes":
            return values[0].encode("utf-8")
        if call.op == "bytes_to_string":
            try:
                return values[0].decode("utf-8")
            except UnicodeDecodeError as exc:
                raise InvocationError("Bytes.to_string() received invalid UTF-8") from exc
        if call.op == "bytes_slice":
            start, end = values[1], values[2]
            if start < 0 or end < start or end > len(values[0]):
                raise InvocationError("Bytes.slice() range is invalid")
            return values[0][start:end]
        if call.op == "bytes_append":
            return values[0] + values[1]
        if call.op == "prng_bytes":
            length = values[0]
            if length < 0 or length > 256:
                raise InvocationError("prng.bytes() length is out of range")
            return bytes(_next_prng(self) & 0xFF for _ in range(length))
        if call.op == "prng_u64":
            low, high = values
            if low > high:
                raise InvocationError("prng.u64() range is empty")
            return low + (_next_prng(self) % (high - low + 1))
        if call.op == "require_auth_for":
            if values[0] not in self._authorized:
                raise AuthorizationError(f"missing authorization for {values[0]!r}")
            return None
        if call.op in {"deploy", "deploy_constructor"}:
            address = "C" + hashlib.sha256(repr(values).encode("utf-8")).hexdigest()[:16]
            self.deployments.append({"address": address, "wasm_hash": values[0], "salt": values[1], "args": values[2:]})
            return address
        if call.op == "upload_wasm":
            digest = hashlib.sha256(values[0]).digest()
            self.uploads.append(digest)
            return digest
        if call.op == "upgrade":
            self.upgraded = values[0]
            return None
        if call.op == "deploy_asset":
            address = "A" + hashlib.sha256(values[0]).hexdigest()[:16]
            self.deployments.append({"address": address, "asset": values[0]})
            return address
        raise AssertionError(call.op)

    def _storage_get(self, bucket, key, value_type, label: str):
        if key not in bucket:
            raise StorageMissingError(f"missing {label} storage key {key!r}")
        result, stored_type = bucket[key]
        if stored_type != value_type:
            raise InvocationError(
                f"stored value is {stored_type.value}, not the requested {value_type.value}"
            )
        _validate_native(result, value_type, "stored value")
        return result

    def _storage_delete(self, bucket, key, label: str):
        if key not in bucket:
            raise StorageMissingError(f"missing {label} storage key {key!r}")
        del bucket[key]
        return None


def _storage_key(value):
    """Make struct and collection values usable as storage and map keys.

    The test host compares those keys by value. Dicts and lists are not
    hashable, so they are stored as nested tuples. Scalars stay unchanged,
    which keeps Address, Symbol, and integer keys identical for callers.
    """
    if isinstance(value, dict):
        return ("struct", tuple(sorted((name, _storage_key(item)) for name, item in value.items())))
    if isinstance(value, list):
        return ("vec", tuple(_storage_key(item) for item in value))
    return value


def _next_prng(contract: ContractTest) -> int:
    value = contract._prng & ((1 << 64) - 1)
    value ^= (value << 13) & ((1 << 64) - 1)
    value ^= value >> 7
    value ^= (value << 17) & ((1 << 64) - 1)
    contract._prng = value
    return value


def _keccak256(data: bytes) -> bytes:
    """Keccak-256, the function Soroban exposes as compute_hash_keccak256."""
    state = [0] * 25
    rate = 136
    padded = bytearray(data)
    padded.append(0x01)
    while (len(padded) % rate) != rate - 1:
        padded.append(0)
    padded.append(0x80)
    rotations = [
        [0, 36, 3, 41, 18],
        [1, 44, 10, 45, 2],
        [62, 6, 43, 15, 61],
        [28, 55, 25, 21, 56],
        [27, 20, 39, 8, 14],
    ]
    constants = [
        0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
        0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
        0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
        0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
        0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
        0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
    ]
    mask = (1 << 64) - 1

    def rotate(value: int, shift: int) -> int:
        value &= mask
        return ((value << shift) | (value >> (64 - shift))) & mask if shift else value

    for offset in range(0, len(padded), rate):
        block = padded[offset:offset + rate]
        for index in range(rate // 8):
            state[index] ^= int.from_bytes(block[index * 8:(index + 1) * 8], "little")
        for constant in constants:
            columns = [state[lane] ^ state[lane + 5] ^ state[lane + 10] ^ state[lane + 15] ^ state[lane + 20] for lane in range(5)]
            rotated = [columns[(lane - 1) % 5] ^ rotate(columns[(lane + 1) % 5], 1) for lane in range(5)]
            for lane in range(25):
                state[lane] ^= rotated[lane % 5]
            lanes = [rotate(state[x + 5 * y], rotations[x][y]) for y in range(5) for x in range(5)]
            permuted = [0] * 25
            for y in range(5):
                for x in range(5):
                    permuted[y + 5 * ((2 * x + 3 * y) % 5)] = lanes[x + 5 * y]
            for y in range(5):
                for x in range(5):
                    current = permuted[x + 5 * y]
                    state[x + 5 * y] = current ^ ((~permuted[((x + 1) % 5) + 5 * y]) & permuted[((x + 2) % 5) + 5 * y])
            state[0] ^= constant
    output = bytearray()
    for lane in state[: rate // 8]:
        output += lane.to_bytes(8, "little")
    return bytes(output[:32])


def _storage_tier(op: str):
    if op.startswith("pstorage_"):
        return "persistent", "persistent", op[len("pstorage_"):]
    if op.startswith("tstorage_"):
        return "temporary", "temporary", op[len("tstorage_"):]
    return None


def _restore_transaction(transaction: List[tuple]) -> None:
    for contract, storage, persistent, temporary, ttl, events, last_events, logs, deployments, uploads, upgraded in reversed(transaction):
        contract._storage = storage
        contract._persistent = persistent
        contract._temporary = temporary
        contract._ttl = ttl
        contract._events = events
        contract._last_events = last_events
        contract.logs = logs
        contract.deployments = deployments
        contract.uploads = uploads
        contract.upgraded = upgraded


def _wrap_integer(value: int, value_type: ValueType) -> int:
    bits = {
        ValueType.I32: 32,
        ValueType.U32: 32,
        ValueType.I64: 64,
        ValueType.U64: 64,
        ValueType.I128: 128,
        ValueType.U128: 128,
    }[value_type]
    value %= 2**bits
    if value_type in {ValueType.I32, ValueType.I64, ValueType.I128} and value >= 2 ** (bits - 1):
        value -= 2**bits
    return value


def _validate_native(value: NativeValue, value_type: ValueType, label: str) -> None:
    if value_type is ValueType.VOID:
        valid = value is None
    elif value_type is ValueType.BOOL:
        valid = isinstance(value, bool)
    elif value_type in {
        ValueType.I32, ValueType.U32, ValueType.I64, ValueType.U64,
        ValueType.I128, ValueType.U128,
    }:
        valid = isinstance(value, int) and not isinstance(value, bool)
        if valid:
            bounds = {
                ValueType.I32: (-(2**31), 2**31 - 1),
                ValueType.U32: (0, 2**32 - 1),
                ValueType.I64: (-(2**63), 2**63 - 1),
                ValueType.U64: (0, 2**64 - 1),
                ValueType.I128: (-(2**127), 2**127 - 1),
                ValueType.U128: (0, 2**128 - 1),
            }
            lower, upper = bounds[value_type]
            valid = lower <= value <= upper
    elif value_type in {ValueType.ADDRESS, ValueType.STRING, ValueType.SYMBOL}:
        valid = isinstance(value, str)
    elif value_type is ValueType.BYTES:
        valid = isinstance(value, bytes)
    elif is_vec_type(value_type):
        valid = isinstance(value, (list, tuple))
        if valid:
            try:
                for index, item in enumerate(value):
                    _validate_native(item, vec_element(value_type), f"{label}[{index}]")
            except InvocationError:
                raise
    elif isinstance(value_type, MapType):
        valid = isinstance(value, dict)
        if valid:
            for key, item in value.items():
                _validate_native(key, value_type.key, f"{label} key")
                _validate_native(item, value_type.value_type, f"{label}[{key!r}]")
    elif isinstance(value_type, EnumType):
        valid = isinstance(value, int) and not isinstance(value, bool) and any(
            case.value == value for case in value_type.cases
        )
    elif isinstance(value_type, StructType):
        valid = isinstance(value, dict) and set(value) == {field.name for field in value_type.fields}
        if valid:
            for field in value_type.fields:
                _validate_native(value[field.name], field.type, f"{label}.{field.name}")
    else:
        valid = False
    if not valid:
        raise InvocationError(f"{label} is not a valid {value_type.value}")
