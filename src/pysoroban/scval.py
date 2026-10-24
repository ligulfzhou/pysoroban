"""Test-host encoding of contract values as Soroban ScVal XDR.

Generated Wasm calls the protocol `serialize_to_bytes` host function. This
module is the matching encoder for the Python test host. Addresses that are
not StrKey values become contract ids of SHA-256(the address string).
"""

import hashlib
import struct

from .model import BytesNType, EnumType, MapType, StructType, ValueType, is_vec_type, vec_element


def xdr_bytes(value, value_type) -> bytes:
    return _value(value, value_type)


def _u32(value: int) -> bytes:
    return struct.pack(">I", value)


def _i32(value: int) -> bytes:
    return struct.pack(">i", value)


def _u64(value: int) -> bytes:
    return struct.pack(">Q", value)


def _i64(value: int) -> bytes:
    return struct.pack(">q", value)


def _opaque(raw: bytes) -> bytes:
    return _u32(len(raw)) + raw + b"\x00" * ((-len(raw)) % 4)


def _value(value, value_type) -> bytes:
    if isinstance(value_type, EnumType) or value_type is ValueType.U32:
        return _u32(3) + _u32(value)
    if value_type is ValueType.BOOL:
        return _u32(0) + _u32(1 if value else 0)
    if value_type is ValueType.VOID:
        return _u32(1)
    if value_type is ValueType.I32:
        return _u32(4) + _i32(value)
    if value_type is ValueType.U64:
        return _u32(5) + _u64(value)
    if value_type is ValueType.I64:
        return _u32(6) + _i64(value)
    if value_type is ValueType.U128:
        return _u32(9) + _u64(value >> 64) + _u64(value & (2**64 - 1))
    if value_type is ValueType.I128:
        bits = value % 2**128
        hi = bits >> 64
        if hi >= 2**63:
            hi -= 2**64
        return _u32(10) + _i64(hi) + _u64(bits & (2**64 - 1))
    if value_type is ValueType.U256:
        parts = [(value >> shift) & (2**64 - 1) for shift in (192, 128, 64, 0)]
        return _u32(11) + b"".join(_u64(part) for part in parts)
    if value_type is ValueType.I256:
        bits = value % 2**256
        parts = [(bits >> shift) & (2**64 - 1) for shift in (192, 128, 64, 0)]
        hi = parts[0] - 2**64 if parts[0] >= 2**63 else parts[0]
        return _u32(12) + _i64(hi) + b"".join(_u64(part) for part in parts[1:])
    if value_type is ValueType.BYTES or isinstance(value_type, BytesNType):
        return _u32(13) + _opaque(value)
    if value_type is ValueType.STRING:
        return _u32(14) + _opaque(value.encode("utf-8"))
    if value_type is ValueType.SYMBOL:
        return _u32(15) + _opaque(value.encode("utf-8"))
    if is_vec_type(value_type):
        element = vec_element(value_type)
        body = b"".join(_value(item, element) for item in value)
        return _u32(16) + _u32(1) + _u32(len(value)) + body
    if isinstance(value_type, MapType):
        entries = sorted(value.items(), key=lambda item: _value(item[0], value_type.key))
        body = b"".join(
            _value(key, value_type.key) + _value(item, value_type.value_type)
            for key, item in entries
        )
        return _u32(17) + _u32(1) + _u32(len(entries)) + body
    if isinstance(value_type, StructType):
        fields = sorted(value_type.fields, key=lambda field: field.name.encode("utf-8"))
        body = b"".join(
            _value(field.name, ValueType.SYMBOL) + _value(value[field.name], field.type)
            for field in fields
        )
        return _u32(17) + _u32(1) + _u32(len(fields)) + body
    if value_type is ValueType.ADDRESS:
        # SCVal address, SCAddress contract, 32-byte contract id.
        return _u32(18) + _u32(1) + hashlib.sha256(value.encode("utf-8")).digest()
    raise AssertionError(value_type)
