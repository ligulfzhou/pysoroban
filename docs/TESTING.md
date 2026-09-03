# Python contract testing

`pysoroban.testing.ContractTest` provides a deterministic, dependency-free
unit-test environment for PySoroban contracts. It parses and type-checks the
same source, lowers it to the same Typed IR used by the Wasm backend, and then
interprets that IR in Python.

It is deliberately not described as a Wasm emulator. Use it for fast contract
logic tests and retain Stellar testnet or a native Soroban host for integration
tests.

## Create an environment

```python
from pysoroban.testing import ContractTest

contract = ContractTest.from_file("examples/counter_contract.py")
```

For generated or inline contracts, use `ContractTest.from_source(source)`.

## Invoke functions

Positional and keyword arguments are supported:

```python
assert contract.invoke("value", "alice") == 0
assert contract.invoke("increment", user="alice", amount=5, auth={"alice"}) == 5
```

Arguments are checked against the contract interface. Mixing positional and
keyword arguments, omitting parameters, passing unknown parameters, or passing
the wrong native type raises `InvocationError`.

## Authorization

Authorization is scoped to one invocation, matching the transaction-oriented
contract model:

```python
import unittest

from pysoroban.testing import AuthorizationError

case = unittest.TestCase()
with case.assertRaises(AuthorizationError):
    contract.invoke("increment", "alice", 5)

contract.invoke("increment", "alice", 5, auth={"alice"})
```

The test environment never retains an authorization grant for the next call.

## Storage and events

Instance storage persists across calls and is exposed as a read-only mapping.
Events are available cumulatively and for the latest invocation:

```python
from pysoroban.testing import Event

typed = ContractTest.from_file("examples/typed_events_contract.py")
typed.invoke("record", "alice", 9, auth={"alice"})

assert typed.storage["total"] == 9
assert typed.last_events == (Event(("updated", "alice"), 9),)
assert typed.events[-1].data == 9
```

`clear_events()` removes captured events without clearing contract storage.
A typed get of a missing key raises `StorageMissingError`.

## Cross-contract calls

Link deterministic test environments by address before invoking a caller:

```python
math = ContractTest.from_file("examples/math_contract.py")
proxy = ContractTest.from_file("examples/cross_contract.py")
proxy.register_contract("math", math)

assert proxy.invoke("add_with", "math", 5, 7) == 12
```

An unregistered address raises `InvocationError`. The initial simulator does
not forward authorization into linked contracts; authorization-tree testing
remains an integration-test concern.

## Numeric behavior

The interpreter validates `i32`, `u32`, `i64`, and `u64` argument ranges.
Arithmetic follows the current Wasm backend and wraps at the corresponding
32- or 64-bit boundary.

`for` loops over `range()` execute with the same start-inclusive,
stop-exclusive behavior as the Wasm backend.

Typed vectors are represented by Python lists or tuples. Element types are
validated recursively before invocation, and invalid indexes raise
`InvocationError`:

```python
vectors = ContractTest.from_file("examples/vector_contract.py")
assert vectors.invoke("sum", [3, 5, 8]) == 16
```

## Limitations

- It runs Typed IR, not the compiled Wasm binary.
- It does not meter CPU, memory, ledger I/O, or fees.
- It does not reproduce ledger TTL, sequence, timestamp, or network state.
- Address values are represented as Python strings and are not StrKey-decoded.
- Maps, nested vectors, and mutable vector operations are not implemented yet.

Every new host operation should have both interpreter tests and a Stellar
integration test before it is treated as supported.
