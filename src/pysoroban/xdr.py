import struct

from .model import (
    BytesNType,
    Contract,
    EnumType,
    MapType,
    OptionType,
    ResultType,
    StructType,
    TupleType,
    UnionType,
    ValueType,
    VecType,
    VEC_ELEMENT_TYPES,
)


SPEC_TYPES = {
    ValueType.ADDRESS: 19,
    ValueType.BOOL: 1,
    ValueType.VOID: 2,
    ValueType.I32: 5,
    ValueType.U32: 4,
    ValueType.U64: 6,
    ValueType.I64: 7,
    ValueType.U128: 10,
    ValueType.I128: 11,
    ValueType.U256: 12,
    ValueType.BYTES: 14,
    ValueType.STRING: 16,
    ValueType.SYMBOL: 17,
    ValueType.VAL: 0,
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


def spec_type(value_type) -> bytes:
    if isinstance(value_type, MapType):
        return u32(1004) + spec_type(value_type.key) + spec_type(value_type.value_type)
    if isinstance(value_type, VecType):
        return u32(1002) + spec_type(value_type.element)
    if isinstance(value_type, BytesNType):
        return u32(1006) + u32(value_type.size)
    if isinstance(value_type, OptionType):
        return u32(1000) + spec_type(value_type.inner)
    if isinstance(value_type, ResultType):
        return u32(1001) + spec_type(value_type.ok) + spec_type(value_type.err)
    if isinstance(value_type, TupleType):
        return u32(1005) + u32(len(value_type.elements)) + b"".join(
            spec_type(item) for item in value_type.elements
        )
    if isinstance(value_type, UnionType):
        return u32(2000) + xdr_string(value_type.name)
    if isinstance(value_type, (StructType, EnumType)):
        return u32(2000) + xdr_string(value_type.name)
    if value_type in VEC_ELEMENT_TYPES:
        return u32(1002) + spec_type(VEC_ELEMENT_TYPES[value_type])
    return u32(SPEC_TYPES[value_type])


def contract_spec(contract: Contract) -> bytes:
    entries = bytearray()
    for struct in getattr(contract, "structs", ()):
        entries += u32(1)  # SC_SPEC_ENTRY_UDT_STRUCT_V0
        entries += xdr_string(struct.doc)
        entries += xdr_string("")  # library
        entries += xdr_string(struct.name)
        entries += u32(len(struct.fields))
        for field in struct.fields:
            entries += xdr_string(field.doc)
            entries += xdr_string(field.name)
            entries += spec_type(field.type)
    for enum in getattr(contract, "enums", ()):
        entries += u32(3)  # SC_SPEC_ENTRY_UDT_ENUM_V0
        entries += xdr_string(enum.doc)
        entries += xdr_string("")  # library
        entries += xdr_string(enum.name)
        entries += u32(len(enum.cases))
        for case in enum.cases:
            entries += xdr_string(case.doc)
            entries += xdr_string(case.name)
            entries += u32(case.value)
    for union in getattr(contract, "unions", ()):
        entries += u32(2)  # SC_SPEC_ENTRY_UDT_UNION_V0
        entries += xdr_string(union.doc)
        entries += xdr_string("")
        entries += xdr_string(union.name)
        entries += u32(len(union.cases))
        for case in union.cases:
            if case.types:
                entries += u32(1)
                entries += xdr_string(case.doc)
                entries += xdr_string(case.name)
                entries += u32(len(case.types))
                for item in case.types:
                    entries += spec_type(item)
            else:
                entries += u32(0)
                entries += xdr_string(case.doc)
                entries += xdr_string(case.name)
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
    for error in getattr(contract, "errors", ()):
        entries += u32(4)  # SC_SPEC_ENTRY_UDT_ERROR_ENUM_V0
        entries += xdr_string(error.doc)
        entries += xdr_string("")  # library
        entries += xdr_string(error.name)
        entries += u32(len(error.cases))
        for case in error.cases:
            entries += xdr_string(case.doc)
            entries += xdr_string(case.name)
            entries += u32(case.value)
    return bytes(entries)
