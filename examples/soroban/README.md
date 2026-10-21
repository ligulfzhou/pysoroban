# Soroban examples in Python

Ports of https://github.com/stellar/soroban-examples. Contracts live in
`contract.py`. A directory with only a README cannot be expressed with the
current language and host surface.

Shared differences:

- There is no `__constructor`. Call `initialize`.
- Token amounts are checked `u128`. The Rust examples use `i128`.
- `fail` replaces `panic` and `Result`.
- The test host authorizes the calling contract on a direct call and inherits
  the flat `auth` list. It does not build Soroban auth entries.
- `deploy.with_constructor` records the new address and arguments. It does not
  execute the deployed contract.

| Example | Python | Notes |
| --- | --- | --- |
| alloc | `alloc/contract.py` | Sums directly. No Rust allocator. `range` bounds are `i32`. |
| atomic_multiswap | `atomic_multiswap/contract.py` | `try_void` ignores a contract error. Authorization failures still abort the batch. |
| atomic_swap | `atomic_swap/contract.py` | `u128` token transfers. |
| auth | `auth/contract.py` | Key is the address. No data-carrying enum. |
| cross_contract | `cross_contract/` | `u32` addition wraps; Rust `checked_add` panics. |
| custom_types | `custom_types/contract.py` | `State` struct. |
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
| other_custom_types | `other_custom_types/contract.py` | Option, Result, tuples, `u256`, `BytesN`, `Val`, and one-payload unions. No `i256`. A two-field variant is a struct. The `None` variant is `Empty`. |
| pause | `pause/contract.py` | |
| single_offer | `single_offer/contract.py` | Prices are `u128`. |
| timelock | `timelock/contract.py` | `u128` claimable balance. |
| token | `token/contract.py` | Contract-owned SEP-41 token, not the Stellar Asset Contract. |
| ttl | `ttl/contract.py` | Extensions are recorded. Entries do not expire in the test host. |
| upgradeable_contract | `upgradeable_contract/` | `deploy.upgrade` records the hash. No host migration. |
| workspace | `workspace/` | Cargo workspace layout is not a language feature. The two contracts match `cross_contract`. |

## Not ported

| Example | What is missing |
| --- | --- |
| account | Custom-account `__check_auth` and the `Context` auth-entry type. |
| assets | Repository image, not a contract. |
| bls_signature | BLS12-381 host functions and the custom-account interface. |
| deep_contract_auth | `authorize_as_current_contract` and nested auth entries. |
| eth_abi | Ethereum ABI decoding. `u256` and byte copies exist; there is no ABI decoder. |
| fuzzing | Cargo-fuzz harness. The contract body is the timelock example. |
| groth16_verifier | BN254 and BLS12-381 pairing host functions. |
| import_ark_bn254 | Imported arkworks BN254 Wasm, not a contract written in the guest language. |
| modular_account | Custom-account context lists and signer policies. |
| multisig_1_of_n_account | Same custom-account entry point, plus `BytesN<32>` signers. |
| privacy-pools | Groth16 verification, BLS scalars, and the incremental Merkle tree. |
| simple_account | `__check_auth` is not invoked by `require_auth`. Ed25519 verification exists, but not the account-contract protocol. |
