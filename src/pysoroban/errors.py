from typing import Optional


class CompileError(Exception):
    """A source error with an optional source location."""

    def __init__(self, message: str, line: Optional[int] = None, column: Optional[int] = None):
        self.message = message
        self.line = line
        self.column = column
        location = ""
        if line is not None:
            location = f" at line {line}"
            if column is not None:
                location += f", column {column + 1}"
        super().__init__(message + location)


def fail(node, message: str):
    raise CompileError(message, getattr(node, "lineno", None), getattr(node, "col_offset", None))
