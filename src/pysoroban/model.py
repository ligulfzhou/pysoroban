from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Union


class ValueType(str, Enum):
    I32 = "i32"
    U32 = "u32"
    I64 = "i64"
    U64 = "u64"
    I128 = "i128"
    U128 = "u128"
    BOOL = "boolean"
    ADDRESS = "Address"
    SYMBOL = "Symbol"
    STRING = "String"
    BYTES = "Bytes"
    VEC_I32 = "Vec[i32]"
    VEC_U32 = "Vec[u32]"
    VEC_I64 = "Vec[i64]"
    VEC_U64 = "Vec[u64]"
    VEC_I128 = "Vec[i128]"
    VEC_U128 = "Vec[u128]"
    VEC_BOOL = "Vec[boolean]"
    VEC_ADDRESS = "Vec[Address]"
    VEC_SYMBOL = "Vec[Symbol]"
    VEC_STRING = "Vec[String]"
    VEC_BYTES = "Vec[Bytes]"
    VOID = "void"


VEC_TYPES_BY_ELEMENT = {
    ValueType.I32: ValueType.VEC_I32,
    ValueType.U32: ValueType.VEC_U32,
    ValueType.I64: ValueType.VEC_I64,
    ValueType.U64: ValueType.VEC_U64,
    ValueType.I128: ValueType.VEC_I128,
    ValueType.U128: ValueType.VEC_U128,
    ValueType.BOOL: ValueType.VEC_BOOL,
    ValueType.ADDRESS: ValueType.VEC_ADDRESS,
    ValueType.SYMBOL: ValueType.VEC_SYMBOL,
    ValueType.STRING: ValueType.VEC_STRING,
    ValueType.BYTES: ValueType.VEC_BYTES,
}
VEC_ELEMENT_TYPES = {value: key for key, value in VEC_TYPES_BY_ELEMENT.items()}


@dataclass(frozen=True)
class MapType:
    """A homogeneous Soroban map type carried through the typed pipeline."""

    key: ValueType
    value_type: ValueType

    @property
    def value(self) -> str:
        return f"Map[{self.key.value}, {self.value_type.value}]"


ContractType = Union[ValueType, MapType]


def is_object_type(value_type: ContractType) -> bool:
    return isinstance(value_type, MapType) or value_type in {
        ValueType.ADDRESS,
        ValueType.BYTES,
        ValueType.I128,
        ValueType.STRING,
        ValueType.SYMBOL,
        ValueType.U128,
    } | set(VEC_ELEMENT_TYPES)


@dataclass(frozen=True)
class Parameter:
    name: str
    type: ContractType


@dataclass(frozen=True)
class Function:
    name: str
    params: Tuple[Parameter, ...]
    result: ContractType
    node: object
    doc: str = ""


@dataclass(frozen=True)
class EventField:
    name: str
    type: ContractType
    topic: bool
    doc: str = ""


@dataclass(frozen=True)
class Event:
    name: str
    prefix: str
    fields: Tuple[EventField, ...]
    doc: str = ""


@dataclass(frozen=True)
class Contract:
    name: str
    functions: Tuple[Function, ...]
    events: Tuple[Event, ...] = ()
    source_name: Optional[str] = None
