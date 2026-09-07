from typing import Optional


class CompileError(Exception):
    """A source error with an optional source location."""

    def __init__(
        self,
        message: str,
        line: Optional[int] = None,
        column: Optional[int] = None,
        source_name: Optional[str] = None,
    ):
        self.message = message
        self.line = line
        self.column = column
        self.source_name = source_name
        if source_name:
            location = source_name
            if line is not None:
                location += f":{line}"
            if line is not None and column is not None:
                location += f":{column + 1}"
            rendered = f"{location}: {message}"
        else:
            location = ""
            if line is not None:
                location = f" at line {line}"
                if column is not None:
                    location += f", column {column + 1}"
            rendered = message + location
        super().__init__(rendered)

    def with_source(self, source_name: str) -> "CompileError":
        return CompileError(self.message, self.line, self.column, source_name)


def fail(node, message: str):
    raise CompileError(message, getattr(node, "lineno", None), getattr(node, "col_offset", None))
