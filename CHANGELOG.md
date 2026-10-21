# Changelog

All notable changes to PySoroban are documented here.

## 0.16.0a1 — 2026-10-21

- Add `Option`, `Result[T, u32]`, `Tuple`, `Val`, and `@union`. A union case
  carries one payload. `try_*` calls protocol `try_call` and returns that
  `Result`. The test host rolls a caught `fail` back.
- Allow nested `Vec` and `Map` values. Map keys stay scalar.
- `atomic_multiswap` uses `try_void`. `other_custom_types` echoes the new
  types. `i256` and multi-field enum variants are still absent.

## 0.15.0a1 — 2026-10-21

- Add `BytesN[N]`, `to_xdr`, byte ordering, `u256.to_be_bytes` /
  `from_be_bytes`, and `Address.to_strkey`.
- The test host encodes `to_xdr` as ScVal XDR. A non-StrKey address is the
  contract id SHA-256 of that string. Generated Wasm calls the host.
- Port `merkle_distribution`.

## 0.14.0a1 — 2026-10-21

- Add the `u256` contract type. Literals, comparisons, storage, vectors, and
  cross-contract returns use the protocol object. Checked `+`, `-`, `*`, and
  `//` call the host `u256` operations and trap on overflow or division by zero.

## 0.13.0a1 — 2026-10-21

- Check `i128` floor division. The protocol `i256` divide truncates toward
  zero; an inexact mixed-sign quotient is decreased by one so the result
  matches Python `//`. Division by zero traps in the host. A quotient that
  does not fit in `i128`, including the minimum divided by `-1`, traps.

## 0.12.0a1 — 2026-10-21

- Document Stellar CLI and stellar-sdk invocation in `docs/INVOKE.md`. The
  compiler still does not submit transactions or speak RPC.
- Load compiler 0.12.0a1 in the browser demo.

- Port the stellar/soroban-examples tree under `examples/soroban/`. Each
  example is a Python contract with tests, or a README that names the missing
  host or language feature.
- Add a tokenized constant-product pool, atomic swap, timelock, single-offer
  exchange, and mint limiter on the SEP-41 style token.
- Direct cross-contract calls in the test host authorize the caller and keep
  the invocation's address list, so a contract can spend its own balance.
- Keep a Wasm local for a name declared in only one branch of `if`.

## 0.11.0a1 — 2026-10-21

- Check `u128` multiplication and floor division through a `u256`
  intermediate. A product that does not fit in `u128`, or a zero divisor,
  traps. Check `i128` multiplication the same way through `i256`. `i128`
  floor division stays rejected because the host divide truncates.
- Add `ledger.sequence`, `timestamp`, `version`, and `network_id`, plus
  `env.current_contract_address()`.
- Add `crypto.sha256`, `keccak256`, and `ed25519_verify`, `log(String)`,
  `prng.bytes` and `prng.u64`, and `String` / `Bytes` conversions, slicing,
  and append.
- Add `address.require_auth_for(...)`.
- Add `deploy.upload`, `deploy.contract`, `deploy.with_constructor`,
  `deploy.upgrade`, and `deploy.asset`.
- Add `examples/token_contract.py`, a contract-owned SEP-41 style token with
  checked `u128` balances. It is not the Stellar Asset Contract.
- The test host records these calls without reproducing the real curve, PRNG,
  TTL expiry, or contract-address derivation. See `docs/LANGUAGE.md`.

## 0.10.0a1 — 2026-10-21

- Add `@struct` and `@enum`, written into `contractspecv0` as Soroban UDT
  struct and enum entries. Structs are maps of field symbols. Enums are
  `u32` values.
- Add `storage.persistent` and `storage.temporary`, `get(key, Type)`,
  `get_address`, `remove`, and TTL extension. Instance storage keeps its
  previous Wasm for contracts that do not use the new methods.
- Add statement updates for `Vec` (`push`, `set`, `insert`, `remove`, `pop`)
  and `Map` (`set`, `remove`), plus empty `Vec()` and `Map()` constructors.
- Specify the current language, including integer wrapping and checked
  overflow, in `docs/LANGUAGE.md`.
- Give `CompileError` stable `E####` codes alongside line and column.
- Lock Wasm hashes for the examples and integer programs whose source did not
  change.
- Add `@error` enums and `fail(Error.CASE)`. Failures call protocol-25
  `fail_with_error` and roll back the test invocation's storage and events.
- Change the AMM kernel so rejected quotes, initialization, and swaps trap
  with `KernelError` instead of returning `u128(0)`.

## 0.9.0a2 — 2026-10-09

- Add statically checked `u32` and `u64` floor division through the frontend,
  Typed IR, test environment, and direct Wasm backend.
- Add `Address.call_void(...)` for statically typed cross-contract calls whose
  target returns `None`.
- Add Soroban `i128` and `u128` ABI values, checked literals, comparisons,
  storage getters, typed events, collections, cross-contract results, artifact
  inspection, and Typed IR/Wasm differential coverage.
- Add checked `i128`/`u128` addition and subtraction with explicit Wasm traps
  on overflow.
- Add `u128.mul_div_floor()` using checked Protocol 25 `u256` multiplication
  and division, floor rounding, and overflow-checked narrowing to `u128`.
- Add a constant-product AMM accounting kernel with authorization, reserve
  storage, typed events, slippage checks, and invariant tests.
- Migrate the AMM kernel from wrapping `u64` to checked `u128`, add
  large-reserve invariant coverage, and verify it on Stellar testnet.
- Document the AMM safety boundary and the compiler gates required before a
  tokenized testnet deployment.

## 0.9.0a1 — 2026-09-07

First public alpha release of `pysoroban-compiler`.

- Compile a statically typed Python subset directly to Soroban-compatible Wasm.
- Generate Soroban environment metadata, contract specifications, and events.
- Support scalar values, authorization, instance storage, cross-contract calls,
  typed events, vectors, and maps.
- Inspect, validate, and reproducibly verify generated Wasm artifacts.
- Test contracts with the Typed IR environment and IR/Wasm differential suite.

This release is experimental and must not be used to control production funds.
