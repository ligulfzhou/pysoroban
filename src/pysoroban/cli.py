import argparse
import hashlib
import json
import sys
from pathlib import Path

from .abi import contract_abi
from .compiler import check_file, compile_file
from .errors import CompileError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pysoroban", description="Compile typed Python contracts directly to Stellar Wasm")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="compile a Python contract to Wasm")
    build.add_argument("source", type=Path)
    build.add_argument("-o", "--output", type=Path)
    build.add_argument("--protocol", type=int, default=25)
    build.add_argument("--json", action="store_true", help="print machine-readable build information")
    check = subparsers.add_parser("check", help="parse and type-check without generating Wasm")
    check.add_argument("source", type=Path)
    check.add_argument("--json", action="store_true", help="print machine-readable check information")
    inspect = subparsers.add_parser("inspect", help="print the checked contract ABI")
    inspect.add_argument("source", type=Path)
    inspect.add_argument("--json", action="store_true", help="print the complete ABI as JSON")
    verify = subparsers.add_parser("verify", help="rebuild source and compare it byte-for-byte with a Wasm artifact")
    verify.add_argument("source", type=Path)
    verify.add_argument("--wasm", type=Path, required=True)
    verify.add_argument("--protocol", type=int, default=25)
    verify.add_argument("--json", action="store_true", help="print machine-readable verification information")
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
                "events": [event.name for event in result.contract.events],
                "output": str(output),
                "protocol": args.protocol,
                "size": len(result.wasm),
                "sha256": hashlib.sha256(result.wasm).hexdigest(),
            }
            if args.json:
                print(json.dumps(info, sort_keys=True))
            else:
                print(f"Built {info['contract']} ({', '.join(info['functions'])})")
                print(f"Wrote {info['output']} ({info['size']} bytes, protocol {info['protocol']})")
            return 0
        if args.command == "inspect":
            abi = contract_abi(check_file(args.source))
            if args.json:
                print(json.dumps(abi, sort_keys=True))
            else:
                print(f"Contract {abi['contract']}")
                for function in abi["functions"]:
                    inputs = ", ".join(f"{item['name']}: {item['type']}" for item in function["inputs"])
                    outputs = ", ".join(function["outputs"]) or "None"
                    print(f"  fn {function['name']}({inputs}) -> {outputs}")
                for event in abi["events"]:
                    topics = ", ".join(
                        [repr(value) for value in event["prefix_topics"]]
                        + [f"{item['name']}: {item['type']}" for item in event["topics"]]
                    )
                    data = ", ".join(f"{item['name']}: {item['type']}" for item in event["data"])
                    print(f"  event {event['name']}({topics}) data({data})")
            return 0
        if args.command == "verify":
            result = compile_file(args.source, protocol=args.protocol)
            actual = args.wasm.read_bytes()
            expected_hash = hashlib.sha256(result.wasm).hexdigest()
            actual_hash = hashlib.sha256(actual).hexdigest()
            verified = result.wasm == actual
            info = {
                "actual_sha256": actual_hash,
                "contract": result.contract.name,
                "expected_sha256": expected_hash,
                "protocol": args.protocol,
                "status": "verified" if verified else "mismatch",
                "wasm": str(args.wasm),
            }
            if args.json:
                print(json.dumps(info, sort_keys=True))
            elif verified:
                print(f"Verified {info['contract']}: {actual_hash}")
            else:
                print(f"Mismatch for {info['contract']}", file=sys.stderr)
                print(f"  rebuilt: {expected_hash}", file=sys.stderr)
                print(f"  artifact: {actual_hash}", file=sys.stderr)
            return 0 if verified else 1
        if args.command == "check":
            contract = check_file(args.source)
            info = {
                "contract": contract.name,
                "functions": [fn.name for fn in contract.functions],
                "source": str(args.source),
                "status": "ok",
            }
            if args.json:
                print(json.dumps(info, sort_keys=True))
            else:
                print(f"Checked {info['contract']} ({', '.join(info['functions'])}): ok")
            return 0
    except (CompileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
