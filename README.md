# PySoroban

PySoroban is an experimental, deterministic, statically typed Python contract
language for Stellar. It compiles a deliberately small Python subset **directly
to Soroban-compatible WebAssembly**. It does not generate Rust and it does not
embed a Python runtime in the contract.

> Status: compiler MVP. The current release is intended for language and
> toolchain validation, not production funds.

## What works

- `@contract` classes and `@public` methods
- `i32`, `boolean`, `Address`, and `None` signatures
- integer arithmetic: `+`, `-`, `*`
- comparisons, boolean expressions, local variables, and `if/else`
- direct Wasm binary generation in pure Python
- Soroban `Val` ABI conversion
- generated `contractenvmetav0`, `contractspecv0`, and `contractmetav0`
- instance storage (`get_i32`, `get_bool`, `has`, `set`)
- address authorization with `address.require_auth()`
- deterministic builds with no compiler dependencies

Events, collection types, loops, cross-contract calls, and developer test
utilities are planned next.

## Quick start

Python 3.9 or later is required.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
pysoroban build examples/math_contract.py
```

The output is `dist/math_contract.wasm`. Inspect it with Stellar CLI:

```bash
stellar contract info interface --wasm dist/math_contract.wasm
stellar contract info env-meta --wasm dist/math_contract.wasm
```

`examples/counter_contract.py` demonstrates address authorization and isolated
instance-storage values keyed by each authorized user.

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
```

Contract files are parsed, type checked, and compiled; they are not imported or
executed by Python during compilation.

## Language boundary

PySoroban intentionally rejects dynamic Python features such as arbitrary
objects, reflection, dynamic imports, `eval`, floating point, exceptions,
generators, and unbounded recursion. This boundary is part of the language's
determinism and security model.

## Architecture

```text
Python source
    -> CPython AST parser
    -> PySoroban static type checker
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
python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m pysoroban build examples/math_contract.py
```

Licensed under Apache-2.0.
