# Artifact validation

PySoroban uses several deliberately separate checks. No single check is
presented as a security audit or proof that arbitrary contract behavior is
correct.

## Source checking

```bash
pysoroban check examples/math_contract.py
```

This parses the supported Python subset and performs static type checking. It
does not produce an artifact.

## Artifact inspection and structural validation

```bash
pysoroban inspect dist/math_contract.wasm
pysoroban validate dist/math_contract.wasm
```

Both commands work without the Python source. The validator checks:

- the WebAssembly 1 magic and version;
- section lengths, uniqueness, and ordering;
- matching function and code counts;
- required `contractenvmetav0`, `contractspecv0`, and `contractmetav0`
  sections;
- the protocol number and PySoroban metadata;
- the function, event, import, and export encodings emitted by this compiler.

This is intentionally a validator for the PySoroban/Soroban subset emitted by
the project. It is not a general-purpose validator for every future WebAssembly
proposal or every contract-spec type another compiler may emit.

## Reproducibility verification

```bash
pysoroban verify examples/math_contract.py --wasm dist/math_contract.wasm
```

This rebuilds the source with the selected protocol and compares the result
byte-for-byte with the supplied artifact. A successful result establishes that
the artifact is the deterministic output of that source and compiler version.

## CI semantic validation

The GitHub Actions workflow builds every example and applies Node's
`WebAssembly.validate()` in addition to `pysoroban validate`. It also runs the
unit tests across the minimum and current Python versions, compares Typed IR
results with generated Wasm for deterministic execution cases, and builds the
web demo.

## Stellar integration

WebAssembly validity is not the same as Soroban compatibility. The testnet
procedure in [`TESTNET.md`](TESTNET.md) remains the integration source of truth:
Stellar CLI reads the generated interface, uploads the Wasm, deploys it, and
invokes the contract on testnet.
