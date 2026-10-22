"""PySoroban language markers and compiler API.

The decorators and type names make contract source valid Python for editor
support. The compiler reads the source as an AST; contracts are never executed
by the Python runtime.
"""

__version__ = "0.19.0a2"

from .compiler import CompilationResult, check_file, check_source, compile_file, compile_source
from .abi import contract_abi
from .artifact import ArtifactError, inspect_wasm, inspect_wasm_file, validate_wasm, validate_wasm_file


class i32:
    """Signed 32-bit Soroban contract value."""


class u32:
    """Unsigned 32-bit Soroban contract value."""


class i64:
    """Signed 64-bit Soroban contract value."""


class u64:
    """Unsigned 64-bit Soroban contract value."""


class i128:
    """Signed 128-bit Soroban contract value."""


class u256:
    """Unsigned 256-bit Soroban contract value."""

    def to_be_bytes(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    @staticmethod
    def from_be_bytes(data):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class u128:
    """Unsigned 128-bit Soroban contract value."""

    @staticmethod
    def mul_div_floor(left, right, denominator):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class Val:
    """An untyped Soroban value."""


class boolean:
    """Soroban boolean contract value."""


class Address:
    """A Stellar account or contract address host object."""

    def require_auth(self) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def require_auth_for(self, *args) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def to_strkey(self) -> str:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_void(self, function, *args) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_i32(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_u32(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_i64(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_u64(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_i128(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_u128(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_u256(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_bool(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_address(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_symbol(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_string(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_bytes(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class Symbol:
    """Soroban symbol object."""


class String:
    """Soroban UTF-8 string object."""

    def to_bytes(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class BytesN:
    """A fixed-length byte string, written BytesN[32](value)."""

    def __class_getitem__(cls, length):
        return cls

    def __init__(self, value):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class Bytes:
    """Soroban byte sequence object."""

    def to_string(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def slice(self, start, end):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def append(self, other) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class Topic:
    """Mark a typed event field as a dynamic event topic."""

    @classmethod
    def __class_getitem__(cls, item):
        return item


class Vec:
    """A homogeneous Soroban vector type, written Vec[T]."""

    @classmethod
    def __class_getitem__(cls, item):
        return cls


class Map:
    """A homogeneous Soroban map type, written Map[K, V]."""

    @classmethod
    def __class_getitem__(cls, item):
        return cls


class _InstanceStorage:
    def get_i32(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_bool(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_u32(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_i64(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_u64(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_i128(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_u128(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_u256(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_symbol(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_string(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_bytes(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_address(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get(self, key, value_type):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def has(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def set(self, key, value) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def remove(self, key) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def extend_ttl(self, *args) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Storage:
    instance = _InstanceStorage()
    persistent = _InstanceStorage()
    temporary = _InstanceStorage()


storage = _Storage()


class _Events:
    def publish(self, topic: Symbol, data) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


events = _Events()


class _Ledger:
    def sequence(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def max_live_until(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def timestamp(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def version(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def network_id(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Env:
    def current_contract_address(self):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Auth:
    def as_current_contract(self, contract, fn_name, argument):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Crypto:
    def sha256(self, value):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def keccak256(self, value):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def ed25519_verify(self, key, message, signature):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def __getattr__(self, name):
        from .model import CURVE_HOST
        if name not in CURVE_HOST:
            raise AttributeError(name)

        def _call(*_args):
            raise RuntimeError("PySoroban contract markers cannot be executed in Python")

        return _call


class _Prng:
    def bytes(self, length):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def u64(self, low, high):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Deploy:
    def contract(self, wasm_hash, salt):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def with_constructor(self, wasm_hash, salt, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def upload(self, wasm):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def upgrade(self, wasm_hash):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def asset(self, serialized_asset):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


ledger = _Ledger()
env = _Env()
auth = _Auth()
crypto = _Crypto()
prng = _Prng()
deploy = _Deploy()


def log(message):
    raise RuntimeError("PySoroban contract markers cannot be executed in Python")


def contract(cls):
    return cls


def error(cls):
    return cls


def struct(cls):
    return cls


def enum(cls):
    return cls


def union(cls):
    return cls


class Option:
    """An optional value. `Option.none()` needs an `Option[T]` annotation."""

    @staticmethod
    def none():
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    @staticmethod
    def some(value):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class Result:
    """A success or a u32 error code, written Result[T, u32].ok / .err."""

    def __class_getitem__(cls, item):
        return cls

    @staticmethod
    def ok(value):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    @staticmethod
    def err(error_case):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class Tuple:
    """A fixed heterogeneous vector, written Tuple[A, B](a, b)."""

    def __class_getitem__(cls, item):
        return cls


def event(cls):
    return cls


def fail(error_case):
    raise RuntimeError("PySoroban contract markers cannot be executed in Python")


def to_xdr(value):
    raise RuntimeError("PySoroban contract markers cannot be executed in Python")


def public(fn):
    return fn


__all__ = [
    "ArtifactError",
    "CompilationResult",
    "Address",
    "auth",
    "Bytes",
    "BytesN",
    "String",
    "Symbol",
    "Topic",
    "Vec",
    "Map",
    "Option",
    "Result",
    "Tuple",
    "Val",
    "boolean",
    "check_file",
    "check_source",
    "compile_file",
    "compile_source",
    "crypto",
    "deploy",
    "env",
    "ledger",
    "log",
    "prng",
    "contract",
    "contract_abi",
    "enum",
    "error",
    "event",
    "struct",
    "fail",
    "events",
    "i32",
    "i64",
    "i128",
    "inspect_wasm",
    "inspect_wasm_file",
    "public",
    "storage",
    "to_xdr",
    "u32",
    "u64",
    "u128",
    "union",
    "u256",
    "validate_wasm",
    "validate_wasm_file",
]
