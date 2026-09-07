# SCF Interest Form Draft

This is a working draft for the initial SCF interest form and the invited Build
submission. Replace bracketed team details before submission. Existing work is
presented as readiness evidence, not as work to be reimbursed.

## Current interest form field mapping

The public SCF Build Interest Form currently asks for the fields below. It does
not expose separate architecture, budget, or tranche fields at this first
stage. Keep these answers concise and use the website, repository, and
architecture links as supporting evidence. The detailed roadmap later in this
document is for the invited Build submission.

### Project Title

PySoroban

### Project Description

PySoroban is a deterministic, statically typed Python smart-contract language
for Stellar. It compiles a deliberately restricted Python subset directly to
Soroban-compatible WebAssembly, without generating Rust or embedding a Python
runtime on-chain. The project includes Soroban ABI and contract-spec generation,
a Typed IR, a Python testing environment, artifact validation, and a public
browser compiler. Our objective is to give Python developers a safe,
Stellar-native path from familiar source code to small, verifiable contracts.

### Project Category

Select the closest available **Developer Tooling / Infrastructure** category.
Do not select End-User Application if a developer-tool option is available.

### Current Traction

PySoroban has a working open-source v0.9 compiler and public live demo. Six
contracts generated directly from Python have been uploaded, deployed, and
invoked successfully on Stellar testnet, covering arithmetic, authorization,
instance storage, typed events, cross-contract calls, vectors, and maps. The
compiler has 56 automated tests plus 26 Typed IR/Wasm differential cases, with
CI on Python 3.9 and 3.13. The browser demo installs the real compiler wheel,
builds downloadable Wasm locally, links deployment transactions, and performs
read-only calls against the testnet contracts.

Evidence:

- https://github.com/ligulfzhou/pysoroban
- https://pysoroban.xyz
- https://github.com/ligulfzhou/pysoroban/blob/main/deployments/testnet.json
- https://github.com/ligulfzhou/pysoroban/actions

### Website

https://pysoroban.xyz

### Planned Stellar Integration

PySoroban is built specifically for Soroban rather than generic WebAssembly.
Its compiler generates Stellar `contractspecv0`, `contractenvmetav0`, and
`contractmetav0` sections; implements Soroban's 64-bit `Val` ABI; and lowers
Python operations to Stellar host functions for storage, address authorization,
events, vectors, maps, and cross-contract calls. Generated artifacts are
inspected, deployed, and invoked with the standard Stellar CLI. Award work
would expand the language and conformance suite, publish a stable PyPI package,
and deliver a reproducible v1.0 release verified on Stellar testnet and mainnet.

### Build Track

Open Track.

PySoroban is novel Stellar developer infrastructure but does not directly match
an active RFP. Do not choose the RFP Track unless SCF publishes a compiler or
alternative contract-language RFP that explicitly fits the project before
submission.

### Submitter Type, Email, and Team Description

- **Submitter type:** [Individual or registered entity — choose the truthful
  current status]
- **Email:** [Project contact email]
- **Team description:** PySoroban is currently led by [name], who designed and
  implemented the compiler, Typed IR, direct Wasm backend, Soroban ABI/XDR
  support, testing tools, testnet deployments, and browser demo. [Add team size,
  concise relevant experience, LinkedIn/GitHub links, and any named future
  contributors.]

### Markets and Jurisdictions

- **Target market:** Global / Not region-specific. PySoroban is open-source
  developer infrastructure usable by Stellar developers worldwide.
