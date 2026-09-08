# PySoroban

[![CI](https://github.com/ligulfzhou/pysoroban/actions/workflows/ci.yml/badge.svg)](https://github.com/ligulfzhou/pysoroban/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pysoroban-compiler.svg)](https://pypi.org/project/pysoroban-compiler/)

PySoroban is an experimental, deterministic, statically typed Python contract
language for Stellar. It compiles a deliberately small Python subset **directly
to Soroban-compatible WebAssembly**. It does not generate Rust and it does not
embed a Python runtime in the contract.

> Status: compiler MVP. The current release is intended for language and
> toolchain validation, not production funds.

The Math, authorized Counter, and typed-event examples have been deployed and
invoked on Stellar testnet. See
[the reproducible testnet verification](https://github.com/ligulfzhou/pysoroban/blob/main/docs/TESTNET.md).

The [PySoroban Live Proof](https://pysoroban.xyz)
can compile the example contracts in the browser, show their deployed testnet
records, and simulate live read-only calls. Its source lives in
[the repository's `web/` directory](https://github.com/ligulfzhou/pysoroban/tree/main/web);
run it locally with `cd web && npm install && npm run dev`.

## What works

- `@contract` classes and `@public` methods
- `i32`, `u32`, `i64`, `u64`, `i128`, `u128`, `boolean`, `Address`, `Symbol`, `String`,
  `Bytes`, and `None` signatures
- integer arithmetic for 32- and 64-bit values: `+`, `-`, `*`, plus `//`
  for `u32` and `u64`
- pass-through, literals, comparison, storage, events, collections, and
  cross-contract results for Soroban `i128` and `u128` values
- comparisons, boolean expressions, local variables, and `if/else`
- metered `for` loops using `range(stop)` or `range(start, stop)` with `i32`
  bounds, lowered to native Wasm loops
- homogeneous `Vec[T]` parameters and results, `len(values)`, and typed
  `values[index]` access
- homogeneous `Map[K, V]` parameters and results with typed indexing,
  `values.has(key)`, and `len(values)`
- direct Wasm binary generation in pure Python
- Soroban `Val` ABI conversion
- generated `contractenvmetav0`, `contractspecv0`, and `contractmetav0`
- typed instance storage (`get_i32`, `get_u32`, `get_i64`, `get_u64`,
  `get_i128`, `get_u128`,
  `get_bool`, `get_symbol`, `get_string`, `get_bytes`, `has`, `set`)
- address authorization with `address.require_auth()`
- typed cross-contract calls through `Address.call_void`, `call_i32`,
  `call_u64`, `call_string`, and the other supported result types
- Soroban-compatible typed event specifications with `@event`, dynamic
  `Topic[T]` fields, and `events.publish(MyEvent(...))`
- backwards-compatible raw events with `events.publish(Symbol(...), data)`
- a deterministic Python test environment for calls, per-invocation auth,
  instance storage, events, and Wasm-style integer wrapping
- deterministic builds with no compiler dependencies
- automated differential tests comparing Typed IR execution with generated
  Wasm for arithmetic, branches, loops, integer boundaries, and vectors

User-defined contract types and mutable collection operations are planned next.

`examples/amm_kernel_contract.py` is the first composed DeFi workload. It
implements constant-product quoting, authorized reserve accounting, slippage
checks, and typed events. It is deliberately not tokenized yet; see the
[AMM reference design](https://github.com/ligulfzhou/pysoroban/blob/main/docs/AMM_DESIGN.md)
for the safety boundary and the gates to a testnet AMM.

## Quick start

Python 3.9 or later is required.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --pre pysoroban-compiler
```

The published package is an alpha preview. Install a source checkout with
`pip install -e .` when contributing to the compiler.

Save the following contract as `contract.py`:

```python
from pysoroban import contract, i32, public

@contract
class Math:
    @public
    def add(self, left: i32, right: i32) -> i32:
        return left + right
```

Then compile and inspect it:

```bash
pysoroban build contract.py
pysoroban validate dist/contract.wasm
```

Inspect the output with Stellar CLI:

```bash
stellar contract info interface --wasm dist/contract.wasm
stellar contract info env-meta --wasm dist/contract.wasm
```

For editor hooks and CI, validate source without producing a Wasm artifact:

```bash
pysoroban check examples/counter_contract.py
pysoroban check examples/counter_contract.py --json
```

Inspect a stable, machine-readable ABI, inspect or validate the compiled Wasm
without its source, and verify that an artifact is the exact deterministic
output of its source:

```bash
pysoroban inspect examples/typed_events_contract.py --json
pysoroban inspect dist/math_contract.wasm
pysoroban validate dist/math_contract.wasm --json
pysoroban verify examples/typed_events_contract.py \
  --wasm dist/typed-events-testnet.wasm
```

Artifact inspection decodes the Soroban protocol metadata, contract functions,
typed events, host imports, Wasm exports, section sizes, and SHA-256 digest.
`validate` checks WebAssembly framing and section ordering together with the
PySoroban contract XDR subset. CI additionally runs the platform WebAssembly
validator and rebuilds, validates, and verifies every example. See
[the validation documentation](https://github.com/ligulfzhou/pysoroban/blob/main/docs/VALIDATION.md)
for the exact validation boundary.

`pysoroban build --json` also reports the artifact SHA-256, protocol, functions,
and typed events for CI and deployment manifests.

`examples/counter_contract.py` demonstrates address authorization and isolated
instance-storage values keyed by each authorized user.

## Test contracts in Python

The fast Typed IR test environment exercises contract behavior without a
network or Rust toolchain:

```python
from pysoroban.testing import ContractTest, Event

contract = ContractTest.from_file("examples/typed_events_contract.py")
result = contract.invoke(
    "record",
    "alice",
    100_000_000_000_000_000,
    auth={"alice"},
)

assert result == 100_000_000_000_000_000
assert contract.storage["total"] == result
assert contract.last_events == (Event(("updated", "alice"), result),)
```

This environment interprets the checked Typed IR. It is intended for fast unit
tests, while Stellar testnet remains the integration-test source of truth. See
[the testing documentation](https://github.com/ligulfzhou/pysoroban/blob/main/docs/TESTING.md)
for the API and limitations.

## Contract example

```python
from pysoroban import boolean, contract, i32, public

@contract
class Math:
    @public
    def add(self, left: i32, right: i32) -> i32:
        return left + right

    @public
    def is_positive(self, value: i32) -> boolean:
        return value > 0

    @public
    def sum_to(self, stop: i32) -> i32:
        total: i32 = 0
        for value in range(stop):
            total = total + value
        return total
```

Contract files are parsed, type checked, and compiled; they are not imported or
executed by Python during compilation.

Typed events use the same shape exposed by Soroban SDKs:

```python
from pysoroban import Address, Topic, event, events, u64

@event
class Updated:
    owner: Topic[Address]
    value: u64

events.publish(Updated(owner, value))
```

The compiler records `updated` as the static prefix topic, `owner` as a dynamic
topic, and `value` as single-value event data in `contractspecv0`.

## Language boundary

PySoroban intentionally rejects dynamic Python features such as arbitrary
objects, reflection, dynamic imports, `eval`, floating point, exceptions,
generators, and unbounded recursion. This boundary is part of the language's
determinism and security model.

The initial loop implementation supports `range(stop)` and
`range(start, stop)` with an implicit step of `+1`. Variables assigned in a
loop body must be declared before the loop; `break`, `continue`, and `for/else`
are not supported yet.

Cross-contract calls use an explicit result type so they remain statically
checked without generated Rust clients:

```python
from pysoroban import Address, Symbol, i32

def add_with(target: Address, left: i32, right: i32) -> i32:
    return target.call_i32(Symbol("add"), left, right)
```

The available methods are `call_void`, `call_i32`, `call_u32`, `call_i64`,
`call_u64`, `call_i128`, `call_u128`, `call_bool`, `call_address`,
`call_symbol`, `call_string`, and `call_bytes`.
The target contract must expose a compatible function; an incompatible target
traps at runtime as it does for the underlying Soroban host call.

`i128` and `u128` are Soroban `Val`-backed wide integers rather than native
Wasm integer locals. They can cross the contract ABI, be constructed from
checked literals, compared, stored, emitted, carried in collections, and
returned from cross-contract calls. Arithmetic on them is deliberately
rejected until checked overflow and rounding semantics are implemented.

Homogeneous vectors use normal Python type and expression syntax:

```python
from pysoroban import Vec, i32

def sum(self, values: Vec[i32]) -> i32:
    total: i32 = 0
    for index in range(len(values)):
        total = total + values[index]
    return total
```

The current vector element types are all existing scalar and object types.
Nested vectors, slicing, and mutation are intentionally deferred.

Homogeneous maps use two type parameters. The first release supports scalar
keys and values, read-only indexing, membership, length, and pass-through
results:

```python
from pysoroban import Map, Symbol, i32

def score(self, scores: Map[Symbol, i32], player: Symbol) -> i32:
    if scores.has(player):
        return scores[player]
    return 0
```

Nested collections and map mutation are intentionally deferred.

## Architecture

See [the architecture documentation](https://github.com/ligulfzhou/pysoroban/blob/main/docs/ARCHITECTURE.md)
for the full compiler architecture, semantic ownership, trust boundaries, and
validation strategy.

```text
Python source
    -> CPython AST parser
    -> PySoroban static type checker
    -> backend-independent Typed IR
    -> native-value Wasm lowering
    -> Soroban Val ABI wrappers
    -> Wasm binary + XDR custom sections
```

The compiler is currently dependency-free and implemented in Python. The Wasm
encoder and the small amount of Stellar XDR required by the MVP live in this
repository so the user-facing build does not require Rust, Cargo, Node, or a
separate WebAssembly toolchain.

## Development

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m pysoroban build examples/math_contract.py
PYTHONPATH=src python3 -m pysoroban validate dist/math_contract.wasm
```

GitHub Actions runs the compiler suite on Python 3.9 and 3.13, validates every
example as WebAssembly, runs the Typed IR/Wasm differential suite, builds an
installable wheel, and builds/tests/lints the Cloudflare demo with Node 24.

Run the same differential suite locally when Node.js is available:

```bash
PYTHONPATH=src python3 scripts/differential_test.py
```

Licensed under MIT. See [the license](https://github.com/ligulfzhou/pysoroban/blob/main/LICENSE).
