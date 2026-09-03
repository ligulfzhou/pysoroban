import struct

from .model import Contract, ValueType, VEC_ELEMENT_TYPES


SPEC_TYPES = {
    ValueType.ADDRESS: 19,
    ValueType.BOOL: 1,
    ValueType.VOID: 2,
    ValueType.I32: 5,
    ValueType.U32: 4,
    ValueType.U64: 6,
    ValueType.I64: 7,
    ValueType.BYTES: 14,
    ValueType.STRING: 16,
    ValueType.SYMBOL: 17,
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


def spec_type(value_type: ValueType) -> bytes:
    if value_type in VEC_ELEMENT_TYPES:
        return u32(1002) + spec_type(VEC_ELEMENT_TYPES[value_type])
    return u32(SPEC_TYPES[value_type])


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
            entries += spec_type(param.type)
        if function.result is ValueType.VOID:
            entries += u32(0)
        else:
            entries += u32(1)
            entries += spec_type(function.result)
    for event in contract.events:
        entries += u32(5)  # SC_SPEC_ENTRY_EVENT_V0
        entries += xdr_string(event.doc)
        entries += xdr_string("")  # library
        entries += xdr_string(event.name)
        entries += u32(1) + xdr_string(event.prefix)
        entries += u32(len(event.fields))
        for field in event.fields:
            entries += xdr_string(field.doc)
            entries += xdr_string(field.name)
            entries += spec_type(field.type)
            entries += u32(1 if field.topic else 0)
        entries += u32(0)  # SC_SPEC_EVENT_DATA_FORMAT_SINGLE_VALUE
    return bytes(entries)
