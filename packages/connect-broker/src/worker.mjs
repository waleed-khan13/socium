const SESSION_TTL_SECONDS = 10 * 60;
const HANDOFF_TTL_SECONDS = 5 * 60;
const ACTION_TTL_SECONDS = 72 * 60 * 60;
// A local model may need time to load before it can regenerate a draft. Keep the
// durable relay lease longer than Socium's bounded interactive generation window.
const ACTION_LEASE_SECONDS = 4 * 60;
const MAX_BODY_BYTES = 24_000;
const LOCAL_CALLBACK_PATH = "/oauth/callback";
const PROVIDERS = new Set(["slack", "linkedin"]);
const SLACK_RELAY_METHODS = new Set([
  "auth.test",
  "chat.postMessage",
  "chat.postEphemeral",
  "files.getUploadURLExternal",
  "files.completeUploadExternal",
]);
const encoder = new TextEncoder();
const decoder = new TextDecoder();

function base64Url(bytes) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/u, "");
}

function fromBase64Url(value) {
  const normalized = value.replaceAll("-", "+").replaceAll("_", "/");
  const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, "=");
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function randomToken(byteLength = 32) {
  return base64Url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

function bytesToHex(bytes) {
  return [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function timingSafeTextEqual(left, right) {
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  if (leftBytes.length !== rightBytes.length) return false;
  let difference = 0;
  for (let index = 0; index < leftBytes.length; index += 1) {
    difference |= leftBytes[index] ^ rightBytes[index];
  }
  return difference === 0;
}

async function sha256(value) {
  return base64Url(new Uint8Array(await crypto.subtle.digest("SHA-256", encoder.encode(value))));
}

export async function pkceChallenge(verifier) {
  return sha256(verifier);
}

export function validateLocalCallback(value) {
  let callback;
  try {
    callback = new URL(value);
  } catch {
    throw new Error("Local callback URL is invalid.");
  }
  if (
    callback.protocol !== "http:"
    || !["127.0.0.1", "localhost", "[::1]"].includes(callback.hostname.toLowerCase())
    || !callback.port
    || callback.pathname !== LOCAL_CALLBACK_PATH
    || callback.username
    || callback.password
    || callback.search
    || callback.hash
  ) {
    throw new Error("OAuth can only return to Socium's exact localhost callback.");
  }
  return callback.toString();
}

function validateOpaqueLocalValue(value, label) {
  if (typeof value !== "string" || !/^[A-Za-z0-9_-]{32,160}$/u.test(value)) {
    throw new Error(`${label} is invalid.`);
  }
  return value;
}

function validateProvider(value) {
  if (!PROVIDERS.has(value)) throw new Error("Unsupported OAuth provider.");
  return value;
}

async function readJson(request) {
  const declaredLength = Number(request.headers.get("content-length") || "0");
  if (declaredLength > MAX_BODY_BYTES) throw new Error("Request body is too large.");
  const text = await request.text();
  if (encoder.encode(text).length > MAX_BODY_BYTES) throw new Error("Request body is too large.");
  if (!text) return {};
  const payload = JSON.parse(text);
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("JSON object required.");
  }
  return payload;
}

function securityHeaders(extra = {}) {
  return {
    "cache-control": "no-store",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
    "referrer-policy": "no-referrer",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    ...extra,
  };
}

function jsonResponse(payload, status = 200) {
  return Response.json(payload, {
    status,
    headers: securityHeaders({ "content-type": "application/json; charset=utf-8" }),
  });
}

function redirectResponse(location) {
  return new Response(null, { status: 302, headers: securityHeaders({ location }) });
}

function htmlResponse(title, message, status = 400) {
  const escape = (value) => String(value).replace(/[&<>"']/gu, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  })[character]);
  return new Response(
    `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escape(title)}</title><style>body{background:#050505;color:#eee;font:16px/1.55 system-ui;margin:0;display:grid;min-height:100vh;place-items:center}.card{border:1px solid #292929;border-radius:14px;max-width:620px;padding:28px;background:#090909}h1{font-size:22px;margin:0 0 10px}p{color:#aaa;margin:0}</style><main class="card"><h1>${escape(title)}</h1><p>${escape(message)}</p></main>`,
    { status, headers: securityHeaders({ "content-type": "text/html; charset=utf-8" }) },
  );
}

function oauthRedirectUri(request, provider) {
  return new URL(`/v1/oauth/${provider}/callback`, request.url).toString();
}

function authorizationUrl(provider, env, redirectUri, state) {
  if (provider === "slack") {
    const url = new URL("https://slack.com/oauth/v2/authorize");
    url.searchParams.set("client_id", env.SLACK_CLIENT_ID);
    url.searchParams.set("scope", "chat:write,im:write,files:write");
    url.searchParams.set("redirect_uri", redirectUri);
    url.searchParams.set("state", state);
    return url.toString();
  }
  const url = new URL("https://www.linkedin.com/oauth/v2/authorization");
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", env.LINKEDIN_CLIENT_ID);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("state", state);
  url.searchParams.set("scope", "openid profile w_member_social");
  return url.toString();
}

const PROVIDER_SECRETS = {
  slack: ["SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET", "SLACK_SIGNING_SECRET"],
  linkedin: ["LINKEDIN_CLIENT_ID", "LINKEDIN_CLIENT_SECRET"],
};

function secretIsConfigured(env, name) {
  return typeof env[name] === "string" && Boolean(env[name].trim());
}

function requireCoreEnvironment(env) {
  for (const name of ["HANDOFF_ENCRYPTION_KEY"]) {
    if (typeof env[name] !== "string" || !env[name].trim()) {
      throw new Error(`Missing required Worker secret: ${name}.`);
    }
  }
  if (!env.DB) throw new Error("Missing required D1 binding: DB.");
}

function requireProviderEnvironment(provider, env) {
  for (const name of PROVIDER_SECRETS[provider]) {
    if (!secretIsConfigured(env, name)) {
      throw new Error(`Missing required ${provider} Worker secret: ${name}.`);
    }
  }
}

export function providerReadiness(env) {
  return Object.fromEntries(
    Object.entries(PROVIDER_SECRETS).map(([provider, names]) => [
      provider,
      names.every((name) => secretIsConfigured(env, name)),
    ]),
  );
}

async function encryptionKey(secret) {
  const raw = fromBase64Url(secret.trim());
  if (raw.length !== 32) throw new Error("HANDOFF_ENCRYPTION_KEY must decode to 32 bytes.");
  return crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]);
}

export async function encryptHandoff(secret, payload) {
  const key = await encryptionKey(secret);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv },
    key,
    encoder.encode(JSON.stringify(payload)),
  );
  return { ciphertext: base64Url(new Uint8Array(ciphertext)), iv: base64Url(iv) };
}

