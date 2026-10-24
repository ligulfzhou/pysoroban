# PySoroban

[![CI](https://github.com/ligulfzhou/pysoroban/actions/workflows/ci.yml/badge.svg)](https://github.com/ligulfzhou/pysoroban/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pysoroban-compiler.svg)](https://pypi.org/project/pysoroban-compiler/)

PySoroban is an experimental, deterministic, statically typed Python contract
language for Stellar. It compiles a deliberately small Python subset **directly
to Soroban-compatible WebAssembly**. It does not generate Rust and it does not
embed a Python runtime in the contract.

> Status: compiler MVP. The current release is intended for language and
> toolchain validation, not production funds.

The September 2026 compiler suite, including the checked `u128` AMM
accounting kernel, was deployed and invoked on Stellar testnet. Those sources
now live in `tests/fixtures/compiler_suite/`. The contracts under `examples/`
are the soroban-examples ports. See
[the reproducible testnet verification](https://github.com/ligulfzhou/pysoroban/blob/main/docs/TESTNET.md).

The [PySoroban Live Proof](https://pysoroban.xyz)
compiles the six editor ports in the browser with the published
`pysoroban-compiler` 0.19.0a2 wheel, shows the scripted testnet records, and
simulates live read-only calls. Its source lives in
[the repository's `web/` directory](https://github.com/ligulfzhou/pysoroban/tree/main/web);
run it locally with `cd web && npm install && npm run dev`.

## What works

- `@contract` classes and `@public` methods
- `i32`, `u32`, `i64`, `u64`, `i128`, `u128`, `boolean`, `Address`, `Symbol`, `String`,
  `Bytes`, and `None` signatures
- integer arithmetic for 32- and 64-bit values: `+`, `-`, `*`, plus `//`
  for `u32` and `u64`
- checked `+`, `-`, and `*` for `i128` and `u128`, plus checked `u128` floor
  division; pass-through, literals, comparison, storage, events, collections,
  and cross-contract results for those wide values
- `u128.mul_div_floor(left, right, denominator)` with a widened `u256`
  intermediate, explicit floor rounding, and checked narrowing
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
- `@error` enums and `fail(Error.CASE)`, which trap through Soroban's
  `fail_with_error` so the invocation's storage and events are not committed
- deterministic builds with no compiler dependencies
- automated differential tests comparing Typed IR execution with generated
  Wasm for arithmetic, branches, loops, integer boundaries, and vectors

- `@struct` records and `@enum` integer discriminants in the contract spec
- `Vec.push`, `set`, `insert`, `remove`, and `pop`, plus `Map.set` and
  `Map.remove`, as statements that update a local
- `storage.persistent` and `storage.temporary`, `get(key, Type)`,
  `get_address`, `remove`, and TTL extension
- ledger sequence, timestamp, version, and network id, plus the current
  contract address
- `crypto.sha256`, `keccak256`, and `ed25519_verify`, `log`, `prng.bytes`,
  and `prng.u64`
- `String` / `Bytes` conversion and slicing, and `Bytes.append`
- `deploy.upload`, `deploy.contract`, `deploy.with_constructor`,
  `deploy.upgrade`, and `deploy.asset`
- `examples/token/contract.py`, a contract-owned SEP-41 style token
- `examples/`, a Python mirror of stellar/soroban-examples, including
  a tokenized constant-product pool. Gaps such as custom accounts, Groth16,
  and `try_call` are documented in [examples/README.md](examples/README.md)

`i128` floor division, nested collections, custom-account authorization, and
the Stellar Asset Contract XDR builder are still absent. The Python test host
does not reproduce ed25519, the host PRNG, TTL expiry, or deployed addresses.

`examples/liquidity_pool/contract.py` is the tokenized constant-product pool.
The earlier accounting kernel remains in
`tests/fixtures/compiler_suite/amm_kernel_contract.py` for compiler tests. It
is not an example to deploy. See the
[AMM reference design](https://github.com/ligulfzhou/pysoroban/blob/main/docs/AMM_DESIGN.md)
for the safety boundary and the gates that kernel was written to expose.

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
pysoroban check examples/hello_world/contract.py
pysoroban check examples/hello_world/contract.py --json
```

Inspect a stable, machine-readable ABI, inspect or validate the compiled Wasm
without its source, and verify that an artifact is the exact deterministic
output of its source:

```bash
pysoroban inspect examples/events/contract.py --json
pysoroban inspect dist/hello.wasm
pysoroban validate dist/hello.wasm --json
pysoroban verify examples/hello_world/contract.py \
  --wasm dist/hello.wasm
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

`examples/auth/contract.py` demonstrates address authorization and persistent
storage keyed by the authorized address.

## Test contracts in Python

The fast Typed IR test environment exercises contract behavior without a
network or Rust toolchain:

```python
from pysoroban.testing import ContractTest, Event

contract = ContractTest.from_file("examples/events/contract.py")
result = contract.invoke("increment")

assert result == 1
assert contract.storage["COUNTER"] == result
assert contract.last_events == (Event(("increment",), result),)
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

Integer wrapping, checked wide arithmetic, and contract errors are specified in
[the language specification](docs/LANGUAGE.md). That document is the behavior
contract for the current compiler: unchanged sources keep their Wasm bytes.
Deploy and invoke with Stellar CLI or stellar-sdk, as described in
[docs/INVOKE.md](docs/INVOKE.md).

## Language boundary

PySoroban intentionally rejects dynamic Python features such as arbitrary
objects, reflection, dynamic imports, `eval`, floating point, exceptions,
generators, and unbounded recursion. This boundary is part of the language's
determinism and security model.

The initial loop implementation supports `range(stop)` and
`range(start, stop)` with an implicit step of `+1`. Variables assigned in a
loop body must be declared before the loop; `break`, `continue`, and `for/else`
are not supported yet.

Rejected work aborts with `fail` instead of a sentinel return. `fail` is a
statement, and it ends the path for the return checker:

```python
from pysoroban import contract, error, fail, public, u128

@error
class SwapError:
    SLIPPAGE = 1

@contract
class Pool:
    @public
    def swap(self, amount_out: u128, minimum_out: u128) -> u128:
        if amount_out < minimum_out:
            fail(SwapError.SLIPPAGE)
        return amount_out
```

A zero return remains a normal numeric result. Use it for an absent view, as
`Counter.value` does, and use `fail` when the call must not commit.

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
returned from cross-contract calls. Addition, subtraction, and multiplication
trap on overflow. `u128` floor division traps on a zero divisor. `i128` floor
division is rejected. `u128.mul_div_floor()` computes a widened product
followed by floor division.

Homogeneous vectors use normal Python type and expression syntax:

```python
from pysoroban import Vec, i32

def sum(self, values: Vec[i32]) -> i32:
    total: i32 = 0
    for index in range(len(values)):
        total = total + values[index]
    return total
```

The current vector element types are scalars, `@struct`, and `@enum`.
Nested vectors are rejected. `push`, `set`, `insert`, `remove`, and `pop`
update the local.

Homogeneous maps use two type parameters. Keys and values may be scalars,
enums, or structs. Indexing, membership, length, and `set` / `remove` are
supported:

```python
from pysoroban import Map, Symbol, i32

def score(self, scores: Map[Symbol, i32], player: Symbol) -> i32:
    if scores.has(player):
        return scores[player]
    return 0
```

Nested collections are rejected. `Map.set` and `Map.remove` update the local.

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
PYTHONPATH=src python3 -m pysoroban build examples/hello_world/contract.py
PYTHONPATH=src python3 -m pysoroban validate dist/hello.wasm
```

GitHub Actions runs the compiler suite on Python 3.9 and 3.13, validates every
example as WebAssembly, runs the Typed IR/Wasm differential suite, builds an
installable wheel, and builds/tests/lints the Cloudflare demo with Node 24.
Publishing a release is described in [docs/RELEASING.md](docs/RELEASING.md).

Run the same differential suite locally when Node.js is available:

```bash
PYTHONPATH=src python3 scripts/differential_test.py
```

Licensed under MIT. See [the license](https://github.com/ligulfzhou/pysoroban/blob/main/LICENSE).
