from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class ValueType(str, Enum):
    I32 = "i32"
    BOOL = "boolean"
    ADDRESS = "Address"
    VOID = "void"


@dataclass(frozen=True)
class Parameter:
    name: str
    type: ValueType


@dataclass(frozen=True)
class Function:
    name: str
    params: Tuple[Parameter, ...]
    result: ValueType
    node: object
    doc: str = ""


@dataclass(frozen=True)
class Contract:
    name: str
    functions: Tuple[Function, ...]
    source_name: Optional[str] = None
