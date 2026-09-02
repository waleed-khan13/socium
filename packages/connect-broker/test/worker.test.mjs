import assert from "node:assert/strict";
import test from "node:test";

import {
  decryptHandoff,
  encryptHandoff,
  pkceChallenge,
  providerReadiness,
  slackApiRequestInit,
  validateLocalCallback,
  validateSlackRelayCall,
  verifySlackSignature,
} from "../src/worker.mjs";

function base64Url(bytes) {
  return Buffer.from(bytes).toString("base64url");
}

test("accepts only an exact loopback OAuth callback with a dynamic port", () => {
  assert.equal(
    validateLocalCallback("http://127.0.0.1:3147/oauth/callback"),
    "http://127.0.0.1:3147/oauth/callback",
  );
  assert.equal(
    validateLocalCallback("http://localhost:49152/oauth/callback"),
    "http://localhost:49152/oauth/callback",
  );
  assert.throws(
    () => validateLocalCallback("https://example.com/oauth/callback"),
    /only return to Socium/u,
  );
  assert.throws(
    () => validateLocalCallback("http://127.0.0.1:3000/another-path"),
    /only return to Socium/u,
  );
  assert.throws(
    () => validateLocalCallback("http://127.0.0.1:3000/oauth/callback?next=https://example.com"),
    /only return to Socium/u,
  );
});

test("derives an RFC 7636 SHA-256 PKCE challenge", async () => {
  const verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
  assert.equal(await pkceChallenge(verifier), "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
});

test("encrypts handoff payloads with AES-GCM and rejects the wrong key", async () => {
  const key = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const wrongKey = base64Url(crypto.getRandomValues(new Uint8Array(32)));
  const payload = {
    provider: "linkedin",
    connector: { secrets: { access_token: "secret-token" } },
  };
  const encrypted = await encryptHandoff(key, payload);

  assert.equal(JSON.stringify(encrypted).includes("secret-token"), false);
  assert.deepEqual(await decryptHandoff(key, encrypted.ciphertext, encrypted.iv), payload);
  await assert.rejects(
    decryptHandoff(wrongKey, encrypted.ciphertext, encrypted.iv),
    /operation-specific|decrypt|authentication|failed/iu,
  );
});

test("verifies Slack signatures and rejects tampering or stale requests", async () => {
  const secret = "slack-signing-secret";
  const timestamp = "1787673600";
  const rawBody = "payload=%7B%22type%22%3A%22block_actions%22%7D";
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = Buffer.from(
    await crypto.subtle.sign(
      "HMAC",
      key,
      new TextEncoder().encode(`v0:${timestamp}:${rawBody}`),
    ),
  ).toString("hex");
  const signature = `v0=${digest}`;
  const requestTime = Number(timestamp) * 1_000;

  assert.equal(await verifySlackSignature(secret, timestamp, signature, rawBody, requestTime), true);
  assert.equal(await verifySlackSignature(secret, timestamp, signature, `${rawBody}x`, requestTime), false);
  assert.equal(await verifySlackSignature(secret, timestamp, signature, rawBody, requestTime + 301_000), false);
});

test("reports provider readiness independently", () => {
  assert.deepEqual(providerReadiness({
    SLACK_CLIENT_ID: "client-id",
    SLACK_CLIENT_SECRET: "client-secret",
    SLACK_SIGNING_SECRET: "signing-secret",
  }), {
    slack: true,
    linkedin: false,
  });
});

test("limits relayed Slack API calls to the installed approval channel", () => {
  const installation = { team_id: "T123", approval_channel_id: "D123" };
  const valid = validateSlackRelayCall({
    botToken: "xoxb-valid-test-token",
    method: "chat.postEphemeral",
    body: { channel: "D123", user: "U123", text: "Regeneration started." },
  }, installation);
  assert.equal(valid.method, "chat.postEphemeral");
  assert.throws(
    () => validateSlackRelayCall({
      botToken: "xoxb-valid-test-token",
      method: "chat.postMessage",
      body: { channel: "D999", text: "Wrong channel" },
    }, installation),
    /approval channel is invalid/u,
  );

  const prepared = validateSlackRelayCall({
    botToken: "xoxb-valid-test-token",
    method: "files.getUploadURLExternal",
    body: { filename: "campaign.png", length: 1234 },
  }, installation);
  const uploadInit = slackApiRequestInit(prepared.botToken, prepared.method, prepared.body);
  assert.match(uploadInit.headers["content-type"], /application\/x-www-form-urlencoded/u);
  assert.match(uploadInit.body, /filename=campaign\.png/u);
  assert.match(uploadInit.body, /length=1234/u);

  const completed = validateSlackRelayCall({
    botToken: "xoxb-valid-test-token",
    method: "files.completeUploadExternal",
    body: { files: [{ id: "F123IMAGE", title: "campaign.png" }], channel_id: "D123" },
  }, installation);
  const completeInit = slackApiRequestInit(completed.botToken, completed.method, completed.body);
  assert.match(completeInit.body, /files=%5B/u);
  assert.match(completeInit.body, /channel_id=D123/u);
  assert.throws(
    () => validateSlackRelayCall({
      botToken: "xoxb-valid-test-token",
      method: "admin.users.remove",
      body: {},
    }, installation),
    /method is unsupported/u,
  );
});
