import assert from "node:assert/strict";
import test from "node:test";

async function render() {
  const workerUrl = new URL("../dist/server/index.js", import.meta.url);
  workerUrl.searchParams.set("test", `${process.pid}-${Date.now()}`);
  const { default: worker } = await import(workerUrl.href);
  return worker.fetch(
    new Request("http://localhost/", { headers: { accept: "text/html" } }),
    { ASSETS: { fetch: async () => new Response("Not found", { status: 404 }) } },
    { waitUntil() {}, passThroughOnException() {} },
  );
}

test("renders the PySoroban live proof", async () => {
  const response = await render();
  assert.equal(response.status, 200);
  const html = await response.text();
  assert.match(html, /<title>PySoroban — Python contracts for Stellar<\/title>/i);
  assert.match(html, /Python contracts\./);
  assert.match(html, /Real Stellar Wasm\./);
  assert.match(html, /Compile in browser/);
  assert.match(html, /Test before testnet/);
  assert.match(html, /45 \/ 45/);
  assert.match(html, /Run nested call/);
  assert.match(html, /Sum live vector/);
  assert.match(html, /Deployed, not mocked\./);
  assert.match(html, /Call the contracts yourself\./);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});
