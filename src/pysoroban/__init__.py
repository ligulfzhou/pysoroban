"""PySoroban language markers and compiler API.

The decorators and type names make contract source valid Python for editor
support. The compiler reads the source as an AST; contracts are never executed
by the Python runtime.
"""

from .compiler import CompilationResult, check_file, check_source, compile_file, compile_source
from .abi import contract_abi


class i32:
    """Signed 32-bit Soroban contract value."""


class u32:
    """Unsigned 32-bit Soroban contract value."""


class i64:
    """Signed 64-bit Soroban contract value."""


class u64:
    """Unsigned 64-bit Soroban contract value."""


class boolean:
    """Soroban boolean contract value."""


class Address:
    """A Stellar account or contract address host object."""

    def require_auth(self) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_i32(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_u32(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_i64(self, function, *args):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def call_u64(self, function, *args):
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


class Bytes:
    """Soroban byte sequence object."""


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

    def get_symbol(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_string(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_bytes(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def has(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def set(self, key, value) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Storage:
    instance = _InstanceStorage()


storage = _Storage()


class _Events:
    def publish(self, topic: Symbol, data) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


events = _Events()


def contract(cls):
    return cls


def event(cls):
    return cls


def public(fn):
    return fn


__all__ = [
    "CompilationResult",
    "Address",
    "Bytes",
    "String",
    "Symbol",
    "Topic",
    "Vec",
    "boolean",
    "check_file",
    "check_source",
    "compile_file",
    "compile_source",
    "contract",
    "contract_abi",
    "event",
    "events",
    "i32",
    "i64",
    "public",
    "storage",
    "u32",
    "u64",
]
