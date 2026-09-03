"use client";

import { useMemo, useState } from "react";

const PYODIDE_URL =
  "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.mjs";
const COMPILER_WHEEL =
  "/compiler/pysoroban_compiler-0.7.0-py3-none-any.whl";
const RPC_URL = "https://soroban-testnet.stellar.org";
const SOURCE_ACCOUNT =
  "GBTZVQRXWUTOBJZU5VEZZVNOQIEP7TIHORJFG26FVAHJGCUPDC22BULU";

const contracts = {
  math: {
    name: "Math",
    file: "math_contract.py",
    id: "CB53RXQYMVPOLRG7UJHYWTXWIYI6C5CRHZ5O2WOFFN6A7LCBVXCIE3NL",
    hash: "330609a5…755fa2",
    transaction:
      "eced9c472f941f19e6ede81a675ab8a07fe3265d5e0ee28ac91f130ee63a34b2",
    source: `from pysoroban import boolean, contract, i32, public


@contract
class Math:
    @public
    def add(self, left: i32, right: i32) -> i32:
        """Add two signed 32-bit integers."""
        return left + right

    @public
    def max(self, left: i32, right: i32) -> i32:
        if left > right:
            return left
        return right

    @public
    def is_positive(self, value: i32) -> boolean:
        return value > 0

    @public
    def sum_to(self, stop: i32) -> i32:
        total: i32 = 0
        for value in range(stop):
            total = total + value
        return total
`,
  },
  counter: {
    name: "Counter",
    file: "counter_contract.py",
    id: "CBUIEGZBBVEITJGOINR2IGAD4QPDAFFSJHJNPZI5WPSCLX6L5F3UU6CT",
    hash: "ddeab1cc…907bfa",
    transaction:
      "451139d86340174eb41db7b21212e6d02ad7bc40221d499d02edb9bb8ba2a6c0",
    source: `from pysoroban import Address, contract, i32, public, storage


@contract
class Counter:
    @public
    def increment(self, user: Address, amount: i32) -> i32:
        user.require_auth()
        current: i32 = 0
        if storage.instance.has(user):
            current = storage.instance.get_i32(user)
        updated: i32 = current + amount
        storage.instance.set(user, updated)
        return updated

    @public
    def value(self, user: Address) -> i32:
        if storage.instance.has(user):
            return storage.instance.get_i32(user)
        return 0
`,
  },
  typed: {
    name: "TypedEvents",
    file: "typed_events_contract.py",
    id: "CBL2NYIUMMVXWYRD4SDBJ6CLPWPBSDCMHXBFVKR2X74UPVSBAGHFBFXN",
    hash: "9f4da43c…e0393a7",
    transaction:
      "48d4fdaa7d7a72175ba44edb3a44164c348415bd3a685ef38920c460b72b5ead",
    source: `from pysoroban import Address, Bytes, String, Symbol, Topic, contract, event, events, i64, public, storage, u32, u64


@event
class Updated:
    """A total changed after its owner authorized an update."""

    owner: Topic[Address]
    value: u64


@contract
class TypedEvents:
    @public
    def record(self, owner: Address, amount: u64) -> u64:
        owner.require_auth()
        key: Symbol = Symbol("total")
        current: u64 = u64(0)
        if storage.instance.has(key):
            current = storage.instance.get_u64(key)
        updated: u64 = current + amount
        storage.instance.set(key, updated)
        events.publish(Updated(owner, updated))
        return updated

    @public
    def offset(self, value: i64) -> i64:
        return value + i64(-7)

    @public
    def generation(self) -> u32:
        return u32(2)

    @public
    def label(self) -> String:
        return String("PySoroban")

    @public
    def fingerprint(self) -> Bytes:
        return Bytes(b"py-soroban")
`,
  },
  proxy: {
    name: "MathProxy",
    file: "cross_contract.py",
    id: "CCLC6RU3HXIVIBWMMF6K6OEIDSMY7FBKLSDVI46A7Z3TKM65Z4P4OHEU",
    hash: "b9a714ac…c0b25a",
    transaction:
      "3e49995bca6152c603846a711fcde6e8ccc2b02c9773592b8e3c8428ddc65553",
    source: `from pysoroban import Address, Symbol, contract, i32, public


@contract
class MathProxy:
    @public
    def add_with(self, target: Address, left: i32, right: i32) -> i32:
        return target.call_i32(Symbol("add"), left, right)

    @public
    def sum_with(self, target: Address, stop: i32) -> i32:
        return target.call_i32(Symbol("sum_to"), stop)
`,
  },
  vectors: {
    name: "VectorMath",
    file: "vector_contract.py",
    id: "CABB6XS7ERQNYLJUKW2BCAPN7IZL4DNY3Q53RMC2GB72N2HLWSXFSOZX",
    hash: "fc9fc3c4…456f3f",
    transaction:
      "5b44dba312e5a3de3663e8dc2df770c955347325e0b541d1b962b33a4880b0b5",
    source: `from pysoroban import Vec, contract, i32, public


@contract
class VectorMath:
    @public
    def count(self, values: Vec[i32]) -> i32:
        return len(values)

    @public
    def first(self, values: Vec[i32]) -> i32:
        return values[0]

    @public
    def sum(self, values: Vec[i32]) -> i32:
        total: i32 = 0
        for index in range(len(values)):
            total = total + values[index]
        return total

    @public
    def echo(self, values: Vec[i32]) -> Vec[i32]:
        return values
`,
  },
} as const;

