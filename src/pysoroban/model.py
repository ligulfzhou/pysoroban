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
class StructField:
    name: str
    type: "ContractType"
    doc: str = ""


@dataclass(frozen=True)
class StructType:
    """A named product type stored as a Soroban map of field symbols."""

    name: str
    fields: Tuple[StructField, ...]
    doc: str = ""

    @property
    def value(self) -> str:
        return self.name


@dataclass(frozen=True)
class EnumCase:
    name: str
    value: int
    doc: str = ""


@dataclass(frozen=True)
class EnumType:
    """A named integer enum stored as a Soroban u32."""

    name: str
    cases: Tuple[EnumCase, ...]
    doc: str = ""

    @property
    def value(self) -> str:
        return self.name


@dataclass(frozen=True)
class VecType:
    """A vector whose element is a user-defined struct or enum."""

    element: "ContractType"

    @property
    def value(self) -> str:
        return f"Vec[{self.element.value}]"


@dataclass(frozen=True)
class MapType:
    """A homogeneous Soroban map type carried through the typed pipeline."""

    key: "ContractType"
    value_type: "ContractType"

    @property
    def value(self) -> str:
        return f"Map[{self.key.value}, {self.value_type.value}]"


ContractType = Union[ValueType, MapType, StructType, EnumType, VecType]


def is_vec_type(value_type: ContractType) -> bool:
    return isinstance(value_type, VecType) or value_type in VEC_ELEMENT_TYPES


def vec_element(value_type: ContractType) -> ContractType:
    if isinstance(value_type, VecType):
        return value_type.element
    return VEC_ELEMENT_TYPES[value_type]


def is_map_type(value_type: ContractType) -> bool:
    return isinstance(value_type, MapType)


def is_collection(value_type: ContractType) -> bool:
    return is_vec_type(value_type) or is_map_type(value_type)


def is_integer_type(value_type: ContractType) -> bool:
    return value_type in {
        ValueType.I32,
        ValueType.U32,
        ValueType.I64,
        ValueType.U64,
        ValueType.I128,
        ValueType.U128,
    }


def is_object_type(value_type: ContractType) -> bool:
    return (
        isinstance(value_type, (MapType, StructType, VecType))
        or value_type in {
            ValueType.ADDRESS,
            ValueType.BYTES,
            ValueType.I128,
            ValueType.STRING,
            ValueType.SYMBOL,
            ValueType.U128,
        }
        | set(VEC_ELEMENT_TYPES)
    )


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
class ErrorCase:
    name: str
    value: int
    doc: str = ""


@dataclass(frozen=True)
class ErrorEnum:
    """A Soroban contract-error enum recorded in the contract specification."""

    name: str
    cases: Tuple[ErrorCase, ...]
    doc: str = ""


@dataclass(frozen=True)
class Contract:
    name: str
    functions: Tuple[Function, ...]
    events: Tuple[Event, ...] = ()
    errors: Tuple[ErrorEnum, ...] = ()
    structs: Tuple[StructType, ...] = ()
    enums: Tuple[EnumType, ...] = ()
    source_name: Optional[str] = None
