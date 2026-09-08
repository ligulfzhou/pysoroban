# Changelog

All notable changes to PySoroban are documented here.

## Unreleased

- Add statically checked `u32` and `u64` floor division through the frontend,
  Typed IR, test environment, and direct Wasm backend.
- Add `Address.call_void(...)` for statically typed cross-contract calls whose
  target returns `None`.
- Add Soroban `i128` and `u128` ABI values, checked literals, comparisons,
  storage getters, typed events, collections, cross-contract results, artifact
  inspection, and Typed IR/Wasm differential coverage.
- Add checked `i128`/`u128` addition and subtraction with explicit Wasm traps
  on overflow; multiplication, division, and `mul_div` remain future work.
- Add a constant-product AMM accounting kernel with authorization, reserve
  storage, typed events, slippage checks, and invariant tests.
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