type ContractKey = keyof typeof contracts;
type Pyodide = {
  loadPackage: (name: string) => Promise<void>;
  runPythonAsync: (code: string) => Promise<unknown>;
  globals: { set: (name: string, value: unknown) => void };
};

let pyodidePromise: Promise<Pyodide> | null = null;

function getPyodide(): Promise<Pyodide> {
  if (!pyodidePromise) {
    pyodidePromise = (async () => {
      const dynamicImport = new Function("url", "return import(url)") as (
        url: string,
      ) => Promise<{ loadPyodide: () => Promise<Pyodide> }>;
      const pyodideModule = await dynamicImport(PYODIDE_URL);
      const runtime = await pyodideModule.loadPyodide();
      await runtime.loadPackage("micropip");
      runtime.globals.set("compiler_wheel", COMPILER_WHEEL);
      await runtime.runPythonAsync(
        "import micropip\nawait micropip.install(compiler_wheel)",
      );
      return runtime;
    })();
  }
  return pyodidePromise;
}

async function compileInBrowser(source: string) {
  const runtime = await getPyodide();
  runtime.globals.set("contract_source", source);
  const raw = await runtime.runPythonAsync(`
import base64, json
from pysoroban import compile_source

compiled = compile_source(contract_source, "browser_contract.py")
json.dumps({
    "contract": compiled.contract.name,
    "functions": [function.name for function in compiled.contract.functions],
    "events": [event.name for event in compiled.contract.events],
    "size": len(compiled.wasm),
    "wasm": base64.b64encode(compiled.wasm).decode("ascii"),
})
`);
  return JSON.parse(String(raw)) as {
    contract: string;
    functions: string[];
    events: string[];
    size: number;
    wasm: string;
  };
}

async function simulateCall(
  contractId: string,
  method: string,
  args: Array<{ value: number | string | number[]; type: "i32" | "address" | "vec_i32" }>,
) {
  const Stellar = await import("@stellar/stellar-sdk");
  const server = new Stellar.rpc.Server(RPC_URL);
  const source = await server.getAccount(SOURCE_ACCOUNT);
  const transaction = new Stellar.TransactionBuilder(source, {
    fee: Stellar.BASE_FEE,
    networkPassphrase: Stellar.Networks.TESTNET,
  })
    .addOperation(
      new Stellar.Contract(contractId).call(
        method,
        ...args.map((arg) => arg.type === "vec_i32"
          ? Stellar.xdr.ScVal.scvVec(
              (arg.value as number[]).map((value) =>
                Stellar.nativeToScVal(value, { type: "i32" }),
              ),
            )
          : Stellar.nativeToScVal(arg.value as number | string, { type: arg.type }),
        ),
      ),
    )
    .setTimeout(30)
    .build();
  const simulation = await server.simulateTransaction(transaction);
  if (!Stellar.rpc.Api.isSimulationSuccess(simulation) || !simulation.result) {
    throw new Error("Testnet simulation failed. The contract may have expired.");
  }
  return {
    value: Stellar.scValToNative(simulation.result.retval),
    ledger: simulation.latestLedger,
  };
}