export async function decryptHandoff(secret, ciphertext, iv) {
  const key = await encryptionKey(secret);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: fromBase64Url(iv) },
    key,
    fromBase64Url(ciphertext),
  );
  return JSON.parse(decoder.decode(plaintext));
}

async function providerJson(response, label) {
  let payload;
  try {
    payload = await response.json();
  } catch {
    throw new Error(`${label} returned an unreadable response.`);
  }
  if (!response.ok || !payload || typeof payload !== "object") {
    throw new Error(`${label} returned HTTP ${response.status}.`);
  }
  return payload;
}

async function slackApi(token, method, body) {
  const response = await fetch(`https://slack.com/api/${method}`, {
    method: "POST",
    headers: {
      accept: "application/json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json; charset=utf-8",
    },
    body: JSON.stringify(body || {}),
  });
  const payload = await providerJson(response, `Slack ${method}`);
  if (!payload.ok) throw new Error(`Slack ${method} failed: ${String(payload.error || "unknown_error")}.`);
  return payload;
}

async function exchangeSlack(env, code, redirectUri) {
  const credentials = btoa(`${env.SLACK_CLIENT_ID}:${env.SLACK_CLIENT_SECRET}`);
  const body = new URLSearchParams({ code, redirect_uri: redirectUri });
  const response = await fetch("https://slack.com/api/oauth.v2.access", {
    method: "POST",
    headers: {
      accept: "application/json",
      authorization: `Basic ${credentials}`,
      "content-type": "application/x-www-form-urlencoded",
    },
    body,
  });
  const payload = await providerJson(response, "Slack OAuth");
  if (!payload.ok) throw new Error(`Slack OAuth failed: ${String(payload.error || "unknown_error")}.`);
  const botToken = String(payload.access_token || "");
  const userId = String(payload.authed_user?.id || "");
  const teamId = String(payload.team?.id || "");
  if (!botToken.startsWith("xoxb-") || !userId || !teamId) {
    throw new Error("Slack OAuth response is missing the bot, user, or workspace identity.");
  }
  const conversation = await slackApi(botToken, "conversations.open", { users: userId });
  const channelId = String(conversation.channel?.id || "");
  if (!channelId) throw new Error("Slack did not return an approval conversation.");
  const relayToken = randomToken();
  const now = Math.floor(Date.now() / 1_000);
  await env.DB.prepare(
    `INSERT INTO slack_installations (team_id, relay_hash, approval_channel_id, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?)
     ON CONFLICT(team_id) DO UPDATE SET relay_hash=excluded.relay_hash,
       approval_channel_id=excluded.approval_channel_id, updated_at=excluded.updated_at`,
  ).bind(teamId, await sha256(relayToken), channelId, now, now).run();
  const teamName = String(payload.team?.name || teamId);
  return {
    version: 1,
    provider: "slack",
    connector: {
      adapterId: "slack",
      name: `Slack · ${teamName}`,
      config: { approval_channel_id: channelId, transport: "broker-relay" },
      secrets: { bot_token: botToken, relay_token: relayToken },
      scopes: ["chat:write", "im:write", "files:write"],
      enabled: true,
    },
    remote: { teamId, teamName, userId, botUserId: String(payload.bot_user_id || "") },
  };
}

