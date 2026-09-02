# Socium Connect Broker

This Cloudflare Worker is the small shared OAuth edge required for a Buffer-style `Connect → Allow` experience. It does not host Socium, its database, generated content, schedules, AI prompts, or media.

## Security contract

- OAuth callbacks terminate on HTTPS at Cloudflare.
- The browser may return only to the exact `/oauth/callback` path on `127.0.0.1`, `localhost`, or `[::1]`, with any dynamically selected port.
- Every local connection uses an unpredictable state plus PKCE (`S256`).
- Provider tokens are AES-256-GCM encrypted while waiting for pickup and expire after five minutes.
- A handoff code is stored only as a SHA-256 hash, works once, and the ciphertext is erased after exchange.
- Slack interaction requests require a valid Slack HMAC signature and a timestamp no older than five minutes.
- Slack actions use a hashed installation relay token and a short lease/ack flow. The broker stores only the minimal action envelope.
- Hourly cleanup removes expired OAuth sessions, handoffs, and Slack actions.
- Provider client secrets and the handoff encryption key are Cloudflare secrets, never repository variables.

## One-time maintainer setup

End users do **not** perform these steps. The Socium maintainer deploys one broker and registers one distributed Slack app plus one LinkedIn app.

1. Install dependencies from the repository root:

   ```bash
   pnpm install
   ```

2. Sign in to the Cloudflare account:

   ```bash
   pnpm --filter @socium/connect-broker exec wrangler login
   ```

3. Create the six values listed in `.dev.vars.example`. Generate `HANDOFF_ENCRYPTION_KEY` with:

   ```bash
   node -e "console.log(require('node:crypto').randomBytes(32).toString('base64url'))"
   ```

4. Put all six production values in an ignored file named `.production.secrets.json`. Wrangler uploads this file atomically with the deployment; it is never bundled into Worker source.

5. Deploy and apply the D1 migration:

   ```bash
   pnpm --filter @socium/connect-broker deploy
   ```

   Wrangler 4 automatically provisions the draft `DB` binding on the first deployment and writes the generated resource information back to `wrangler.jsonc`. The deploy command uploads all required secrets with `--secrets-file`, deploys once to provision D1, applies migrations, and deploys the verified version.

6. Confirm the result:

   ```bash
   curl https://YOUR-WORKER.workers.dev/health
   ```

## Slack app

Create one Slack app from `slack-app-manifest.example.yaml`, then copy its Client ID, Client Secret, and Signing Secret into Cloudflare secrets. The checked-in manifest already uses the production Worker hostname. Enable public distribution when Socium is ready for external workspaces.

The broker requests `chat:write`, `im:write`, and `files:write`. It opens a direct conversation with the approving member and uploads the generated approval image, so users do not copy a channel ID or create an app-level Socket Mode token. Configure these exact HTTPS endpoints:

- OAuth redirect: `https://socium-connect.socium-connect-broker.workers.dev/v1/oauth/slack/callback`
- Interactivity: `https://socium-connect.socium-connect-broker.workers.dev/v1/slack/interactions`

## LinkedIn app

Create one LinkedIn developer app, request the **Share on LinkedIn** product, and configure:

- OAuth redirect: `https://socium-connect.socium-connect-broker.workers.dev/v1/oauth/linkedin/callback`
- Scopes: `openid profile w_member_social`

LinkedIn must approve the required product/scopes before public member publishing works. Put the Client ID and Client Secret in Cloudflare secrets; never add them to this repository or paste them into an issue/chat.

## Local development

Copy `.dev.vars.example` to `.dev.vars`, use test provider credentials, then run:

```bash
pnpm --filter @socium/connect-broker migrate:local
pnpm --filter @socium/connect-broker dev
pnpm --filter @socium/connect-broker test
```

`.dev.vars`, `.production.secrets.json`, and Wrangler local state are ignored by Git.

## API contract

- `POST /v1/sessions` — creates a ten-minute Slack or LinkedIn session from a loopback callback, local state, and PKCE challenge.
- `GET /v1/oauth/{provider}/callback` — claims the provider code and redirects a one-time handoff code to localhost.
- `POST /v1/handoffs/exchange` — validates state/PKCE and returns the connector payload once.
- `POST /v1/slack/interactions` — verifies and queues Slack button actions.
- `POST /v1/slack/actions/poll` — leases the next action using the locally encrypted relay token.
- `POST /v1/slack/actions/ack` — acknowledges a processed lease.
- `POST /v1/slack/disconnect` — removes the broker relay mapping and queued actions.
