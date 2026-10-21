# Examples

Python ports of [stellar/soroban-examples](https://github.com/stellar/soroban-examples).
Each directory is one upstream example. Contracts live in `contract.py`. A
directory with only a README cannot be expressed with the current language
and host surface.

The earlier flat `*_contract.py` compiler suite is not in this directory.
Those sources are `tests/fixtures/compiler_suite/` so the bytecode lock and
the differential suite can still compile them. Copy a port below when writing
a contract.

Shared differences:

- `__constructor` is the protocol constructor. The test host runs it once via `invoke`. `deploy.with_constructor` does not execute the new Wasm.
- Token amounts are checked `u128`. The Rust examples use `i128`.
- `fail` replaces `panic` and `Result`.
- The test host authorizes the calling contract on a direct call only. The
  flat `auth` list is inherited, but an intermediate contract address is not.
  `authorize_account` runs `__check_auth`. `auth.as_current_contract` records
  one deeper `require_auth`.
- BLS12-381 and BN254 calls are real Wasm imports. The test host returns a
  queued result. `enforce_ttl` is off unless the test sets it.
- `deploy.with_constructor` records the new address and arguments. It does not
  execute the deployed contract.

| Example | Python | Notes |
| --- | --- | --- |
| account | `account/contract.py` | Multisig spend limits. Contexts are supplied by the test. No create-contract variant. |
| alloc | `alloc/contract.py` | Sums directly. No Rust allocator. `range` bounds are `i32`. |
| atomic_multiswap | `atomic_multiswap/contract.py` | `try_void` ignores a contract error. Authorization failures still abort the batch. |
| atomic_swap | `atomic_swap/contract.py` | `u128` token transfers. |
| auth | `auth/contract.py` | Key is the address. No data-carrying enum. |
| bls_signature | `bls_signature/contract.py` | Aggregate BLS account. Pairing is scripted in the test host. |
| cross_contract | `cross_contract/` | `u32` addition wraps; Rust `checked_add` panics. |
| custom_types | `custom_types/contract.py` | `State` struct. |
| deep_contract_auth | `deep_contract_auth/` | One subcall with one argument. Deeper auth trees are not built. |
| deployer | `deployer/` | Test host does not run the child constructor. |
| errors | `errors/contract.py` | `fail` at 5. |
| events | `events/contract.py` | One symbol topic, not two static topics. |
| hello_world | `hello_world/contract.py` | |
| increment | `increment/contract.py` | No formatted `log!`. |
| increment_with_fuzz | `increment_with_fuzz/contract.py` | Cargo-fuzz harness is not a contract. |
| increment_with_pause | `increment_with_pause/contract.py` | Calls `pause`. |
| liquidity_pool | `liquidity_pool/contract.py` | Tokenized constant-product pool. Tuple results are structs. No address ordering. |
| logging | `logging/contract.py` | `log` takes a `String`, not a formatted `Symbol`. |
| merkle_distribution | `merkle_distribution/contract.py` | Leaf is `to_xdr` of the receiver. Claimed keys are `u32`. |
| mint-lock | `mint-lock/contract.py` | Struct keys. `minter` returns `MinterInfo`. |
| multisig_1_of_n_account | `multisig_1_of_n_account/contract.py` | Any one ed25519 signer. Context is unused. |
| other_custom_types | `other_custom_types/contract.py` | Option, Result, tuples, `u256`, `BytesN`, `Val`, and one-payload unions. No `i256`. A two-field variant is a struct. The `None` variant is `Empty`. |
| pause | `pause/contract.py` | |
| simple_account | `simple_account/contract.py` | Owner ed25519 check. A test may `allow_signature` or pass a real signature. |
| single_offer | `single_offer/contract.py` | Prices are `u128`. |
| timelock | `timelock/contract.py` | `u128` claimable balance. |
| token | `token/contract.py` | Contract-owned SEP-41 token, not the Stellar Asset Contract. |
| ttl | `ttl/contract.py` | Extensions are recorded. Set `enforce_ttl` to expire them. |
| upgradeable_contract | `upgradeable_contract/` | `deploy.upgrade` records the hash. No host migration. |
| workspace | `workspace/` | Cargo workspace layout is not a language feature. The two contracts match `cross_contract`. |

## Not ported

| Example | What is missing |
| --- | --- |
| assets | Repository image, not a contract. |
| eth_abi | Ethereum ABI decoding. `u256` and byte copies exist; there is no ABI decoder. |
| fuzzing | Cargo-fuzz harness. The contract body is the timelock example. |
| groth16_verifier | The BN254 pairing host calls exist. The example is an arkworks circuit and a prepared verifying key, not those calls. |
| import_ark_bn254 | Imported arkworks BN254 Wasm, not a contract written in the guest language. |
| modular_account | Delegated signers are protocol 27. This compiler targets protocol 25. |
| privacy-pools | Groth16 circuit and LeanIMT. BLS scalar arithmetic is available; the proof objects are not. |
