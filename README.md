# Socium

Socium is an open-source, localhost-only control plane for AI-assisted social publishing. Version `1.0.5` runs a Next.js console and FastAPI service on the operator's own computer, stores application data in SQLite, and does not require a hosted Socium account or server.

## Version 1.0 scope

The default v1.0 product surface focuses on one complete workflow: connect an AI model, create channel-aware drafts, obtain human approval, and publish or schedule the exact approved revision. Lead intelligence and Local SEO remain in the repository as opt-in previews so they can mature through later updates without weakening the first stable release. Set `SOCIUM_ENABLE_LABS=1` before launch to show those preview workspaces.

See [docs/V1_RELEASE.md](docs/V1_RELEASE.md) for the current stable contract, [docs/V1_1_RELEASE.md](docs/V1_1_RELEASE.md) for the local-first consumer plan, and [docs/RELEASING.md](docs/RELEASING.md) for the maintainer dry-run, tagging, and publication procedure.

## What works today

- Start with private local AI or select a ready-made OpenAI, Google Gemini, Anthropic Claude, OpenRouter, or NVIDIA NIM connection; safe custom OpenAI-compatible and Anthropic-compatible discovery remains available for advanced servers.
- Confirm a durable brand profile with business facts, audience, voice, content rules, colors, logo, and reference media; every confirmed revision becomes reusable generation context.
- Generate a channel-bounded brand content kit containing publish-ready copy, normalized hashtags, an explicit call to action, an image prompt, visual exclusions, and planned alt text; hand the visual brief to Media Studio with one click.
- Persist settings, drafts, revisions, and audit events in a local SQLite WAL database.
- Encrypt AI, Telegram, and multi-secret connector credentials with an automatically generated local master key.
- Import the previous v0.2 JSON store on first launch without deleting the original file.
- Edit, approve, or reject exact draft revisions; edits invalidate prior approval.
- Send Telegram approval requests and receive button decisions through local long polling.
- Publish an approved Telegram draft exactly once and record its remote message ID.
- Schedule approved Telegram revisions with a restart-safe SQLite job queue, pause/resume, catch-up, cancellation, and reviewed retries.
- Save a scoped Slack connector in the local vault and verify its bot identity and Socket Mode app token against Slack's real API.
- Send revision-bound Slack approval buttons and receive approve/reject decisions through an outbound-only Socket Mode listener.
- Save and verify a WordPress connector with encrypted Application Password credentials.
- Publish or schedule an exact approved Blog revision through the official WordPress REST API and retain its remote post link.
- Save and verify a Facebook Page connector with an encrypted Page Access Token and a deliberately pinned Meta Graph API version.
- Publish or schedule an exact approved Facebook revision through the official Page feed endpoint and retain its remote post ID.
- Save and verify an Instagram Business or Creator account using modern Instagram Login permissions and an encrypted access token.
- Publish or schedule an exact approved Instagram caption and public HTTPS image URL through the official two-step media container flow.
- Upload JPEG, PNG, or WebP campaign images into a private local media library with verified decoding, SHA-256 deduplication, previews, metadata, and social-size transforms.
- Connect an encrypted OpenAI-compatible Images API, local Automatic1111/Forge server, or ComfyUI API workflow; queue restart-safe generations with progress/cancel/retry controls and retain provenance locally.
- Save and verify a LinkedIn Member connector with an encrypted 3-legged OAuth token and pinned monthly API version.
- Publish or schedule an exact approved public text revision through LinkedIn's official Posts API and retain its returned post URN.
- Save and verify an access-gated LinkedIn Company Page connector against the consenting member's `ORGANIC_SHARE_CREATE` authorization.
- Publish or schedule an exact approved public text revision as the verified organization through the official Posts API.
- Import allowed CSV, CRM, and LinkedIn exports into a durable local lead vault with source evidence.
- Deduplicate leads by email, domain, phone, or business and location without silently overwriting existing values.
- Search and qualify leads, preserve an audited suppression list, and block suppressed records from reactivation during import.
- Connect the official Google Places API with an encrypted local key and search attributed, no-store results without scraping Google Maps HTML.
- Scan up to four robots-allowed public website pages with SSRF, redirect, content-type, size, timeout, and crawl-delay controls, then explicitly add independently extracted contact evidence to the vault.
- Define an ideal customer profile with target keywords, locations, exclusions, and contact requirements, then rescore the complete local vault without an AI call.
- Inspect point-by-point reason codes, filter leads at the 70+ high-intent threshold, and record auditable human score corrections without erasing the rule-based result.
- Record a lead's legal basis, consent state, purpose/evidence note, and retention review date before AI outreach is enabled.
- Generate editable email drafts with exact revision approval, then export only an approved current revision as CSV; the core never sends outreach.
- Export a lead and its outreach history as local JSON, filter expired retention reviews, and permanently delete lead data only with a reason plus typed confirmation.
- Run a robots-aware, SSRF-protected SEO audit with 18 deterministic technical, on-page, content, and social checks.
- Save derived SEO snapshots and score deltas in SQLite, export a selected report as JSON, and schedule one-off restart-safe audits with the local job worker.
- Run the browser through one same-origin surface at `127.0.0.1:3000`; the API remains internal.

