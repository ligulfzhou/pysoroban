# PySoroban Live Proof

An interactive proof page for the experimental PySoroban compiler.

The page demonstrates three separate pieces of the project:

- **Compile:** edit a soroban-examples port and compile it to Soroban-compatible Wasm in the browser. The default source is `examples/hello_world/contract.py`. Pyodide runs the actual `pysoroban` compiler wheel; the page reports the artifact size, exports and SHA-256 digest.
- **Ports:** the compiler tabs and the first deployment grid are the Python ports (`hello_world`, `increment`, `events`, `errors`, `auth`, `cross_contract`). They are not deployed as the historical contract IDs.
- **Call:** simulate read-only calls against the September 2026 compiler-suite deployments through Stellar's public testnet RPC. Those sources now live in `tests/fixtures/compiler_suite/`. No wallet or secret key is required.

This is an experimental language-tooling prototype, not a production smart-contract platform.

## Run locally

Requires Node.js 22.13 or newer.

```bash
npm install
npm run dev
```

Open <http://localhost:3000>.

The current Cloudflare deployment is available at <https://pysoroban.xyz>.
The `workers.dev` address remains enabled as a deployment fallback.

## Verify

```bash
npm test
npm run lint
```

`npm test` creates a production build and checks the rendered page for the compiler, deployment and live-call surfaces.

## Browser compiler artifact

The browser installs the pure-Python wheel at:

```text
public/compiler/pysoroban_compiler-0.12.0a1-py3-none-any.whl
```

Rebuild it from the repository root after changing the Python compiler:

```bash
python3 -m pip wheel . --no-deps --wheel-dir web/public/compiler
```

## Testnet contracts

The September 2026 deployment evidence lives in [`../deployments/testnet.json`](../deployments/testnet.json). That record is the former compiler suite, not the ports in the editor. The UI intentionally performs simulations for its public demo calls, so visitors cannot accidentally submit transactions or spend funds.
