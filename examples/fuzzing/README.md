# fuzzing

The upstream crate is the timelock contract plus a cargo-fuzz harness. The harness is a Rust test target, not a contract. The claimable-balance logic is ported as `../timelock/contract.py`.
