# Constant-product AMM reference design

## Status and purpose

The current `examples/amm_kernel_contract.py` is an **experimental accounting
kernel**, not a deployable exchange and not production financial software. It
exists to turn a realistic DeFi workload into concrete compiler requirements.

The kernel already compiles directly from PySoroban source to Soroban Wasm and
exercises:

- unsigned fixed-fee arithmetic and integer division;
- address authorization;
- persistent reserve and share accounting;
- typed initialization and swap events;
- a minimum-output check before state mutation; and
- constant-product invariant tests in the Typed IR environment.

It intentionally does not transfer tokens. Supplying `amount_in` to the current
kernel is only a test input; no asset is received or paid out.

## Current formula

For an A-to-B swap with a 0.3% fee, the kernel computes:

```text
amount_in_with_fee = amount_in * 997
amount_out = (amount_in_with_fee * reserve_b)
             // (reserve_a * 1000 + amount_in_with_fee)
```

The swap is rejected by returning zero when it is uninitialized, has zero
input, produces zero output, misses `minimum_out`, or would exhaust reserve B.
Only an accepted quote changes the stored reserves and publishes `Swapped`.

## Safety boundary

The current implementation must not hold real assets because it does not yet
have all of the primitives required for safe token accounting:

- arithmetic is `u64` and wraps on overflow;
- token `transfer` calls returning `None` are not yet supported;
- there is no checked `u128`/`i128` or `mul_div` primitive;
- rejected operations return zero instead of raising a typed contract error;
- liquidity deposits and withdrawals do not transfer or verify token balances;
- the testing environment is not a full Soroban host and does not meter
  resources or model authorization trees; and
- the implementation has not received an independent security review.

These are explicit compiler-development gates, not deferred application polish.

## Path to a tokenized testnet AMM

### Gate 1 — asset-safe arithmetic

- Add checked `u128`/`i128` values through the frontend, Typed IR, XDR, Wasm
  backend, and test environment.
- Define multiplication, division, rounding, overflow, and division-by-zero
  semantics in the language specification.
- Add a checked `mul_div` operation suitable for reserve and share math.

### Gate 2 — contract composition and failure

- Add statically typed cross-contract calls returning `None`, required for
  Stellar token `transfer`.
- Add typed contract errors or an explicit abort operation so invalid swaps
  revert rather than returning an ambiguous numeric sentinel.
- Test authorization forwarding and atomic rollback on a real Soroban host.

### Gate 3 — liquidity lifecycle

- Store token contract addresses and retrieve typed `Address` values.
- Implement first deposit, proportional subsequent deposits, LP share minting,
  proportional withdrawals, and two swap directions.
- Emit typed deposit, withdrawal, and swap events with stable schemas.

### Gate 4 — testnet evidence

- Run invariant and boundary tests against both Typed IR and generated Wasm.
- Compare behavior with a small Rust/Soroban reference implementation.
- Deploy using test assets, publish contract IDs and artifact hashes, and record
  successful and rejected transactions.

Only after all four gates should the project describe the example as a
tokenized testnet AMM. Mainnet or production-funds use requires a separate
security review and is outside this reference workload.

## Acceptance properties

The eventual reference implementation should demonstrate, at minimum:

1. An unauthorized caller cannot deposit, withdraw, or swap another account's
   assets.
2. A rejected swap leaves reserves and token balances unchanged.
3. A successful swap satisfies `amount_out >= minimum_out`.
4. After fees, the reserve product does not decrease for a successful swap.
5. LP shares are monotonic and proportional within the documented rounding
   rule.
6. Contract storage agrees with actual token balances after every operation.
7. Clean builds produce byte-identical Wasm and a stable contract interface.

The AMM is the first workload because it exposes gaps in arithmetic, errors,
storage, authorization, events, and cross-contract calls without the much
larger scope of a lending protocol or route aggregator.
