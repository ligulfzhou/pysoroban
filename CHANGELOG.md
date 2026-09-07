# Changelog

All notable changes to PySoroban are documented here.

## 0.9.0a1 — 2026-09-07

First public alpha release of `pysoroban-compiler`.

- Compile a statically typed Python subset directly to Soroban-compatible Wasm.
- Generate Soroban environment metadata, contract specifications, and events.
- Support scalar values, authorization, instance storage, cross-contract calls,
  typed events, vectors, and maps.
- Inspect, validate, and reproducibly verify generated Wasm artifacts.
- Test contracts with the Typed IR environment and IR/Wasm differential suite.

This release is experimental and must not be used to control production funds.
