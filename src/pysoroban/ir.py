"""Typed, backend-independent intermediate representation for PySoroban."""

from dataclasses import dataclass
from typing import Optional, Tuple, Union

from .model import Event, Parameter, ValueType


@dataclass(frozen=True)
class Constant:
    value: Optional[Union[int, bool, str, bytes]]
    type: ValueType


@dataclass(frozen=True)
class Local:
    name: str
    type: ValueType


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
    type: ValueType


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


Statement = Union[Return, SetLocal, If, ForRange, Drop]


@dataclass(frozen=True)
class Function:
    name: str
    params: Tuple[Parameter, ...]
    result: ValueType
    locals: Tuple[Parameter, ...]
    body: Tuple[Statement, ...]
    doc: str = ""


@dataclass(frozen=True)
class Contract:
    name: str
    functions: Tuple[Function, ...]
    events: Tuple[Event, ...] = ()
    source_name: Optional[str] = None