- **Team base:** [Select the team's actual country or incorporation location.]
- **Local currencies or payment rails:** No.

### Referral

Select **No** unless a specific SDF or Stellar ecosystem participant has agreed
to support the submission. If that changes, name only the confirmed referrer
and use their actual referral code.

## Project

**Project name:** PySoroban

**Suggested track:** Open Track

**Category:** Stellar/Soroban developer tooling and infrastructure

**One-line description:** PySoroban lets developers write statically typed
Python smart contracts that compile directly to Soroban-compatible WebAssembly,
without generated Rust or an embedded Python runtime.

**Website:** https://pysoroban.xyz

**Repository:** https://github.com/ligulfzhou/pysoroban

**Architecture:**
https://github.com/ligulfzhou/pysoroban/blob/main/docs/ARCHITECTURE.md

## What are you building?

PySoroban is a new contract language and compiler for Stellar. It accepts a
small, deterministic, statically typed subset of Python and compiles it directly
through a backend-independent Typed IR into Soroban-compatible Wasm. It also
generates the contract specification and protocol metadata used by Stellar CLI,
provides a fast Python testing environment, and verifies compiler behavior by
comparing Typed IR execution with independently executed Wasm.

The project is designed as developer infrastructure, not as a Python runtime on
the blockchain. Unsupported dynamic Python behavior is rejected at compile
time, and deployed contracts contain neither Rust artifacts nor a Python
interpreter.

## Problem and ecosystem value

Soroban's primary contract workflow is excellent for Rust developers, but it
creates a substantial language and toolchain barrier for the much larger Python
developer population. This limits who can prototype, teach, and ultimately
ship Stellar smart contracts.

PySoroban aims to make Stellar contract development approachable to Python
developers while retaining deterministic execution, static contract interfaces,
small Wasm artifacts, and compatibility with existing Stellar deployment tools.
It can expand the Stellar developer funnel without requiring the network or
Soroban host to support a new runtime.

## Why Stellar?

PySoroban targets Soroban specifically rather than generic WebAssembly. The
compiler emits Stellar contract XDR, uses Soroban's `Val` ABI and protocol host
functions, supports address authorization, instance storage, typed events,
cross-contract calls, vectors, and maps, and validates generated artifacts with
Stellar CLI and Stellar testnet.

Stellar is not an interchangeable deployment target for this project: the
language surface, type system, metadata, host calls, testing strategy, and
release criteria are all built around Soroban.

## Current status and readiness

An open-source compiler MVP is already live and independently verifiable:

- Python source compiles directly to deterministic Soroban Wasm.
- Six reference contracts have been accepted and invoked on Stellar testnet.
- The compiler supports typed integers and host objects, control flow, bounded
  loops, storage, authorization, events, cross-contract calls, vectors, and
  maps.
- The repository includes unit, Typed IR, artifact, and IR/Wasm differential
  tests running on Python 3.9 and 3.13 in CI.
- A public Cloudflare demo loads the actual Python compiler wheel in the browser,
  lets visitors edit and compile contracts, and performs read-only calls against
  deployed testnet contracts.

This work establishes feasibility. The requested award would fund future work
needed to turn the experimental compiler into a stable, documented v1.0
developer tool; it would not reimburse the existing MVP.

## Differentiation

PySoroban is not a Python-to-Rust source generator. Its Typed IR and Wasm
backend are compiler components with explicit Soroban operations and ABI
lowering. It also does not bundle a general Python VM, which keeps the on-chain
artifact small and gives the language a reviewable deterministic boundary.

The combination of Python syntax, static contract types, direct Wasm output,
Soroban-native metadata, deterministic builds, and multi-layer semantic
validation is the project's core technical contribution.

## Target users and measurable impact

The initial target users are Python developers evaluating or building on
Stellar, educators creating Soroban material, and teams that want a rapid
contract prototyping path with standard Stellar deployment tooling.

Success will be measured through verifiable engineering and launch outputs:

- stable compiler releases installable from PyPI;
- reference applications compiled by PySoroban and invoked on testnet/mainnet;
- protocol compatibility and conformance results published in CI;
- public documentation covering the supported language and Soroban interfaces;
- independently reproducible artifacts and release hashes;
- downstream contracts or examples built from the public package after v1.0.

## Real-world validation strategy

PySoroban will be validated with progressively harder DeFi workloads rather
than only small syntax examples:

1. A constant-product AMM reference contract exercises checked asset math,
   token transfers, authorization, persistent state, liquidity shares, and
   contract events.
2. A bounded lending kernel exercises oracle calls, collateral and liability
   accounting, health-factor checks, and multi-contract composition. This is a
   compatibility and compiler-validation workload, not a promise to fork or
   replace the complete Blend protocol.
3. The existing LumAgg execution contract is used as the flagship application
   workload. Its PySoroban implementation exercises nested route types,
   multi-hop and split swaps, dynamic cross-contract calls, authorization, and
   atomic slippage enforcement.

The AMM and lending contracts are reference software and will be deployed with
test assets only. They are not represented as audited production financial
protocols. The LumAgg port will be mandatory on testnet; any production-funds
deployment will require a separate security review and will not replace the
existing Rust production contract merely to satisfy a grant milestone.

## Proposed roadmap and budget

**Total request: USD 60,000 worth of XLM**

SCF's four-payment schedule would be: initial award payment $6,000 (10%),
Tranche 1 $12,000 (20%), Tranche 2 $18,000 (30%), and Tranche 3 $24,000 (40%).
The project duration is approximately five months. Audit fees are excluded.

### Tranche 1 — Production language core

**Timeline:** 6 weeks after award acceptance

**Payment:** $12,000

Deliverables:

- Add checked `i128`/`u128` asset arithmetic and the fixed-point primitives
  required by Soroban DeFi contracts, with explicit overflow, division, and
  rounding semantics.
- Implement statically typed user-defined contract structs and enums across
  parsing, type checking, Typed IR, contract XDR, Wasm lowering, and tests.
- Add safe mutable operations for `Vec[T]` and `Map[K, V]`, with explicit
  semantics and Soroban host lowering.
- Publish a versioned language specification defining accepted syntax, types,
  integer behavior, control flow, determinism, and rejected Python features.
- Improve source diagnostics for type, ABI, and unsupported-feature errors.
- Compile and execute a constant-product AMM reference implementation in the
  local differential test environment, covering pool initialization,
  deposit/withdraw, liquidity-share accounting, and swaps with a minimum-output
  check.

Completion evidence:

- Public release and tagged source containing all deliverables.
- Stellar CLI parses every new example interface.
- Unit and IR/Wasm differential suites cover every new type and collection
  operation with no regressions.
- Examples compile reproducibly from a clean install of the released wheel.
- AMM invariant tests demonstrate reserve conservation, monotonic share
  accounting, and rejection of invalid or under-minimum swaps.

### Tranche 2 — Testnet hardening and developer workflow

**Timeline:** 8 weeks after Tranche 1

**Payment:** $18,000

Deliverables:

- Add first-class CLI workflows for building, deploying, invoking, and recording
  PySoroban contract deployments using standard Stellar tooling.
- Build a protocol conformance suite covering the supported ABI, storage,
  authorization, events, cross-contract calls, collections, and user-defined
  types on Stellar testnet.
- Add property-based and malformed-input testing for the frontend, XDR encoder,
  artifact inspector, and Wasm value conversions.
- Publish the compiler package to PyPI with reproducible release artifacts,
  checksums, compatibility metadata, and upgrade documentation.
- Expand the browser lab to demonstrate the new language features and expose
  testnet transaction evidence.
- Deploy and exercise the PySoroban AMM on Stellar testnet with test assets,
  and publish parity tests against an equivalent Rust/Soroban reference.
- Deliver a bounded Blend-style lending kernel on testnet covering supply,
  withdraw, borrow, repay, an oracle interface, and collateral health checks.
  Backstop, emissions, governance, liquidation auctions, and production-funds
  deployment are explicitly outside this milestone.

Completion evidence:

- A clean environment can install PySoroban from PyPI, compile, deploy, and
  invoke all reference contracts on testnet using documented commands.
- CI publishes a machine-readable conformance report and deterministic hashes.
- All reference deployment IDs and transactions are public and linked from the
  demo.
- AMM and lending-kernel invariant suites and end-to-end testnet transactions
  are reproducible from the tagged release.

### Tranche 3 — v1.0 and mainnet-ready public launch

**Timeline:** 8 weeks after Tranche 2

**Payment:** $24,000

Deliverables:

- Freeze and publish the PySoroban v1.0 language, ABI support matrix, semantic
  versioning policy, and compatibility guarantees.
- Complete security hardening, resource-bound tests, compiler fuzzing, and
  remediation of findings from any SCF-supported external review.
- Publish end-to-end tutorials, API/CLI reference, architecture documentation,
  migration guidance, and a maintainer release/incident process.
- Produce signed, reproducible v1.0 wheels and example Wasm artifacts with an
  SBOM and public checksums.
- Port the core LumAgg aggregator execution contract to PySoroban, including
  typed routes, multi-hop and split execution, token authorization,
  cross-contract DEX calls, atomic failure, and minimum-output enforcement.
- Run the PySoroban LumAgg contract against testnet DEX fixtures and publish
  behavioral parity results against the existing Rust implementation.
- Deploy non-custodial, non-production reference contracts compiled by v1.0 to
  Stellar mainnet and publish verified contract IDs, hashes, invocations, and a
  recorded end-to-end demonstration. A production-funds LumAgg migration is
  outside the acceptance criteria unless the port receives an appropriate
  external security review.

Completion evidence:

- Public v1.0 release installs and reproduces documented artifact hashes.
- Mainnet accepts the reference artifacts and their interfaces are inspectable
  with standard Stellar tools.
- Public CI, conformance, security, documentation, and mainnet evidence are
  linked from the project website.
- A public LumAgg testnet demonstration completes quote, route construction,
  transaction simulation, authorization, execution, and result verification
  using a contract compiled directly from Python.

## Team

**Lead:** [Full legal name / public profile]

**Role:** Compiler architecture, implementation, testing, Stellar integration,
documentation, and release engineering.

**Relevant experience:** [Add concise evidence: compiler/language work, Python,
WebAssembly, blockchain, Stellar/Soroban, shipped open-source projects, and
links. Do not use generic biography text.]

**Additional contributors or contractors:** [Name and exact future role, or
state that this is currently a solo-led open-source project.]

## Sustainability

PySoroban will remain Apache-2.0 open source. After v1.0, maintenance will focus
on Stellar protocol compatibility, security fixes, reproducible releases, and
carefully versioned language additions. The small language boundary and
dependency-free compiler are deliberate choices to keep long-term maintenance
tractable.

## Items to complete before submission

- Replace all bracketed team details with verifiable links.
- Confirm the exact current SCF round and submission deadline.
- Add an SCF referrer and referral code if one is available; do not invent one.
- Confirm whether the form expects a single interest-form summary or the full
  tranche text at this stage.
- Recheck budget and timeline against the final team allocation.
- Use only future work in the requested budget.
