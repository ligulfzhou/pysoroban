"""Typed, backend-independent intermediate representation for PySoroban."""

from dataclasses import dataclass
from typing import Optional, Tuple, Union

from .model import ContractType, EnumType, ErrorEnum, Event, Parameter, StructType, UnionType, ValueType


@dataclass(frozen=True)
class Constant:
    value: Optional[Union[int, bool, str, bytes]]
    type: ValueType


@dataclass(frozen=True)
class Local:
    name: str
    type: ContractType


@dataclass(frozen=True)
class Unary:
    op: str
    operand: "Expression"
    type: ValueType


@dataclass(frozen=True)
class Binary:
    op: str
    left: "Expression"
    right: "Expression"
    type: ValueType


@dataclass(frozen=True)
class Compare:
    op: str
    left: "Expression"
    right: "Expression"
    type: ValueType = ValueType.BOOL


@dataclass(frozen=True)
class HostCall:
    op: str
    args: Tuple["Expression", ...]
    type: ContractType


Expression = Union[Constant, Local, Unary, Binary, Compare, HostCall]


@dataclass(frozen=True)
class Return:
    value: Expression


@dataclass(frozen=True)
class SetLocal:
    name: str
    value: Expression


@dataclass(frozen=True)
class If:
    test: Expression
    body: Tuple["Statement", ...]
    otherwise: Tuple["Statement", ...]


@dataclass(frozen=True)
class ForRange:
    variable: str
    start: Expression
    stop: Expression
    stop_local: str
    body: Tuple["Statement", ...]


@dataclass(frozen=True)
class Drop:
    value: Expression


@dataclass(frozen=True)
class Fail:
    """Abort the invocation with a Soroban contract error."""

    code: int
    error: str
    case: str


@dataclass(frozen=True)
class PopBack:
    """Remove the last element of a local Vec and bind that element."""

    collection: str
    target: str


Statement = Union[Return, SetLocal, If, ForRange, Drop, Fail, PopBack]


@dataclass(frozen=True)
class Function:
    name: str
    params: Tuple[Parameter, ...]
    result: ContractType
    locals: Tuple[Parameter, ...]
    body: Tuple[Statement, ...]
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
