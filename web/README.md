# PySoroban Live Proof

An interactive proof page for the experimental PySoroban compiler.

The page demonstrates three separate pieces of the project:

- **Compile:** edit a Python contract and compile it to Soroban-compatible Wasm in the browser. Pyodide runs the actual `pysoroban` compiler wheel; the page reports the artifact size, exports and SHA-256 digest.
- **Deploy:** inspect five contracts compiled by the current PySoroban compiler and deployed to Stellar testnet, with links to their contract and deployment transaction records.
- **Call:** simulate read-only calls against those live contracts through Stellar's public testnet RPC. No wallet or secret key is required.

This is an experimental language-tooling prototype, not a production smart-contract platform.

## Run locally

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Open <http://localhost:3000>.

The current Cloudflare deployment is available at
<https://pysoroban-live-proof.ligulfzhou53.workers.dev>.

## Verify

```bash
npm test
npm run lint
```

`npm test` creates a production build and checks the rendered page for the compiler, deployment and live-call surfaces.

## Browser compiler artifact

The browser installs the pure-Python wheel at:

```text
public/compiler/pysoroban_compiler-0.7.0-py3-none-any.whl
```

Rebuild it from the repository root after changing the Python compiler:

```bash
python3 -m pip wheel . --no-deps --wheel-dir web/public/compiler
```

## Testnet contracts

The canonical deployment evidence lives in [`../deployments/testnet.json`](../deployments/testnet.json). The UI intentionally performs simulations for its public demo calls, so visitors cannot accidentally submit transactions or spend funds.