async function exchangeLinkedIn(env, code, redirectUri) {
  const body = new URLSearchParams({
    grant_type: "authorization_code",
    code,
    client_id: env.LINKEDIN_CLIENT_ID,
    client_secret: env.LINKEDIN_CLIENT_SECRET,
    redirect_uri: redirectUri,
  });
  const tokenResponse = await fetch("https://www.linkedin.com/oauth/v2/accessToken", {
    method: "POST",
    headers: { accept: "application/json", "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  const token = await providerJson(tokenResponse, "LinkedIn OAuth");
  const accessToken = String(token.access_token || "");
  if (!accessToken) throw new Error("LinkedIn OAuth response did not include an access token.");
  const profileResponse = await fetch("https://api.linkedin.com/v2/userinfo", {
    headers: { accept: "application/json", authorization: `Bearer ${accessToken}` },
  });
  const profile = await providerJson(profileResponse, "LinkedIn profile");
  const personId = String(profile.sub || "");
  if (!personId) throw new Error("LinkedIn profile did not include a member ID.");
  const name = String(profile.name || profile.given_name || "LinkedIn member");
  return {
    version: 1,
    provider: "linkedin",
    connector: {
      adapterId: "linkedin",
      name: `LinkedIn · ${name}`,
      config: { person_id: personId, api_version: "202607" },
      secrets: { access_token: accessToken },
      scopes: ["openid", "profile", "w_member_social"],
      enabled: true,
    },
    remote: { personId, name, expiresIn: Number(token.expires_in || 0) },
  };
}

async function createHandoff(env, session, payload) {
  const handoffCode = randomToken();
  const encrypted = await encryptHandoff(env.HANDOFF_ENCRYPTION_KEY, payload);
  const now = Math.floor(Date.now() / 1_000);
  await env.DB.prepare(
    `INSERT INTO oauth_handoffs
      (code_hash, provider, local_state, code_challenge, ciphertext, iv, created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    await sha256(handoffCode),
    session.provider,
    session.local_state,
    session.code_challenge,
    encrypted.ciphertext,
    encrypted.iv,
    now,
    now + HANDOFF_TTL_SECONDS,
  ).run();
  return handoffCode;
}

async function startSession(request, env) {
  const payload = await readJson(request);
  const provider = validateProvider(payload.provider);
  requireProviderEnvironment(provider, env);
  const localCallback = validateLocalCallback(payload.localCallback);
  const localState = validateOpaqueLocalValue(payload.localState, "Local OAuth state");
  const codeChallenge = validateOpaqueLocalValue(payload.codeChallenge, "PKCE challenge");
  const sessionId = randomToken();
  const redirectUri = oauthRedirectUri(request, provider);
  const now = Math.floor(Date.now() / 1_000);
  await env.DB.prepare(
    `INSERT INTO oauth_sessions
      (id, provider, local_callback, local_state, code_challenge, redirect_uri, created_at, expires_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    sessionId,
    provider,
    localCallback,
    localState,
    codeChallenge,
    redirectUri,
    now,
    now + SESSION_TTL_SECONDS,
  ).run();
  return jsonResponse({
    ok: true,
    provider,
    authorizationUrl: authorizationUrl(provider, env, redirectUri, sessionId),
    expiresIn: SESSION_TTL_SECONDS,
  }, 201);
}

function localRedirect(session, values) {
  const callback = new URL(session.local_callback);
  for (const [key, value] of Object.entries(values)) callback.searchParams.set(key, String(value));
  callback.searchParams.set("provider", session.provider);
  callback.searchParams.set("state", session.local_state);
  return redirectResponse(callback.toString());
}

async function oauthCallback(request, env, provider) {
  requireProviderEnvironment(provider, env);
  const url = new URL(request.url);
  const state = url.searchParams.get("state") || "";
  const now = Math.floor(Date.now() / 1_000);
  const session = await env.DB.prepare(
    `SELECT id, provider, local_callback, local_state, code_challenge, redirect_uri,
            expires_at, used_at
       FROM oauth_sessions WHERE id = ?`,
  ).bind(state).first();
  if (!session || session.provider !== provider || session.used_at || Number(session.expires_at) <= now) {
    return htmlResponse("Connection expired", "Return to Socium and start the connection again.", 400);
  }
  const claimed = await env.DB.prepare(
    "UPDATE oauth_sessions SET used_at = ? WHERE id = ? AND used_at IS NULL AND expires_at > ?",
  ).bind(now, state, now).run();
  if (!claimed.meta?.changes) {
    return htmlResponse("Connection already used", "Return to Socium and start a new connection.", 409);
  }
  const providerError = url.searchParams.get("error");
  if (providerError) return localRedirect(session, { error: providerError });
  const code = url.searchParams.get("code") || "";
  if (!code || code.length > 4_000) return localRedirect(session, { error: "missing_authorization_code" });
  try {
    const payload = provider === "slack"
      ? await exchangeSlack(env, code, session.redirect_uri)
      : await exchangeLinkedIn(env, code, session.redirect_uri);
    const handoffCode = await createHandoff(env, session, payload);
    return localRedirect(session, { code: handoffCode });
  } catch (error) {
    console.error("OAuth callback failed", { provider, error: error instanceof Error ? error.message : String(error) });
    return localRedirect(session, { error: "provider_exchange_failed" });
  }
}

async function exchangeHandoff(request, env) {
  const payload = await readJson(request);
  const provider = validateProvider(payload.provider);
  requireProviderEnvironment(provider, env);
  const localState = validateOpaqueLocalValue(payload.localState, "Local OAuth state");
  const verifier = validateOpaqueLocalValue(payload.codeVerifier, "PKCE verifier");
  const handoffCode = validateOpaqueLocalValue(payload.handoffCode, "Handoff code");
  const codeHash = await sha256(handoffCode);
  const now = Math.floor(Date.now() / 1_000);
  const handoff = await env.DB.prepare(
    `SELECT code_hash, provider, local_state, code_challenge, ciphertext, iv, expires_at, consumed_at
       FROM oauth_handoffs WHERE code_hash = ?`,
  ).bind(codeHash).first();
  if (
    !handoff
    || handoff.provider !== provider
    || handoff.local_state !== localState
    || handoff.consumed_at
    || Number(handoff.expires_at) <= now
    || !timingSafeTextEqual(await pkceChallenge(verifier), String(handoff.code_challenge))
  ) {
    return jsonResponse({ ok: false, error: "Handoff is invalid, expired, or already used." }, 400);
  }
  const claimed = await env.DB.prepare(
    "UPDATE oauth_handoffs SET consumed_at = ? WHERE code_hash = ? AND consumed_at IS NULL AND expires_at > ?",
  ).bind(now, codeHash, now).run();
  if (!claimed.meta?.changes) {
    return jsonResponse({ ok: false, error: "Handoff was already used." }, 409);
  }
  const connector = await decryptHandoff(
    env.HANDOFF_ENCRYPTION_KEY,
    String(handoff.ciphertext),
    String(handoff.iv),
  );
  await env.DB.prepare(
    "UPDATE oauth_handoffs SET ciphertext = '', iv = '' WHERE code_hash = ?",
  ).bind(codeHash).run();
  return jsonResponse({ ok: true, ...connector });
}

export async function verifySlackSignature(signingSecret, timestamp, signature, rawBody, now = Date.now()) {
  if (!/^\d{10,13}$/u.test(timestamp || "") || !/^v0=[a-f0-9]{64}$/u.test(signature || "")) return false;
  const timestampSeconds = Number(timestamp);
  if (!Number.isFinite(timestampSeconds) || Math.abs(Math.floor(now / 1_000) - timestampSeconds) > 300) {
    return false;
  }
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(signingSecret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = new Uint8Array(
    await crypto.subtle.sign("HMAC", key, encoder.encode(`v0:${timestamp}:${rawBody}`)),
  );
  return timingSafeTextEqual(`v0=${bytesToHex(digest)}`, signature);
}

async function slackInteraction(request, env) {
  const rawBody = await request.text();
  if (encoder.encode(rawBody).length > MAX_BODY_BYTES) return new Response("", { status: 413 });
  const timestamp = request.headers.get("x-slack-request-timestamp") || "";
  const signature = request.headers.get("x-slack-signature") || "";
  if (!await verifySlackSignature(env.SLACK_SIGNING_SECRET, timestamp, signature, rawBody)) {
    return new Response("", { status: 401 });
  }
  let payload;
  try {
    payload = JSON.parse(new URLSearchParams(rawBody).get("payload") || "null");
  } catch {
    return new Response("", { status: 400 });
  }
  if (payload?.type !== "block_actions" || !Array.isArray(payload.actions)) {
    return new Response("", { status: 200 });
  }
  const teamId = String(payload.team?.id || "");
  const channelId = String(payload.channel?.id || "");
  const userId = String(payload.user?.id || "");
  const action = payload.actions.find((item) => [
    "socium_approve",
    "socium_regenerate",
    "socium_regenerate_post",
    "socium_regenerate_image",
    "socium_edit",
    "socium_skip",
  ].includes(item?.action_id));
  if (!teamId || !channelId || !userId || !action) return new Response("", { status: 200 });
  const installation = await env.DB.prepare(
    "SELECT team_id, approval_channel_id FROM slack_installations WHERE team_id = ?",
  ).bind(teamId).first();
  if (!installation || installation.approval_channel_id !== channelId) return new Response("", { status: 200 });
  const event = {
    type: "block_actions",
    team: { id: teamId },
    channel: { id: channelId },
    user: { id: userId },
    actions: [{ action_id: String(action.action_id), value: String(action.value || "") }],
  };
  const dedupeSource = `${teamId}:${String(payload.trigger_id || payload.action_ts || "")}:${String(action.value || "")}`;
  await env.DB.prepare(
    "INSERT OR IGNORE INTO slack_actions (id, team_id, payload, created_at) VALUES (?, ?, ?, ?)",
  ).bind(await sha256(dedupeSource), teamId, JSON.stringify(event), Math.floor(Date.now() / 1_000)).run();
  return new Response("", { status: 200 });
}

async function installationForRelay(env, relayToken) {
  const token = validateOpaqueLocalValue(relayToken, "Slack relay token");
  return env.DB.prepare(
    "SELECT team_id, approval_channel_id FROM slack_installations WHERE relay_hash = ?",
  ).bind(await sha256(token)).first();
}

export function validateSlackRelayCall(payload, installation) {
  const botToken = String(payload.botToken || "");
  if (!botToken.startsWith("xoxb-") || botToken.length > 1_000) {
    throw new Error("Slack bot token is invalid.");
  }
  const method = String(payload.method || "");
  if (!SLACK_RELAY_METHODS.has(method)) throw new Error("Slack API method is unsupported.");
  const body = payload.body && typeof payload.body === "object" && !Array.isArray(payload.body)
    ? payload.body
    : {};
  if (method === "chat.postMessage" || method === "chat.postEphemeral") {
    if (String(body.channel || "") !== String(installation.approval_channel_id || "")) {
      throw new Error("Slack approval channel is invalid.");
    }
  }
  if (method === "chat.postEphemeral") {
    if (!/^U[A-Z0-9]{2,}$/u.test(String(body.user || ""))) {
      throw new Error("Slack approval user is invalid.");
    }
    if (String(body.text || "").length > 2_000) {
      throw new Error("Slack feedback is too long.");
    }
  }
  if (method === "files.getUploadURLExternal") {
    if (!String(body.filename || "").trim() || String(body.filename).length > 255) {
      throw new Error("Slack upload filename is invalid.");
    }
    if (!Number.isSafeInteger(Number(body.length)) || Number(body.length) <= 0) {
      throw new Error("Slack upload length is invalid.");
    }
  }
  if (method === "files.completeUploadExternal") {
    const files = Array.isArray(body.files) ? body.files : [];
    const file = files.length === 1 && files[0] && typeof files[0] === "object" ? files[0] : null;
    if (!file || !/^F[A-Z0-9]{2,}$/u.test(String(file.id || ""))) {
      throw new Error("Slack uploaded file is invalid.");
    }
    if (String(body.channel_id || "") !== String(installation.approval_channel_id || "")) {
      throw new Error("Slack approval channel is invalid.");
    }
  }
  return { botToken, method, body };
}

export function slackApiRequestInit(botToken, method, body) {
  const headers = {
    accept: "application/json",
    authorization: `Bearer ${botToken}`,
  };
  if (method === "files.getUploadURLExternal" || method === "files.completeUploadExternal") {
    const form = new URLSearchParams();
    for (const [key, value] of Object.entries(body)) {
      form.set(key, typeof value === "object" ? JSON.stringify(value) : String(value));
    }
    return {
      method: "POST",
      headers: { ...headers, "content-type": "application/x-www-form-urlencoded; charset=utf-8" },
      body: form.toString(),
    };
  }
  return {
    method: "POST",
    headers: { ...headers, "content-type": "application/json; charset=utf-8" },
    body: JSON.stringify(body),
  };
}

async function forwardSlackApi(request, env) {
  const payload = await readJson(request);
  const installation = await installationForRelay(env, payload.relayToken);
  if (!installation) return jsonResponse({ ok: false, error: "Slack relay is not authorized." }, 401);
  const { botToken, method, body } = validateSlackRelayCall(payload, installation);
  let response;
  try {
    response = await fetch(`https://slack.com/api/${method}`, {
      ...slackApiRequestInit(botToken, method, body),
    });
  } catch {
    return jsonResponse({ ok: false, error: "Slack is temporarily unavailable." }, 503);
  }
  let result;
  try {
    result = await response.json();
  } catch {
    return jsonResponse({ ok: false, error: "Slack returned an unreadable response." }, 502);
  }
  if (!response.ok || !result || typeof result !== "object" || !result.ok) {
    const reason = String(result?.error || `HTTP ${response.status}`).slice(0, 160);
    return jsonResponse({ ok: false, error: `Slack ${method} failed: ${reason}.` }, 502);
  }
  if (method === "auth.test" && String(result.team_id || "") !== String(installation.team_id)) {
    return jsonResponse({ ok: false, error: "Slack token does not belong to this installation." }, 403);
  }
  return jsonResponse({ ok: true, result });
}

async function pollSlackAction(request, env) {
  const payload = await readJson(request);
  const installation = await installationForRelay(env, payload.relayToken);
  if (!installation) return jsonResponse({ ok: false, error: "Slack relay is not authorized." }, 401);
  const now = Math.floor(Date.now() / 1_000);
  const action = await env.DB.prepare(
    `SELECT id, payload FROM slack_actions
      WHERE team_id = ? AND consumed_at IS NULL AND (lease_until IS NULL OR lease_until <= ?)
      ORDER BY created_at ASC LIMIT 1`,
  ).bind(installation.team_id, now).first();
  if (!action) return jsonResponse({ ok: true, action: null });
  const leaseToken = randomToken();
  const claimed = await env.DB.prepare(
    `UPDATE slack_actions SET lease_hash = ?, lease_until = ?
      WHERE id = ? AND consumed_at IS NULL AND (lease_until IS NULL OR lease_until <= ?)`,
  ).bind(await sha256(leaseToken), now + ACTION_LEASE_SECONDS, action.id, now).run();
  if (!claimed.meta?.changes) return jsonResponse({ ok: true, action: null });
  return jsonResponse({
    ok: true,
    action: { id: action.id, leaseToken, payload: JSON.parse(String(action.payload)) },
  });
}

async function acknowledgeSlackAction(request, env) {
  const payload = await readJson(request);
  const installation = await installationForRelay(env, payload.relayToken);
  if (!installation) return jsonResponse({ ok: false, error: "Slack relay is not authorized." }, 401);
  const actionId = validateOpaqueLocalValue(payload.actionId, "Slack action ID");
  const leaseToken = validateOpaqueLocalValue(payload.leaseToken, "Slack lease token");
  const result = await env.DB.prepare(
    `UPDATE slack_actions SET consumed_at = ?, lease_hash = NULL, lease_until = NULL
      WHERE id = ? AND team_id = ? AND lease_hash = ? AND consumed_at IS NULL`,
  ).bind(
    Math.floor(Date.now() / 1_000),
    actionId,
    installation.team_id,
    await sha256(leaseToken),
  ).run();
  return result.meta?.changes
    ? jsonResponse({ ok: true })
    : jsonResponse({ ok: false, error: "Slack action lease is invalid or expired." }, 409);
}

async function disconnectSlack(request, env) {
  const payload = await readJson(request);
  const installation = await installationForRelay(env, payload.relayToken);
  if (!installation) return jsonResponse({ ok: true });
  await env.DB.batch([
    env.DB.prepare("DELETE FROM slack_actions WHERE team_id = ?").bind(installation.team_id),
    env.DB.prepare("DELETE FROM slack_installations WHERE team_id = ?").bind(installation.team_id),
  ]);
  return jsonResponse({ ok: true });
}

async function cleanup(env) {
  const now = Math.floor(Date.now() / 1_000);
  await env.DB.batch([
    env.DB.prepare("DELETE FROM oauth_sessions WHERE expires_at <= ?").bind(now),
    env.DB.prepare("DELETE FROM oauth_handoffs WHERE expires_at <= ? OR consumed_at IS NOT NULL").bind(now),
    env.DB.prepare("DELETE FROM slack_actions WHERE created_at <= ? OR consumed_at IS NOT NULL").bind(now - ACTION_TTL_SECONDS),
  ]);
}

async function route(request, env) {
  requireCoreEnvironment(env);
  const url = new URL(request.url);
  if (request.method === "GET" && url.pathname === "/health") {
    return jsonResponse({
      ok: true,
      service: "socium-connect",
      version: 1,
      providers: providerReadiness(env),
    });
  }
  if (request.method === "POST" && url.pathname === "/v1/sessions") return startSession(request, env);
  if (request.method === "POST" && url.pathname === "/v1/handoffs/exchange") return exchangeHandoff(request, env);
  if (request.method === "GET" && url.pathname === "/v1/oauth/slack/callback") {
    return oauthCallback(request, env, "slack");
  }
  if (request.method === "GET" && url.pathname === "/v1/oauth/linkedin/callback") {
    return oauthCallback(request, env, "linkedin");
  }
  if (request.method === "POST" && url.pathname === "/v1/slack/interactions") {
    requireProviderEnvironment("slack", env);
    return slackInteraction(request, env);
  }
  if (request.method === "POST" && url.pathname === "/v1/slack/actions/poll") {
    requireProviderEnvironment("slack", env);
    return pollSlackAction(request, env);
  }
  if (request.method === "POST" && url.pathname === "/v1/slack/actions/ack") {
    requireProviderEnvironment("slack", env);
    return acknowledgeSlackAction(request, env);
  }
  if (request.method === "POST" && url.pathname === "/v1/slack/api") {
    requireProviderEnvironment("slack", env);
    return forwardSlackApi(request, env);
  }
  if (request.method === "POST" && url.pathname === "/v1/slack/disconnect") {
    requireProviderEnvironment("slack", env);
    return disconnectSlack(request, env);
  }
  return jsonResponse({ ok: false, error: "Not found." }, 404);
}

const worker = {
  async fetch(request, env) {
    const requestId = crypto.randomUUID();
    try {
      return await route(request, env);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unexpected broker error.";
      console.error("Broker request failed", { requestId, path: new URL(request.url).pathname, message });
      const clientError = /invalid|unsupported|required|too large|only return/iu.test(message);
      return jsonResponse(
        { ok: false, error: clientError ? message : "Connection broker failed.", requestId },
        clientError ? 400 : 500,
      );
    }
  },
  async scheduled(_controller, env, context) {
    context.waitUntil(cleanup(env));
  },
};

export default worker;
