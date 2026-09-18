import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = await readFile(new URL("../src/app/api/[...path]/route.ts", import.meta.url), "utf8");
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
});

function loadProxy(upstream) {
  const compiledModule = { exports: {} };
  const requests = [];
  const fetch = async (url) => {
    requests.push(String(url));
    return Response.json({ ok: true });
  };
  // Isolate configuration and network calls without changing global process state.
  const load = new Function("require", "module", "exports", "process", "fetch", outputText);
  load(require, compiledModule, compiledModule.exports, { env: { SOCIUM_API_URL: upstream } }, fetch);
  return { route: compiledModule.exports, requests };
}

for (const upstream of ["http://127.0.0.1:8123", "http://localhost:8456", "http://[::1]:8789"]) {
  test(`API proxy accepts loopback upstream ${upstream}`, async () => {
    const { route, requests } = loadProxy(upstream);
    const result = await route.GET(new Request("http://localhost:3000/api/health"), {
      params: Promise.resolve({ path: ["health"] }),
    });
    assert.equal(result.status, 200);
    assert.deepEqual(requests, [`${upstream}/api/health`]);
  });
}

for (const upstream of [
  "http://api:8000", "http://host.docker.internal:8000", "http://example.com:8000",
  "http://127.0.0.1.example.com:8000", "https://localhost:8000",
  "http://user:password@localhost:8000", "http://localhost:8000/?key=secret",
  "http://localhost:8000/#fragment",
]) {
  test(`API proxy rejects unsupported upstream ${upstream}`, async () => {
    const { route, requests } = loadProxy(upstream);
    const result = await route.GET(new Request("http://localhost:3000/api/health"), {
      params: Promise.resolve({ path: ["health"] }),
    });
    assert.equal(result.status, 503);
    assert.deepEqual(requests, []);
    assert.equal((await result.json()).error, "The local FastAPI service is unavailable. Restart Socium and try again.");
  });
}

test("API proxy still rejects cross-origin callers before forwarding", async () => {
  const { route, requests } = loadProxy("http://127.0.0.1:8000");
  const result = await route.POST(new Request("http://localhost:3000/api/posts", {
    method: "POST", headers: { origin: "https://example.com" },
  }), { params: Promise.resolve({ path: ["posts"] }) });
  assert.equal(result.status, 403);
  assert.deepEqual(requests, []);
});
