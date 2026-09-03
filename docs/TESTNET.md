# Testnet verification

PySoroban-generated Wasm has been uploaded, deployed, and invoked on Stellar
testnet protocol 25. The verification used `stellar-cli 25.2.0` and did not use
generated Rust or a Rust contract build.

The current deployment IDs and transaction hashes are recorded in
`deployments/testnet.json`. Testnet contracts and ledger entries may eventually
expire, so the commands below are the durable verification procedure.

All recorded Wasm hashes can be reproduced locally before contacting testnet:

```bash
pysoroban verify examples/math_contract.py --wasm dist/math-testnet.wasm
pysoroban verify examples/counter_contract.py --wasm dist/counter-testnet.wasm
pysoroban verify examples/typed_events_contract.py \
  --wasm dist/typed-events-testnet.wasm
pysoroban verify examples/cross_contract.py \
  --wasm dist/cross-contract-testnet.wasm
pysoroban verify examples/vector_contract.py --wasm dist/vector-testnet.wasm
```

## Prerequisites

Configure a funded testnet identity in Stellar CLI. The examples use an
identity named `alice`:

```bash
stellar network health --network testnet
stellar keys address alice
```

## Build and deploy Math

```bash
pysoroban build examples/math_contract.py -o dist/math-testnet.wasm

MATH_ID=$(stellar contract deploy \
  --wasm dist/math-testnet.wasm \
  --source alice \
  --network testnet)

stellar contract invoke --id "$MATH_ID" --source alice --network testnet \
  --send no -- add --left 7 --right 35

stellar contract invoke --id "$MATH_ID" --source alice --network testnet \
  --send no -- sum_to --stop 10
```

Expected results: `42` and `45`. The second call executes a parameter-bounded
Wasm loop generated from Python `for value in range(stop)`.

## Build and deploy Counter

```bash
pysoroban build examples/counter_contract.py -o dist/counter-testnet.wasm

COUNTER_ID=$(stellar contract deploy \
  --wasm dist/counter-testnet.wasm \
  --source alice \
  --network testnet)

USER=$(stellar keys address alice)

stellar contract invoke --id "$COUNTER_ID" --source alice --network testnet \
  --send no -- value --user "$USER"

stellar contract invoke --id "$COUNTER_ID" --source alice --network testnet \
  -- increment --user "$USER" --amount 5

stellar contract invoke --id "$COUNTER_ID" --source alice --network testnet \
  --send no -- value --user "$USER"
```

Expected sequence: `0`, `5`, `5`. The state-changing call exercises Soroban
address authorization and instance storage; the final call confirms the value
was committed to the ledger.

## Build and deploy typed values and events

```bash
pysoroban build examples/typed_events_contract.py \
  -o dist/typed-events-testnet.wasm

TYPED_ID=$(stellar contract deploy \
  --wasm dist/typed-events-testnet.wasm \
  --source alice \
  --network testnet)

stellar contract invoke --id "$TYPED_ID" --source alice --network testnet \
  --send no -- offset --value -40000000000000000

stellar contract invoke --id "$TYPED_ID" --source alice --network testnet \
  --send no -- label

USER=$(stellar keys address alice)
stellar contract invoke --id "$TYPED_ID" --source alice --network testnet \
  -- record --owner "$USER" --amount 100000000000000000
```

Expected results are `-40000000000000007`, `"PySoroban"`, and a committed
`Updated` typed event whose topics are the `updated` symbol and owner address,
and whose data is the `u64` value `100000000000000000`.

## Build and deploy the cross-contract proxy

```bash
pysoroban build examples/cross_contract.py \
  -o dist/cross-contract-testnet.wasm

PROXY_ID=$(stellar contract deploy \
  --wasm dist/cross-contract-testnet.wasm \
  --source alice \
  --network testnet)

stellar contract invoke --id "$PROXY_ID" --source alice --network testnet \
  --send no -- add_with --target "$MATH_ID" --left 5 --right 7

stellar contract invoke --id "$PROXY_ID" --source alice --network testnet \
  --send no -- sum_with --target "$MATH_ID" --stop 10
```

Expected results: `12` and `45`. Both are returned through a real nested
contract invocation on testnet.

## Build and deploy typed vectors

```bash
pysoroban build examples/vector_contract.py -o dist/vector-testnet.wasm

VECTOR_ID=$(stellar contract deploy \
  --wasm dist/vector-testnet.wasm \
  --source alice \
  --network testnet)

stellar contract invoke --id "$VECTOR_ID" --source alice --network testnet \
  --send no -- sum --values '[3,5,8]'

stellar contract invoke --id "$VECTOR_ID" --source alice --network testnet \
  --send no -- echo --values '[3,5,8]'
```

Expected results: `16` and `[3,5,8]`.

## What this proves

- contract environment and interface metadata are accepted by the network;
- exported functions use the correct Soroban `Val` ABI;
- signed `i32` and `bool` arguments and results round-trip correctly;
- Python `for range` is lowered to working Wasm structured control flow;
- `u32`, full-range object-backed `i64/u64`, `String`, and `Bytes` values
  round-trip correctly;
- `Address` host objects pass through the guest interface correctly;
- `require_auth` is recognized and satisfied by Stellar CLI;
- instance `has`, `get`, and `put` host functions persist state.
- a PySoroban contract can publish a real Soroban typed event with static and
  dynamic topics whose schema is understood by Stellar CLI.
- one PySoroban contract can invoke another using a typed return value and a
  Soroban argument vector.
- `Vec[T]` interfaces, vector length/index access, loops over vectors, and
  vector results round-trip through the network.

It does not constitute a security audit or production-readiness claim.
