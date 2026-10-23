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
    U256 = "u256"
    I256 = "i256"
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
    VEC_U256 = "Vec[u256]"
    VEC_I256 = "Vec[i256]"
    VEC_BOOL = "Vec[boolean]"
    VEC_ADDRESS = "Vec[Address]"
    VEC_SYMBOL = "Vec[Symbol]"
    VEC_STRING = "Vec[String]"
    VEC_BYTES = "Vec[Bytes]"
    VAL = "Val"
    VOID = "void"


VEC_TYPES_BY_ELEMENT = {
    ValueType.I32: ValueType.VEC_I32,
    ValueType.U32: ValueType.VEC_U32,
    ValueType.I64: ValueType.VEC_I64,
    ValueType.U64: ValueType.VEC_U64,
    ValueType.I128: ValueType.VEC_I128,
    ValueType.U128: ValueType.VEC_U128,
    ValueType.U256: ValueType.VEC_U256,
    ValueType.I256: ValueType.VEC_I256,
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


@dataclass(frozen=True)
class BytesNType:
    """A byte string whose length is fixed by the contract spec."""

    size: int

    @property
    def value(self) -> str:
        return f"BytesN[{self.size}]"


@dataclass(frozen=True)
class OptionType:
    inner: "ContractType"

    @property
    def value(self) -> str:
        return f"Option[{self.inner.value}]"


@dataclass(frozen=True)
class ResultType:
    ok: "ContractType"
    err: "ContractType"

    @property
    def value(self) -> str:
        return f"Result[{self.ok.value}, {self.err.value}]"


@dataclass(frozen=True)
class TupleType:
    elements: Tuple["ContractType", ...]

    @property
    def value(self) -> str:
        return "Tuple[" + ", ".join(item.value for item in self.elements) + "]"


@dataclass(frozen=True)
class UnionCase:
    name: str
    types: Tuple["ContractType", ...]
    doc: str = ""


@dataclass(frozen=True)
class UnionType:
    """A data-carrying enum stored as a symbol or a vec of symbol plus payload."""

    name: str
    cases: Tuple[UnionCase, ...]
    doc: str = ""

    @property
    def value(self) -> str:
        return self.name


ContractType = Union[
    ValueType, MapType, StructType, EnumType, VecType, BytesNType,
    OptionType, ResultType, TupleType, UnionType,
]


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
        ValueType.U256,
        ValueType.I256,
    }


def is_bytes_type(value_type: ContractType) -> bool:
    return value_type is ValueType.BYTES or isinstance(value_type, BytesNType)


def is_object_type(value_type: ContractType) -> bool:
    return (
        isinstance(value_type, (MapType, StructType, VecType, BytesNType, OptionType, ResultType, TupleType, UnionType))
        or value_type in {
            ValueType.ADDRESS,
            ValueType.BYTES,
            ValueType.I128,
            ValueType.STRING,
            ValueType.SYMBOL,
            ValueType.U128,
            ValueType.U256,
            ValueType.I256,
            ValueType.VAL,
        }
        | set(VEC_ELEMENT_TYPES)
    )


# Official points use 96-byte G1 and 192-byte G2 values. The cap is a
# compiler limit, not a protocol limit on the Bytes object itself.
BYTESN_MAX = 1024


def vec_element_accepts(element: ContractType, actual: ContractType) -> bool:
    """A ``Vec[Bytes]`` element may be ``Bytes`` or ``BytesN``."""
    if actual == element:
        return True
    return element is ValueType.BYTES and is_bytes_type(actual)


# Protocol-25 curve host functions. Each entry is the env export, argument
# kinds, and result type. Protocol 26 scalar and on-curve checks are omitted
# because this compiler targets protocol 25.
_B = "bytes"
_U = "u256"
_L = "u64"
_VB = "vec_bytes"
_VU = "vec_u256"
CURVE_HOST = {
    "bls12_381_check_g1_is_in_subgroup": ("4", (_B,), ValueType.BOOL),
    "bls12_381_g1_add": ("5", (_B, _B), ValueType.BYTES),
    "bls12_381_g1_mul": ("6", (_B, _U), ValueType.BYTES),
    "bls12_381_g1_msm": ("7", (_VB, _VU), ValueType.BYTES),
    "bls12_381_map_fp_to_g1": ("8", (_B,), ValueType.BYTES),
    "bls12_381_hash_to_g1": ("9", (_B, _B), ValueType.BYTES),
    "bls12_381_check_g2_is_in_subgroup": ("a", (_B,), ValueType.BOOL),
    "bls12_381_g2_add": ("b", (_B, _B), ValueType.BYTES),
    "bls12_381_g2_mul": ("c", (_B, _U), ValueType.BYTES),
    "bls12_381_g2_msm": ("d", (_VB, _VU), ValueType.BYTES),
    "bls12_381_map_fp2_to_g2": ("e", (_B,), ValueType.BYTES),
    "bls12_381_hash_to_g2": ("f", (_B, _B), ValueType.BYTES),
    "bls12_381_multi_pairing_check": ("g", (_VB, _VB), ValueType.BOOL),
    "bls12_381_fr_add": ("h", (_U, _U), ValueType.U256),
    "bls12_381_fr_sub": ("i", (_U, _U), ValueType.U256),
    "bls12_381_fr_mul": ("j", (_U, _U), ValueType.U256),
    "bls12_381_fr_pow": ("k", (_U, _L), ValueType.U256),
    "bls12_381_fr_inv": ("l", (_U,), ValueType.U256),
    "bn254_g1_add": ("m", (_B, _B), ValueType.BYTES),
    "bn254_g1_mul": ("n", (_B, _U), ValueType.BYTES),
    "bn254_multi_pairing_check": ("o", (_VB, _VB), ValueType.BOOL),
}


def curve_arg_matches(kind: str, actual: ContractType) -> bool:
    if kind == "bytes":
        return is_bytes_type(actual)
    if kind == "u256":
        return actual is ValueType.U256
    if kind == "u64":
        return actual is ValueType.U64
    if kind == "vec_bytes":
        return is_vec_type(actual) and is_bytes_type(vec_element(actual))
    if kind == "vec_u256":
        return is_vec_type(actual) and vec_element(actual) is ValueType.U256
    return False


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
    unions: Tuple[UnionType, ...] = ()
    source_name: Optional[str] = None
