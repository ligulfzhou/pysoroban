# Examples

Flat `*_contract.py` files are the compiler's original suite. Their Wasm hashes
are locked in `tests/test_bytecode_lock.py` when the source has not changed.

`soroban/` mirrors [stellar/soroban-examples](https://github.com/stellar/soroban-examples).
Each directory has a Python contract, or a README that names the missing
language or host feature. Differences from the Rust contracts (no
`__constructor`, checked `u128` instead of `i128`, no `try_call`, no
data-carrying enums) are noted on the contract or in
[soroban/README.md](soroban/README.md).
