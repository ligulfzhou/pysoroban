from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .frontend import parse_contract
from .model import Contract
from .wasm import emit_module


@dataclass(frozen=True)
class CompilationResult:
    contract: Contract
    wasm: bytes


def compile_source(source: str, source_name: Optional[str] = None, protocol: int = 25) -> CompilationResult:
    contract = parse_contract(source, source_name)
    return CompilationResult(contract, emit_module(contract, protocol))


def compile_file(
    source_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    protocol: int = 25,
) -> CompilationResult:
    source_path = Path(source_path)
    result = compile_source(source_path.read_text(encoding="utf-8"), str(source_path), protocol)
    if output_path is not None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(result.wasm)
    return result

