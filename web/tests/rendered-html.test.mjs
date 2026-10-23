import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import test from "node:test";

const PUBLISHED_WHEEL_SHA256 =
  "22ad350565ff66bbcf41177ca63f0ebbed02833f0cf0d408ebc61f86eb4e9d68";

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
  assert.match(html, /href="\/favicon\.ico\?v=3"/);
  assert.match(html, /href="\/favicon\.svg\?v=3"/);
  assert.match(html, /href="\/favicon-32x32\.png\?v=3"/);
  assert.match(html, /src="\/logo-mark\.svg"/);
  assert.match(html, /Python contracts\./);
  assert.match(html, /Real Stellar Wasm\./);
  assert.match(html, /pip install --pre pysoroban-compiler/);
  assert.match(html, /https:\/\/pypi\.org\/project\/pysoroban-compiler\//);
  assert.match(html, /Compile in browser/);
  assert.match(html, /Download \.wasm/);
  assert.match(html, /Test before testnet/);
  assert.match(html, /129 \/ 129/);
  assert.match(html, /In-browser compiler 0\.19\.0a2/);
  assert.match(html, />0\.19\.0a2</);
  assert.doesNotMatch(html, /0\.12\.0a1|0\.9\.0a2/);
  assert.match(html, /examples\/hello_world\/contract\.py/);
  assert.match(html, /examples\/increment\/contract\.py/);
  assert.match(html, /examples\/events\/contract\.py/);
  assert.match(html, /examples\/errors\/contract\.py/);
  assert.match(html, /examples\/auth\/contract\.py/);
  assert.match(html, /examples\/cross_contract\/contract_a\/contract\.py/);
  assert.match(html, /Soroban example ports\./);
  assert.match(html, /Scripted testnet deployments\./);
  assert.match(html, /Run nested call/);
  assert.match(html, /Sum live vector/);
  assert.match(html, /Look up live map/);
  assert.match(html, /Swipe to explore/);
  assert.match(html, /Call the scripted deployments\./);
  assert.doesNotMatch(html, /codex-preview|react-loading-skeleton/i);
});

test("ships the published 0.19.0a2 compiler wheel", async () => {
  const bytes = await readFile(
    new URL("../public/compiler/pysoroban_compiler-0.19.0a2-py3-none-any.whl", import.meta.url),
  );
  assert.equal(createHash("sha256").update(bytes).digest("hex"), PUBLISHED_WHEEL_SHA256);
});

test("keeps anchored content below the sticky header", async () => {
  const css = await readFile(new URL("../app/globals.css", import.meta.url), "utf8");
  assert.match(css, /--site-header-height:\s*72px/);
  assert.match(
    css,
    /\.install-card,\s*\.section\[id\]\s*\{\s*scroll-margin-top:\s*calc\(var\(--site-header-height\) \+ 20px\)/,
  );
});
