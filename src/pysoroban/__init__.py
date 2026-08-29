"""PySoroban language markers and compiler API.

The decorators and type names make contract source valid Python for editor
support. The compiler reads the source as an AST; contracts are never executed
by the Python runtime.
"""

from .compiler import CompilationResult, compile_file, compile_source


class i32:
    """Signed 32-bit Soroban contract value."""


class boolean:
    """Soroban boolean contract value."""


class Address:
    """A Stellar account or contract address host object."""

    def require_auth(self) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _InstanceStorage:
    def get_i32(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def get_bool(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def has(self, key):
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")

    def set(self, key, value) -> None:
        raise RuntimeError("PySoroban contract markers cannot be executed in Python")


class _Storage:
    instance = _InstanceStorage()


storage = _Storage()


def contract(cls):
    return cls


def public(fn):
    return fn


__all__ = [
    "CompilationResult",
    "Address",
    "boolean",
    "compile_file",
    "compile_source",
    "contract",
    "i32",
    "public",
    "storage",
]