Publishing adapters for X; Instagram carousel/Reels processing; outreach delivery connectors; rendered-page crawling; Lighthouse/PageSpeed and Search Console adapters; keyword maps; and approved SEO fix proposals remain roadmap work. Channel names can already be used to generate social drafts, while verified Telegram, WordPress, Facebook Page, Instagram Professional, LinkedIn Member, and access-approved LinkedIn Company Page connections can publish or schedule exact approved revisions. Outreach is deliberately export-only and never pretends an email was sent.

## One-command localhost install

Requirements:

- Node.js 20.9+

Windows, macOS, and Linux users do not need Docker, Python, uv, pnpm, or a source checkout:

```bash
npx -y socium@latest onboard
```

The `-y` makes the npm download prompt-free. The command downloads the bundle for the current operating system and CPU, verifies its published SHA-256 checksum, keeps the runtime separate from business data, starts both services on loopback, and opens [http://127.0.0.1:3000](http://127.0.0.1:3000). Updates and normal uninstalls preserve the SQLite database, encryption key, media, and exports. See [docs/INSTALLATION.md](docs/INSTALLATION.md) for paths, lifecycle commands, troubleshooting, and permanent removal.

On a fresh database, the browser opens Socium's resumable first-run wizard automatically. It confirms the active data/model locations, guides either private local Ollama or one cloud API connection, verifies the exact saved model, and collects the confirmed brand profile. Setup progress stays in local SQLite, can be dismissed and resumed from **Setup guide**, and does not require a Socium account. Telegram, Slack, and every publisher remain optional.

Choose another drive for durable data and large local-AI models during first install:

```powershell
npx -y socium@latest onboard --data-dir "D:\Socium\data" --models-dir "D:\Socium\models"
```

Stop Socium before moving existing storage. The move is checksum-verified and keeps the source as a recoverable copy:

```powershell
npx socium storage move --data-dir "E:\Socium\data" --models-dir "E:\Socium\models"
```

### Start or run Socium later

```bash
npx socium start
```

`run` is an alias for the same command:

```bash
npx socium run
```

Keep that terminal open while using Socium. The browser opens at [http://127.0.0.1:3000](http://127.0.0.1:3000). Press `Ctrl+C` in the terminal to stop the local API and web app. Add `--no-open` if you do not want Socium to open the browser automatically.

### Update Socium

Stop a running Socium process with `Ctrl+C`, then run:

```bash
npx socium@latest update
```

The update verifies and activates the newest runtime while preserving the local SQLite database, encryption key, settings, media, and exports. If an installation is incomplete or damaged, repair it with:

```bash
npx socium@latest update --force
```

### Check the installation

```bash
npx socium doctor
npx socium version
```

`doctor` checks the installed runtime, local data directory, and default ports. `version` prints the CLI version.

### Remove Socium but keep local data

Stop Socium first, then run:

```bash
npx socium uninstall --yes
```

This removes the downloaded program runtime but deliberately keeps the database, encryption key, settings, media, and exports. Running `npx socium@latest onboard` later reinstalls Socium without intentionally deleting that preserved data.

### Permanently remove Socium and all local data

> **Warning:** This permanently deletes Socium's SQLite database, encryption key, settings, media, exports, downloads, and installed runtimes from the Socium application directory.

```bash
npx socium uninstall --yes --purge-data
```

Back up the complete Socium `data` directory before using `--purge-data`. The SQLite database and its matching `master.key` must be backed up and restored together.

## Run from source

Contributor requirements:

- Node.js 20.9+
- pnpm 10+
- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

```bash
pnpm install
pnpm backend:sync
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000). `pnpm dev` starts both the local FastAPI service on loopback port `8000` and the Next.js console on loopback port `3000`.

The first-run wizard completes the required setup in the dashboard:

1. Review the current durable-data and model locations. If a reliability warning is present, the wizard explains it and requires acknowledgement. Moving existing storage still requires Socium to be stopped; the exact safe command is shown and can be copied in the wizard.
2. Choose **Local AI - Recommended** or **Cloud API**. Local setup inspects this computer, recommends a model, and downloads it with 1% progress when Ollama is running. Cloud setup needs only the selected provider's API key.
3. Enter the business facts and content preferences, choose optional logo/reference assets from the private Media Library, then select **Save & confirm profile**. Confirmation creates an auditable revision.
4. Finish setup, generate a draft, and approve it in the built-in dashboard; no approval connector is required.
5. Optionally connect Telegram or Slack if approvals should also reach another app.
6. Connect only the publishing destination you want to use; the other connectors can stay unconfigured.
7. Publish immediately or schedule the exact approved revision from the local queue.

Every credential field in the UI includes its official **Get key/token** page and short setup instructions. The complete provider-by-provider directory is in [Connector credentials](docs/CREDENTIALS.md).

Socium fills the official endpoint and a working default model for OpenAI, Gemini, Claude, OpenRouter, and NVIDIA. Ollama needs no API key; Socium detects hardware and installed models, shows the separate model-storage path, verifies downloads, and asks Ollama to release heavy inference memory after an idle timeout. Open **Advanced settings** only to change the model or local port.

Only a confirmed brand-profile revision supplies the AI with the expanded audience, offer, goals, voice, content pillars, calls to action, branded hashtags, restricted claims, colors, and visual direction. Editing the legacy basic workspace fields invalidates that confirmation until the complete profile is reviewed and confirmed again. Logo and reference-image bytes stay in the local Media Library; Phase 4 stores their IDs with the profile but does not upload those bytes to a text provider.

For another server, choose **Cloud API → Custom / I'm not sure**, enter its base URL, and select **Detect API & models**. Automatic discovery sends no secret. If the server requires authentication before it can identify itself, Socium asks you to select OpenAI-compatible, Anthropic-compatible, or Ollama first, then sends the key only to that one protocol on the entered origin. Saved keys are encrypted before SQLite storage and remain on this computer. Socium has no hosted login or cloud account requirement.

Slack can also be configured under Integrations. Socium stores its `xoxb-` and `xapp-` tokens encrypted, exposes only presence flags to the browser, and starts the outbound Socket Mode listener after the connection is verified. Approval buttons carry the post ID and exact revision, so edited, repeated, unauthorized-channel, or stale decisions are rejected.

For a personal or business blog, add a WordPress connection under Integrations using the site root URL, username, and a WordPress Application Password. Remote sites must use HTTPS. After **Save & test**, generate a `Blog` draft, approve that exact revision, then publish immediately or schedule it with the same durable local worker. Socium stores the returned WordPress post ID and link in local state and the audit trail.

For Facebook publishing, create a Page Access Token for the target Page with `pages_read_engagement` and `pages_manage_posts`, then add the numeric Page ID, pinned Graph API version, and token under **Integrations → Facebook Page publisher**. The official Meta `/me/accounts` flow can return the Page IDs and Page Access Tokens available to a user token. After **Save & test**, generate a `Facebook` draft and approve it; immediate and scheduled delivery both send only that exact revision. The token remains encrypted in the local vault, and only its presence flag reaches the browser. See the [official Meta Facebook API collection](https://www.postman.com/meta/facebook/documentation/r56bjfd/facebook-api).

For Instagram publishing, use an Instagram Business or Creator account and a token created through Instagram Login with `instagram_business_basic` and `instagram_business_content_publish`. Add the numeric Professional Account ID, pinned Graph API version, and token under **Integrations → Instagram Professional publisher**. A linked Facebook Page is not required for this login path. Each `Instagram` draft also requires a public HTTPS image URL; Meta fetches that image itself, so a localhost file, private IP, or local network URL cannot be used even though Socium itself remains localhost-only. The exact URL, caption, and hashtags are stored with the draft revision, processed as a media container, and published only after that container reports `FINISHED`. See the [official Instagram API documentation](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api), [image-container request](https://www.postman.com/meta/instagram/request/23987686-f4b5a72d-a125-4080-8968-93de1a549e68), and [publish request](https://www.postman.com/meta/instagram/request/23987686-f1c081c0-be35-4ffa-84bb-2c1726860c2b).

The **Media library** accepts decoded JPEG, PNG, and WebP files up to 10 MB and 40 megapixels. It uses random storage names, retains the original locally, generates a bounded WebP preview, deduplicates identical bytes, and can create 1080×1080 square, 1080×1350 portrait, or 1200×628 landscape WebP variants. Alt text and an optional public HTTPS source can be recorded per asset. Local content URLs remain private loopback resources; **Use in draft** is enabled only when the operator explicitly records where that same asset is publicly hosted for Meta to fetch. Deleting an asset names the affected file, requires confirmation, removes both local original and preview, and leaves an audit event.

The same screen includes an **AI image studio** with three independently stored adapters. **Automatic1111 / Forge** uses the local WebUI API (`--api`), accepts optional `username:password` credentials for `--api-auth`, and supports prompt, negative prompt, aspect, steps, guidance, seed, and an optional per-request checkpoint. **OpenAI-compatible Images API** uses `/v1/images/generations`, defaults to `gpt-image-2`, and supports aspect and quality. **ComfyUI** accepts a workflow exported with **Save (API Format)** and injects only explicit `{{prompt}}`, `{{negative_prompt}}`, `{{seed}}`, `{{width}}`, `{{height}}`, `{{steps}}`, `{{guidance_scale}}`, and `{{model}}` placeholders. It submits through `/prompt`, observes `/history` and `/queue`, downloads the first declared image output through `/view`, and retains the provider prompt ID for cancellation and provenance.

All image requests enter the SQLite-backed local worker instead of keeping the browser request open. The queue survives navigation and restart, exposes stage progress and attempt counts, supports operator cancellation and retry, and refreshes the private library when output is ready. Image-provider credentials are encrypted separately from the text provider. Every returned byte stream must pass the same content, size, pixel, and dimension verification as a manual upload before it enters the library. Generation never creates or publishes a post; the library remains the human review boundary. See the [OpenAI Image API guide](https://developers.openai.com/api/docs/guides/image-generation), [Automatic1111 API guide](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API), and [ComfyUI server routes](https://docs.comfy.org/development/comfyui-server/comms_routes).

For LinkedIn Member publishing, enable the **Sign In with LinkedIn using OpenID Connect** and **Share on LinkedIn** products for your own LinkedIn developer app. Generate a member-authorized 3-legged OAuth token with `openid`, `profile`, and `w_member_social`, then enter the `sub` returned by `/v2/userinfo` as the Member ID. Under **Integrations → LinkedIn Member publisher**, save that ID, the token, and a supported `YYYYMM` API version; Socium defaults to `202607` but keeps it editable because LinkedIn versions are released monthly and supported for a limited period. After **Save & test**, an exact approved `LinkedIn` text revision can publish immediately or through the durable scheduler. Socium uses bearer authorization, `X-Restli-Protocol-Version: 2.0.0`, and the pinned `Linkedin-Version` header; it never uses LinkedIn cookies, passwords, profile scraping, or simulated browser clicks. See the [official Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api), [OpenID Connect guide](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2), and [3-legged OAuth flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow).

LinkedIn Company Page publishing is deliberately a separate, access-gated connector. Your LinkedIn developer app must be approved for organization publishing and organization administration scopes. Create a member-authorized token with `openid`, `profile`, `w_organization_social`, and `rw_organization_admin`, then add the consenting member's OIDC `sub`, numeric Organization ID, token, and supported API version under **Integrations → LinkedIn Company Page publisher**. **Save & verify permission** checks the member identity and LinkedIn's permission-based `ORGANIC_SHARE_CREATE` authorization for that exact organization before Socium marks the connector ready. An approved `LinkedIn Company Page` revision then publishes with `urn:li:organization:{id}` as its author. Socium cannot grant LinkedIn products, scopes, or Page roles; a 403 remains an actionable connector error rather than a bypass attempt. See LinkedIn's [organization authorization guide](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-authorizations/getting-started) and [organization authorizations API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/organizations/organization-authorizations/organization-authorizations).

With Labs enabled, open **Lead intelligence** to upload or paste CSV data. Recognized columns include `company`, `website`, `email`, `phone`, `location`, `source_url`, and common aliases. Choose `LinkedIn export` only for a file you exported or are authorized to use; Socium does not scrape LinkedIn pages. Duplicate rows merge into one local record while retaining their source evidence. Suppressing a lead preserves its identity so later imports cannot silently reactivate it.

Before qualification, configure the **Ideal customer profile** in Lead intelligence. Saving it deterministically rescales every local lead from 0–100 and new imports are scored immediately. Open any score to see its reason codes and point changes. A manual correction requires a written reason, remains visibly separate from the underlying ICP score, and can be cleared at any time.

Open a lead's **Reviewed outreach** control to record the legal basis, consent state, supporting purpose, and retention review date. Only a non-suppressed lead with an email and a current, internally consistent review can generate an AI email draft. Editing increments the revision and clears approval. An exact approved revision can be downloaded as CSV, while **Data controls** exports the complete lead package as JSON or permanently deletes the local lead and its drafts after typed confirmation. No outreach send connector is included in v1.0.

With Labs enabled, open **Local SEO lab** and enter a public website URL to create a deterministic baseline. Socium checks the HTTP response, indexing directives, mobile viewport, canonical, encoding, response time, title, description, headings, visible copy, image alt coverage, internal links, structured data, and Open Graph fields. It stores only derived metrics, weighted checks, and recommendations—not the page HTML. A future-dated one-off snapshot can be placed in the same restart-safe SQLite worker used by publishing jobs; the SEO screen keeps those read-only jobs separate from publication jobs.

For live business discovery, create a restricted Google Maps API key with Places API (New) enabled, open **Lead intelligence → Connection**, and select **Save & test**. Search results remain transient browser state with Google Maps attribution and are never copied into SQLite. Select **Crawl public site** to inspect the business's own website under its robots rules, review the extracted fields, and explicitly select **Add to vault**. See the local [terms](docs/TERMS.md) and [privacy notice](docs/PRIVACY.md).

For a production-mode native run:

```bash
pnpm build
pnpm start
```

The native launcher waits for FastAPI migrations and health checks before starting the web console. The default data directory is `./data`; set `SOCIUM_DATA_DIR` to another local directory if needed. Media originals and previews are stored under its `media/` subdirectory.

Back up the complete data directory together. `socium.db` needs its matching `master.key` to decrypt connector secrets. If `socium.json` from v0.2 exists when SQLite is first created, its settings, posts, audit events, and encrypted secrets are imported automatically while the JSON file remains untouched.

## Optional Docker localhost run

```bash
docker compose up --build
```

Compose runs the FastAPI service on a private container network and exposes only `127.0.0.1:3000`. Application data lives in the `socium-data` volume. When connecting Ollama running on the host, use `http://host.docker.internal:11434` in provider settings.

## Telegram approvals without hosting

Telegram notifications and publishing are outbound API calls. Approval buttons use Telegram `getUpdates` long polling from the local worker, so no domain, public HTTPS endpoint, tunnel, webhook, or Socium cloud service is required.

The application must be running to receive a new Telegram decision. Telegram retains pending bot updates temporarily; Socium stores the processed update ID in SQLite to reject replays after restart.

## Slack approvals without hosting

Create a Slack app, enable Socket Mode and interactivity, add the `chat:write` bot scope, and create an app-level token with `connections:write`. Install the app in your workspace, invite it to the approval channel, then save the channel ID, `xoxb-` bot token, and `xapp-` app token under Integrations.

After **Save & test**, Socium opens an outbound WebSocket and shows `Listening`. No public request URL is needed. The application must remain running to receive decisions; connector errors and retries stay visible in the local UI.

## Local-only behavior

- No Socium account, cloud database, billing system, or telemetry endpoint is required.
- Native services bind to `127.0.0.1` by default.
- The operator's computer must be on for scheduled automation and approval listeners to run.
- Local drafts, dashboard approvals, audit history, and Ollama remain available without internet.
- Provider-backed AI, social publishing, lead sources, and analytics naturally need their provider connection.

## Checks

```bash
pnpm typecheck
pnpm lint
pnpm backend:test
pnpm test:e2e:install
pnpm test:e2e
pnpm build
```

The Playwright suite starts a real Next.js console, FastAPI service, and temporary SQLite database on loopback ports. It uses deterministic local stand-ins only for external APIs, then verifies provider setup, draft generation, revision-bound approval, multi-platform publishing, a queued AI image save/test/generate/progress/provenance workflow, a real media upload/metadata/transform/delete lifecycle, automated WCAG A/AA checks, and mobile keyboard navigation. Browser artifacts are written under `output/playwright/`.

Install Chromium once with `pnpm test:e2e:install`. If the Playwright browser download is unavailable but Google Chrome is already installed, run with `SOCIUM_E2E_BROWSER_CHANNEL=chrome` (PowerShell: `$env:SOCIUM_E2E_BROWSER_CHANNEL='chrome'`).

Run every check together with:

```bash
pnpm check
```

## Repository map

- `e2e` — real localhost workflows, automated accessibility checks, and responsive keyboard coverage.
- `scripts/e2e-server.mjs` — isolated browser-test runtime and deterministic external-service stand-ins.
- `src/app` — Next.js dashboard and same-origin FastAPI proxy.
- `src/components` — custom product UI built on shadcn primitives.
- `src/lib` — browser-side domain contracts and utilities.
- `backend/app` — FastAPI routes, local services, connector registry/vault, media and lead vaults, image verification/transforms, ICP scoring, Places discovery, safe website crawler, approval listeners, publishers, durable scheduler, and domain operations.
- `backend/alembic` — automatic SQLite schema migrations.
- `backend/tests` — local API, connector-vault redaction, crawler safety, lead discovery, approval, scheduling, and publishing tests.
- `docs/PRODUCT.md` — product boundaries, features, and core concepts.
- `docs/ARCHITECTURE.md` — localhost runtime and adapter contracts.
- `docs/V1_1_RELEASE.md` — frozen v1.1 scope, delivery order, and release acceptance.
- `docs/V1_1_BASELINE.md` — Phase 0 branch point, toolchain, and baseline verification evidence.
- `docs/ROADMAP.md` — milestones and acceptance criteria.
- `docs/CREDENTIALS.md` — exact official credential portals, connector requirements, and token-safety steps.
- `docs/COMPLIANCE.md` — discovery, publishing, outreach, and retention guardrails.
- `docs/TERMS.md` and `docs/PRIVACY.md` — localhost product/provider terms and data-flow disclosure.
- `design-system/socium/MASTER.md` — persisted visual system.
- `Dockerfile`, `backend/Dockerfile`, and `compose.yaml` — loopback-only container packaging.

## Safety boundary

Socium will not ship credential theft, CAPTCHA bypasses, rate-limit evasion, or unapproved LinkedIn scraping. LinkedIn discovery must use an approved API/provider, user-owned export, CRM sync, or manual import. Google business discovery should use the Places API or another licensed source and honor its attribution and storage rules. Website crawling must respect robots directives and configurable rate limits.

## License

MIT.
