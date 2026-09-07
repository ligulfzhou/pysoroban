import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import __version__
from .abi import contract_abi
from .artifact import ArtifactError, inspect_wasm_file
from .compiler import check_file, compile_file
from .errors import CompileError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pysoroban", description="Compile typed Python contracts directly to Stellar Wasm")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="compile a Python contract to Wasm")
    build.add_argument("source", type=Path)
    build.add_argument("-o", "--output", type=Path)
    build.add_argument("--protocol", type=int, default=25)
    build.add_argument("--json", action="store_true", help="print machine-readable build information")
    check = subparsers.add_parser("check", help="parse and type-check without generating Wasm")
    check.add_argument("source", type=Path)
    check.add_argument("--json", action="store_true", help="print machine-readable check information")
    inspect = subparsers.add_parser("inspect", help="inspect a Python contract or compiled Wasm artifact")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--json", action="store_true", help="print complete inspection data as JSON")
    validate = subparsers.add_parser("validate", help="validate a compiled PySoroban Wasm artifact")
    validate.add_argument("wasm", type=Path)
    validate.add_argument("--json", action="store_true", help="print machine-readable validation information")
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
            is_wasm = args.input.suffix.lower() == ".wasm"
            abi = inspect_wasm_file(args.input) if is_wasm else contract_abi(check_file(args.input))
            if args.json:
                print(json.dumps(abi, sort_keys=True))
            else:
                if is_wasm:
                    print(
                        f"Artifact {abi['contract']} ({abi['size']} bytes, "
                        f"protocol {abi['protocol']})"
                    )
                    print(f"  sha256 {abi['sha256']}")
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
                if is_wasm:
                    for item in abi["imports"]:
                        print(f"  import {item['module']}.{item['name']} ({item['kind']})")
                    for item in abi["exports"]:
                        print(f"  export {item['name']} ({item['kind']})")
            return 0
        if args.command == "validate":
            info = inspect_wasm_file(args.wasm)
            result = {
                "contract": info["contract"],
                "protocol": info["protocol"],
                "sha256": info["sha256"],
                "size": info["size"],
                "status": "valid",
                "wasm": str(args.wasm),
            }
            if args.json:
                print(json.dumps(result, sort_keys=True))
            else:
                print(
                    f"Valid {result['contract']}: {result['sha256']} "
                    f"({result['size']} bytes, protocol {result['protocol']})"
                )
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
    except (ArtifactError, CompileError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
