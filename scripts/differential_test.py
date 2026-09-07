"""Compare Typed IR execution with the generated Wasm for deterministic cases."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from pysoroban import compile_source
from pysoroban.testing import ContractTest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "wasm_runner.mjs"

NUMERIC_SOURCE = """
from pysoroban import boolean, contract, i32, i64, public, u32, u64

@contract
class Numeric:
    @public
    def choose(self, flag: boolean, left: i32, right: i32) -> i32:
        if flag:
            return left
        return right

    @public
    def difference(self, left: i32, right: i32) -> i32:
        return left - right

    @public
    def product(self, left: i32, right: i32) -> i32:
        return left * right

    @public
    def equal(self, left: i32, right: i32) -> boolean:
        return left == right

    @public
    def next_u32(self, value: u32) -> u32:
        return value + u32(1)

    @public
    def next_i64(self, value: i64) -> i64:
        return value + i64(1)

    @public
    def next_u64(self, value: u64) -> u64:
        return value + u64(1)
"""


SUITES = (
    (
        "math",
        ROOT / "examples" / "math_contract.py",
        (
            ("add-positive", "add", (7, 35)),
            ("add-i32-wrap", "add", (2**31 - 1, 1)),
            ("max-left", "max", (9, -4)),
            ("max-right", "max", (-9, 4)),
            ("positive-false", "is_positive", (-1,)),
            ("positive-true", "is_positive", (1,)),
            ("loop-ten", "sum_to", (10,)),
            ("loop-empty", "sum_to", (0,)),
            ("loop-negative", "sum_to", (-4,)),
        ),
    ),
    (
        "vectors",
        ROOT / "examples" / "vector_contract.py",
        (
            ("vec-count", "count", ([3, 5, 8],)),
            ("vec-first", "first", ([-7, 4],)),
            ("vec-sum", "sum", ([3, 5, 8],)),
            ("vec-echo", "echo", ([3, -5, 8],)),
        ),
    ),
    (
        "numeric-boundaries",
        NUMERIC_SOURCE,
        (
            ("branch-true", "choose", (True, 7, 9)),
            ("branch-false", "choose", (False, 7, 9)),
            ("difference", "difference", (-12, 7)),
            ("product", "product", (-9, 6)),
            ("equal", "equal", (42, 42)),
            ("u32-wrap", "next_u32", (2**32 - 1,)),
            ("i64-wrap", "next_i64", (2**63 - 1,)),
            ("u64-wrap", "next_u64", (2**64 - 1,)),
        ),
    ),
)


def _normalized(value):
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_normalized(item) for item in value]
    return value


def _source(value):
    if isinstance(value, Path):
        return value.read_text(encoding="utf-8"), str(value)
    return value, "<differential-numeric>"


def run(node: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="pysoroban-differential-") as directory:
        output = Path(directory)
        suites = []
        for suite_name, source_value, cases in SUITES:
            source, source_name = _source(source_value)
            compilation = compile_source(source, source_name)
            contract = ContractTest(compilation)
            wasm = output / f"{suite_name}.wasm"
            wasm.write_bytes(compilation.wasm)
            functions = {function.name: function for function in compilation.ir.functions}
            encoded_cases = []
            for case_name, function_name, args in cases:
                function = functions[function_name]
                expected = contract.invoke(function_name, *args)
                encoded_cases.append({
                    "name": case_name,
                    "function": function_name,
                    "params": [param.type.value for param in function.params],
                    "result": function.result.value,
                    "args": [_normalized(value) for value in args],
                    "expected": _normalized(expected),
                })
            suites.append({"name": suite_name, "wasm": str(wasm), "cases": encoded_cases})

        manifest = output / "manifest.json"
        manifest.write_text(json.dumps({"suites": suites}), encoding="utf-8")
        completed = subprocess.run(
            [node, str(RUNNER), str(manifest)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode:
            raise RuntimeError(completed.stderr or completed.stdout or "Wasm differential runner failed")
        return json.loads(completed.stdout)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", default=shutil.which("node"), help="path to Node.js")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not args.node:
        print("error: Node.js is required for Wasm differential tests", file=sys.stderr)
        return 2
    try:
        result = run(args.node)
    except (OSError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"Typed IR/Wasm differential: {result['matched']}/{result['total']} matched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
