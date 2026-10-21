# Invoke a PySoroban contract

PySoroban compiles Python to Soroban Wasm. It does not submit transactions,
manage keys, or talk to RPC. Upload, deploy, and invoke with Stellar CLI or
[stellar-sdk](https://github.com/StellarCN/py-stellar-base) (`pip install stellar-sdk`).

Build the artifact first:

```bash
pysoroban build examples/soroban/hello_world/contract.py -o dist/hello.wasm
pysoroban validate dist/hello.wasm
```

`ContractTest` in `pysoroban.testing` is the fast check. It runs Typed IR. A
testnet invoke is the check that the Wasm host accepts the same function.

## Stellar CLI

The recorded testnet procedure for the original examples is
[TESTNET.md](TESTNET.md). The same commands deploy any later artifact. This
hello-world contract returns a `Vec[String]`:

```bash
HELLO_ID=$(stellar contract deploy \
  --wasm dist/hello.wasm \
  --source alice \
  --network testnet)

stellar contract invoke --id "$HELLO_ID" --source alice --network testnet \
  --send no -- hello --to Ada
```

`--send no` simulates and does not commit. Omit it when the call must persist
storage. Authorization is the CLI's auth entries, not the flat `auth=` list
used by `ContractTest`.

## stellar-sdk

`ContractClient` simulates, and submits only when you give it a signer. Read
the simulated value with `result()`. Do not reimplement the RPC client.

```python
from stellar_sdk import Network, scval
from stellar_sdk.contract import ContractClient

client = ContractClient(
    "C...",  # contract id from stellar contract deploy
    "https://soroban-testnet.stellar.org:443",
    Network.TESTNET_NETWORK_PASSPHRASE,
)

assembled = client.invoke(
    "hello",
    [scval.to_string("Ada")],
    parse_result_xdr_fn=lambda value: [
        scval.from_string(item).decode() for item in scval.from_vec(value)
    ],
)
print(assembled.result())  # ["Hello", "Ada"]
```

A state-changing call needs the source account and its key:

```python
from stellar_sdk import Keypair, scval

source = Keypair.from_secret("S...")
assembled = client.invoke(
    "increment",
    [scval.to_address("G..."), scval.to_uint32(1)],
    source=source.public_key,
    signer=source,
)
assembled.sign_and_submit()
```

Argument order is the contract's parameter order. Types follow the Soroban
spec: `scval.to_uint32` for `u32`, `scval.to_uint128` for `u128`,
`scval.to_address` for `Address`, `scval.to_string` for `String`, and
`scval.to_bytes` for `Bytes`. When another address must authorize, sign that
entry before submit:

```python
assembled.sign_auth_entries(other)
assembled.sign_and_submit()
```

Generated bindings from
[stellar-contract-bindings](https://github.com/lightsail-network/stellar-contract-bindings)
are optional. They call this same SDK. PySoroban does not generate them.

## What the Python test host does not prove

`ContractTest` records TTL extensions, accepts ed25519 triples only after
`allow_signature`, uses a local PRNG, and invents deploy addresses. Those
calls still need a network run before they are treated as host-accurate.
Custom-account authorization is not modeled at all. See
[LANGUAGE.md](LANGUAGE.md) and [examples/soroban/README.md](../examples/soroban/README.md).
