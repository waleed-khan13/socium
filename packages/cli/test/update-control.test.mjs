import assert from "node:assert/strict";
import test from "node:test";
import { createControlServer } from "../src/runtime.mjs";

test("controller prepares the update helper and rejects duplicate restart actions", async (t) => {
  const calls = [];
  let finish;
  const finished = new Promise((resolve) => { finish = resolve; });
  const server = await createControlServer({
    token: "test-only", state: () => ({}),
    onAction(action, _payload, phase) {
      calls.push({ action, phase });
      if (phase.prepared) finish();
    },
  });
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const url = `http://127.0.0.1:${server.address().port}`;
  const options = { method: "POST", headers: { authorization: "Bearer test-only" } };
  assert.equal((await fetch(`${url}/update`, options)).status, 200);
  assert.equal((await fetch(`${url}/update`, options)).status, 409);
  await finished;
  assert.deepEqual(calls, [
    { action: "update", phase: { prepareOnly: true } },
    { action: "update", phase: { prepared: true } },
  ]);
});

test("controller returns helper launch failure before claiming update success", async (t) => {
  const server = await createControlServer({
    token: "test-only", state: () => ({}),
    onAction() { throw new Error("Helper could not start"); },
  });
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const url = `http://127.0.0.1:${server.address().port}/update`;
  const options = { method: "POST", headers: { authorization: "Bearer test-only" } };
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await fetch(url, options);
    assert.equal(response.status, 400);
    assert.equal((await response.json()).ok, false);
  }
});
