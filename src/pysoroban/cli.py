import argparse
import json
import sys
from pathlib import Path

from .compiler import compile_file
from .errors import CompileError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pysoroban", description="Compile typed Python contracts directly to Stellar Wasm")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="compile a Python contract to Wasm")
    build.add_argument("source", type=Path)
    build.add_argument("-o", "--output", type=Path)
    build.add_argument("--protocol", type=int, default=25)
    build.add_argument("--json", action="store_true", help="print machine-readable build information")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "build":
            output = args.output or Path("dist") / (args.source.stem + ".wasm")
            result = compile_file(args.source, output, args.protocol)
            info = {
                "contract": result.contract.name,
                "functions": [fn.name for fn in result.contract.functions],
                "output": str(output),
                "protocol": args.protocol,
                "size": len(result.wasm),
            }
            if args.json:
                print(json.dumps(info, sort_keys=True))
            else:
                print(f"Built {info['contract']} ({', '.join(info['functions'])})")
                print(f"Wrote {info['output']} ({info['size']} bytes, protocol {info['protocol']})")
            return 0
    except (CompileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

