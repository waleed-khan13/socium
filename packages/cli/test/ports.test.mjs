import assert from "node:assert/strict";
import { once } from "node:events";
import { createServer } from "node:net";
import test from "node:test";

import { findAvailablePort, isPortAvailable } from "../src/ports.mjs";

async function occupyLocalPort() {
  const server = createServer();
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return server;
}

test("keeps the preferred port when it is available", async () => {
  const temporary = await occupyLocalPort();
  const preferred = temporary.address().port;
  await new Promise((resolve) => temporary.close(resolve));

  assert.equal(await isPortAvailable(preferred), true);
  assert.equal(await findAvailablePort(preferred), preferred);
});

test("selects another local port when the preferred port is busy", async (context) => {
  const occupied = await occupyLocalPort();
  context.after(() => new Promise((resolve) => occupied.close(resolve)));
  const preferred = occupied.address().port;

  assert.equal(await isPortAvailable(preferred), false);
  const selected = await findAvailablePort(preferred);
  assert.notEqual(selected, preferred);
  assert.equal(await isPortAvailable(selected), true);
});

test("never selects an excluded port", async () => {
  const temporary = await occupyLocalPort();
  const preferred = temporary.address().port;
  await new Promise((resolve) => temporary.close(resolve));

  const selected = await findAvailablePort(preferred, { exclude: [preferred] });
  assert.notEqual(selected, preferred);
});
