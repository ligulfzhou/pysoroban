import struct

from .model import Contract, ValueType


SPEC_TYPES = {
    ValueType.ADDRESS: 19,
    ValueType.BOOL: 1,
    ValueType.VOID: 2,
    ValueType.I32: 5,
}


def u32(value: int) -> bytes:
    return struct.pack(">I", value)


def xdr_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    padding = b"\x00" * ((-len(raw)) % 4)
    return u32(len(raw)) + raw + padding


def environment_metadata(protocol: int) -> bytes:
    # Stream containing one SCEnvMetaEntry: kind, protocol, pre-release.
    return u32(0) + u32(protocol) + u32(0)


def contract_spec(contract: Contract) -> bytes:
    entries = bytearray()
    for function in contract.functions:
        entries += u32(0)  # SC_SPEC_ENTRY_FUNCTION_V0
        entries += xdr_string(function.doc)
        entries += xdr_string(function.name)
        entries += u32(len(function.params))
        for param in function.params:
            entries += xdr_string("")
            entries += xdr_string(param.name)
            entries += u32(SPEC_TYPES[param.type])
        if function.result is ValueType.VOID:
            entries += u32(0)
        else:
            entries += u32(1)
            entries += u32(SPEC_TYPES[function.result])
    return bytes(entries)
