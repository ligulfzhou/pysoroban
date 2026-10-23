# PySoroban Live Proof

An interactive proof page for the experimental PySoroban compiler.

The page demonstrates three separate pieces of the project:

- **Compile:** edit a soroban-examples port and compile it to Soroban-compatible Wasm in the browser. The tabs are Hello, Increment, Events, Errors, Auth, and CrossContract. The default source is `examples/hello_world/contract.py`. Pyodide installs the published `pysoroban-compiler` 0.19.0a2 wheel; the page reports the artifact size, exports and SHA-256 digest.
- **Ports:** the compiler tabs and the first deployment grid are those six Python ports. They are not the scripted testnet contract IDs.
- **Call:** simulate read-only calls against the scripted compiler-suite deployments through Stellar's public testnet RPC. Those sources live in `tests/fixtures/compiler_suite/`. No wallet or secret key is required.

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

The browser installs the published pure-Python wheel:

```text
public/compiler/pysoroban_compiler-0.19.0a2-py3-none-any.whl
```

SHA-256: `22ad350565ff66bbcf41177ca63f0ebbed02833f0cf0d408ebc61f86eb4e9d68`

That file is the PyPI `pysoroban-compiler` 0.19.0a2 release. The tree is
`0.19.0a3`, which is not published yet, so the demo keeps these bytes. A
local `pip wheel` build is not the published artifact.

## Testnet contracts

The scripted deployment record lives in [`../deployments/testnet.json`](../deployments/testnet.json). It is the compiler-suite fixtures, not the ports in the editor. The UI intentionally performs simulations for its public demo calls, so visitors cannot accidentally submit transactions or spend funds.