function truncate(value: string, start = 8, end = 6) {
  return `${value.slice(0, start)}…${value.slice(-end)}`;
}

export function PySorobanLab() {
  const [selected, setSelected] = useState<ContractKey>("math");
  const [source, setSource] = useState(contracts.math.source);
  const [compileState, setCompileState] = useState<
    "idle" | "loading" | "success" | "error"
  >("idle");
  const [compileResult, setCompileResult] = useState<{
    contract: string;
    functions: string[];
    events: string[];
    size: number;
    wasm: string;
    sha256: string;
  } | null>(null);
  const [compileError, setCompileError] = useState("");
  const [left, setLeft] = useState(7);
  const [right, setRight] = useState(35);
  const [mathResult, setMathResult] = useState<string>("—");
  const [counterUser, setCounterUser] = useState(SOURCE_ACCOUNT);
  const [counterResult, setCounterResult] = useState<string>("—");
  const [typedResult, setTypedResult] = useState<string>("—");
  const [proxyResult, setProxyResult] = useState<string>("—");
  const [vectorInput, setVectorInput] = useState("3, 5, 8");
  const [vectorResult, setVectorResult] = useState<string>("—");
  const [callState, setCallState] = useState<"idle" | "math" | "counter" | "typed" | "proxy" | "vectors">(
    "idle",
  );
  const [callLedger, setCallLedger] = useState<number | null>(null);
  const active = contracts[selected];

  const lineCount = useMemo(() => source.split("\n").length, [source]);

  function selectContract(key: ContractKey) {
    setSelected(key);
    setSource(contracts[key].source);
    setCompileState("idle");
    setCompileResult(null);
    setCompileError("");
  }

  async function handleCompile() {
    setCompileState("loading");
    setCompileError("");
    try {
      const result = await compileInBrowser(source);
      const bytes = Uint8Array.from(atob(result.wasm), (character) =>
        character.charCodeAt(0),
      );
      const digest = await crypto.subtle.digest("SHA-256", bytes);
      const sha256 = Array.from(new Uint8Array(digest))
        .map((value) => value.toString(16).padStart(2, "0"))
        .join("");
      setCompileResult({ ...result, sha256 });
      setCompileState("success");
    } catch (error) {
      setCompileError(error instanceof Error ? error.message : String(error));
      setCompileState("error");
    }
  }

  function downloadWasm() {
    if (!compileResult) return;
    const bytes = Uint8Array.from(atob(compileResult.wasm), (character) =>
      character.charCodeAt(0),
    );
    const url = URL.createObjectURL(
      new Blob([bytes], { type: "application/wasm" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${compileResult.contract.toLowerCase()}.wasm`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function callMath() {
    setCallState("math");
    setMathResult("…");
    try {
      const result = await simulateCall(contracts.math.id, "add", [
        { value: left, type: "i32" },
        { value: right, type: "i32" },
      ]);
      setMathResult(String(result.value));
      setCallLedger(result.ledger);
    } catch (error) {
      setMathResult(error instanceof Error ? error.message : "Call failed");
    } finally {
      setCallState("idle");
    }
  }

  async function callCounter() {
    setCallState("counter");
    setCounterResult("…");
    try {
      const result = await simulateCall(contracts.counter.id, "value", [
        { value: counterUser, type: "address" },
      ]);
      setCounterResult(String(result.value));
      setCallLedger(result.ledger);
    } catch (error) {
      setCounterResult(error instanceof Error ? error.message : "Call failed");
    } finally {
      setCallState("idle");
    }
  }

  async function callTyped() {
    setCallState("typed");
    setTypedResult("…");
    try {
      const result = await simulateCall(contracts.typed.id, "label", []);
      setTypedResult(String(result.value));
      setCallLedger(result.ledger);
    } catch (error) {
      setTypedResult(error instanceof Error ? error.message : "Call failed");
    } finally {
      setCallState("idle");
    }
  }

  async function callProxy() {
    setCallState("proxy");
    setProxyResult("…");
    try {
      const result = await simulateCall(contracts.proxy.id, "add_with", [
        { value: contracts.math.id, type: "address" },
        { value: left, type: "i32" },
        { value: right, type: "i32" },
      ]);
      setProxyResult(String(result.value));
      setCallLedger(result.ledger);
    } catch (error) {
      setProxyResult(error instanceof Error ? error.message : "Call failed");
    } finally {
      setCallState("idle");
    }
  }

  async function callVectors() {
    setCallState("vectors");
    setVectorResult("…");
    try {
      const values = vectorInput.split(",").map((value) => Number(value.trim()));
      if (!values.length || values.some((value) => !Number.isInteger(value))) {
        throw new Error("Enter comma-separated integers");
      }
      const result = await simulateCall(contracts.vectors.id, "sum", [
        { value: values, type: "vec_i32" },
      ]);
      setVectorResult(String(result.value));
      setCallLedger(result.ledger);
    } catch (error) {
      setVectorResult(error instanceof Error ? error.message : "Call failed");
    } finally {
      setCallState("idle");
    }
  }

  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="PySoroban home">
          <span className="brand-mark">Py</span>
          <span>PySoroban</span>
        </a>
        <nav aria-label="Main navigation">
          <a href="#compiler">Compiler</a>
          <a href="#testing">Testing</a>
          <a href="#deployments">Deployments</a>
          <a href="#live-calls">Live calls</a>
        </nav>
        <a
          className="github-link"
          href="https://github.com/stellar"
          target="_blank"
          rel="noreferrer"
        >
          Protocol 25 <span aria-hidden="true">↗</span>
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">
            <span className="live-dot" /> Live on Stellar testnet
          </div>
          <h1>
            Python contracts.
            <br />
            <span>Real Stellar Wasm.</span>
          </h1>
          <p>
            A deterministic, statically typed Python contract language that
            compiles directly to Soroban-compatible WebAssembly. No generated
            Rust. No Python runtime on-chain.
          </p>
          <div className="hero-actions">
            <a className="primary-action" href="#compiler">
              Try the compiler <span aria-hidden="true">↓</span>
            </a>
            <a className="text-action" href="#live-calls">
              Call a live contract <span aria-hidden="true">→</span>
            </a>
          </div>
        </div>
        <div className="pipeline-card" aria-label="Compilation pipeline">
          <div className="pipeline-top">
            <span>Build pipeline</span>
            <span className="pipeline-status">verified</span>
          </div>
          {[
            ["01", "Typed Python", "source"],
            ["02", "PySoroban IR", "checked"],
            ["03", "Soroban Wasm", "direct"],
            ["04", "Stellar testnet", "deployed"],
          ].map(([step, title, status], index) => (
            <div className="pipeline-step" key={title}>
              <span className="step-number">{step}</span>
              <span className="step-title">{title}</span>
              <span className="step-status">{status}</span>
              {index < 3 && <span className="step-line" />}
            </div>
          ))}
        </div>
      </section>

      <section className="proof-strip" aria-label="Project facts">
        <div><strong>0</strong><span>Rust artifacts</span></div>
        <div><strong>1,125 B</strong><span>Typed Wasm</span></div>
        <div><strong>45/45</strong><span>Compiler tests</span></div>
        <div><strong>5</strong><span>Live contracts</span></div>
      </section>

      <section className="section compiler-section" id="compiler">
        <div className="section-heading">
          <div>
            <span className="section-kicker">01 / Browser compiler</span>
            <h2>Edit Python. Build Wasm.</h2>
          </div>
          <p>
            Compilation runs locally in your browser using the actual PySoroban
            Python package. Your source never leaves this page.
          </p>
        </div>

        <div className="workbench">
          <div className="editor-panel">
            <div className="panel-bar">
              <div className="contract-tabs" role="tablist" aria-label="Example contracts">
                {(Object.keys(contracts) as ContractKey[]).map((key) => (
                  <button
                    key={key}
                    role="tab"
                    aria-selected={selected === key}
                    className={selected === key ? "active" : ""}
                    onClick={() => selectContract(key)}
                  >
                    {contracts[key].name}
                  </button>
                ))}
              </div>
              <span className="file-name">{active.file}</span>
            </div>
            <div className="code-editor">
              <div className="line-numbers" aria-hidden="true">
                {Array.from({ length: lineCount }, (_, index) => (
                  <span key={index}>{index + 1}</span>
                ))}
              </div>
              <textarea
                value={source}
                onChange={(event) => setSource(event.target.value)}
                aria-label="Python contract source"
                spellCheck={false}
              />
            </div>
          </div>

          <aside className="build-panel">
            <div className="build-header">
              <span>Build artifact</span>
              <span className={`build-state ${compileState}`}>
                {compileState === "success" ? "valid Wasm" : compileState}
              </span>
            </div>
            <div className="artifact-visual">
              <span className="wasm-cube">W</span>
              <div>
                <strong>{compileResult?.contract ?? active.name}.wasm</strong>
                <span>{compileResult ? `${compileResult.size} bytes` : "not built yet"}</span>
              </div>
            </div>
            <dl className="artifact-details">
              <div>
                <dt>Target</dt>
                <dd>wasm32v1-none</dd>
              </div>
              <div>
                <dt>Protocol</dt>
                <dd>25</dd>
              </div>
              <div>
                <dt>Functions</dt>
                <dd>{compileResult?.functions.join(", ") ?? "—"}</dd>
              </div>
              <div>
                <dt>Typed events</dt>
                <dd>{compileResult?.events.join(", ") || "—"}</dd>
              </div>
              <div>
                <dt>SHA-256</dt>
                <dd title={compileResult?.sha256}>
                  {compileResult ? truncate(compileResult.sha256, 10, 8) : "—"}
                </dd>
              </div>
            </dl>
            {compileError && <p className="build-error">{compileError}</p>}
            <button
              className="compile-button"
              onClick={handleCompile}
              disabled={compileState === "loading"}
            >
              {compileState === "loading" ? "Loading compiler…" : "Compile in browser"}
              <span aria-hidden="true">⌘</span>
            </button>
            <button
              className="download-button"
              onClick={downloadWasm}
              disabled={!compileResult}
            >
              Download .wasm
            </button>
            <p className="build-note">
              First build loads the Python runtime. Later builds are instant.
            </p>
          </aside>
        </div>
      </section>

      <section className="section testing-section" id="testing">
        <div className="section-heading">
          <div>
            <span className="section-kicker">02 / Python test SDK</span>
            <h2>Test before testnet.</h2>
          </div>
          <p>
            Exercise the same checked Typed IR in fast Python unit tests. Inspect
            authorization, persistent instance storage, and contract events without
            waiting for a ledger.
          </p>
        </div>
        <div className="testing-workbench">
          <pre><code>{`from pysoroban.testing import ContractTest, Event

contract = ContractTest.from_file("typed_events_contract.py")
result = contract.invoke(
    "record", "alice", 100_000_000_000_000_000,
    auth={"alice"},
)

assert contract.storage["total"] == result
assert contract.last_events == (Event(("updated", "alice"), result),)`}</code></pre>
          <div className="test-result-card">
            <span className="test-status">● all checks passed</span>
            <strong>45 / 45</strong>
            <p>Compiler, Typed IR, CLI, auth, storage, events, and numeric boundaries.</p>
            <small>Deterministic IR simulator · network integration remains on testnet</small>
          </div>
        </div>
      </section>

      <section className="section deployments-section" id="deployments">
        <div className="section-heading light">
          <div>
            <span className="section-kicker">03 / On-chain proof</span>
            <h2>Deployed, not mocked.</h2>
          </div>
          <p>
            All five artifacts were uploaded with Stellar CLI and accepted by
            testnet. Contract IDs and deployment transactions are public.
          </p>
        </div>
        <div className="deployment-grid">
          {(Object.keys(contracts) as ContractKey[]).map((key) => {
            const item = contracts[key];
            return (
              <article className="deployment-card" key={key}>
                <div className="deployment-title">
                  <span className="contract-icon">{item.name[0]}</span>
                  <div>
                    <h3>{item.name}</h3>
                    <span>Python → Wasm</span>
                  </div>
                  <span className="verified-badge">● verified</span>
                </div>
                <dl>
                  <div><dt>Contract ID</dt><dd>{truncate(item.id, 12, 10)}</dd></div>
                  <div><dt>Wasm hash</dt><dd>{item.hash}</dd></div>
                  <div><dt>Network</dt><dd>Stellar testnet</dd></div>
                </dl>
                <a
                  href={`https://stellar.expert/explorer/testnet/contract/${item.id}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  View contract <span aria-hidden="true">↗</span>
                </a>
                <a
                  className="transaction-link"
                  href={`https://stellar.expert/explorer/testnet/tx/${item.transaction}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  Deployment transaction
                </a>
              </article>
            );
          })}
        </div>
      </section>

      <section className="section calls-section" id="live-calls">
        <div className="section-heading">
          <div>
            <span className="section-kicker">04 / Live RPC</span>
            <h2>Call the contracts yourself.</h2>
          </div>
          <p>
            These are real read-only simulations against the deployed testnet
            contracts. No wallet or test XLM required.
          </p>
        </div>
        <div className="call-grid">
          <article className="call-card">
            <div className="call-card-title">
              <div><span>Math</span><h3>add(left, right)</h3></div>
              <span className="method-badge">view</span>
            </div>
            <div className="call-inputs two-columns">
              <label>left<input type="number" value={left} onChange={(e) => setLeft(Number(e.target.value))} /></label>
              <label>right<input type="number" value={right} onChange={(e) => setRight(Number(e.target.value))} /></label>
            </div>
            <div className="call-result">
              <span>Result</span><strong>{mathResult}</strong>
            </div>
            <button onClick={callMath} disabled={callState !== "idle"}>
              {callState === "math" ? "Calling testnet…" : "Run live call"}
              <span aria-hidden="true">→</span>
            </button>
          </article>

          <article className="call-card">
            <div className="call-card-title">
              <div><span>Counter</span><h3>value(user)</h3></div>
              <span className="method-badge">storage</span>
            </div>
            <div className="call-inputs">
              <label>User address<input value={counterUser} onChange={(e) => setCounterUser(e.target.value)} /></label>
            </div>
            <div className="call-result">
              <span>Stored value</span><strong>{counterResult}</strong>
            </div>
            <button onClick={callCounter} disabled={callState !== "idle"}>
              {callState === "counter" ? "Calling testnet…" : "Read live state"}
              <span aria-hidden="true">→</span>
            </button>
          </article>

          <article className="call-card">
            <div className="call-card-title">
              <div><span>TypedEvents</span><h3>label()</h3></div>
              <span className="method-badge">String</span>
            </div>
            <div className="call-description">
              Reads an object-backed Soroban String returned by Python-compiled Wasm.
            </div>
            <div className="call-result">
              <span>Result</span><strong>{typedResult}</strong>
            </div>
            <button onClick={callTyped} disabled={callState !== "idle"}>
              {callState === "typed" ? "Calling testnet…" : "Read typed value"}
              <span aria-hidden="true">→</span>
            </button>
          </article>

          <article className="call-card">
            <div className="call-card-title">
              <div><span>MathProxy</span><h3>add_with(Math, left, right)</h3></div>
              <span className="method-badge">nested call</span>
            </div>
            <div className="call-description">
              Calls the deployed Math contract from inside another Python-compiled contract.
            </div>
            <div className="call-result">
              <span>Nested result</span><strong>{proxyResult}</strong>
            </div>
            <button onClick={callProxy} disabled={callState !== "idle"}>
              {callState === "proxy" ? "Calling both contracts…" : "Run nested call"}
              <span aria-hidden="true">→</span>
            </button>
          </article>

          <article className="call-card">
            <div className="call-card-title">
              <div><span>VectorMath</span><h3>sum(values)</h3></div>
              <span className="method-badge">Vec[i32]</span>
            </div>
            <div className="call-inputs">
              <label>Comma-separated values<input value={vectorInput} onChange={(e) => setVectorInput(e.target.value)} /></label>
            </div>
            <div className="call-result">
              <span>Vector sum</span><strong>{vectorResult}</strong>
            </div>
            <button onClick={callVectors} disabled={callState !== "idle"}>
              {callState === "vectors" ? "Calling testnet…" : "Sum live vector"}
              <span aria-hidden="true">→</span>
            </button>
          </article>
        </div>
        <p className="ledger-note">
          <span className="live-dot" /> Public RPC · Stellar testnet
          {callLedger && <> · latest response at ledger {callLedger.toLocaleString()}</>}
        </p>
      </section>

      <footer>
        <div className="brand footer-brand"><span className="brand-mark">Py</span><span>PySoroban</span></div>
        <p>Python-native smart contracts for Stellar.</p>
        <span>Experimental compiler · Not for production funds</span>
      </footer>
    </main>
  );
}
