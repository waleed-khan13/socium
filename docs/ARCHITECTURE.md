# Architecture

## Product boundary

Socium is a single-operator, localhost-only application. The project does not operate a cloud control plane, hosted database, multi-tenant API, or SaaS account system. Internet access is used only when the operator explicitly connects an AI, approval, lead, analytics, or publishing provider.

All application services bind to loopback in a native install. Docker Compose exposes only the web console on `127.0.0.1:3000`; the API remains on the private Compose network.

## Stack

| Layer | Choice | Why |
| --- | --- | --- |
| Web console | Next.js + React + TypeScript | Mature local web UI, reusable contracts, and the existing custom shadcn interface. |
| Local API | FastAPI + Pydantic | Strong Python AI/crawling ecosystem, typed validation, and generated OpenAPI. |
| Data | SQLite in WAL mode | Serverless single-file storage with transactions, indexes, backup portability, and low install overhead. |
| ORM/migrations | SQLAlchemy + Alembic | Explicit relational models and automatic local upgrade migrations. |
| Durable work | SQLite-backed job table + local worker | Restart-safe schedules and retries without requiring Redis or another service. |
| Browser audit | Lightweight HTTP crawler + Playwright fallback | Fast static crawling while retaining rendered-page checks when required. |
| Local AI | Ollama/LM Studio/LocalAI adapters | Private user-controlled inference. |
| Cloud AI | OpenAI, Gemini, Anthropic, OpenRouter, NVIDIA, and generic compatible adapters | Ready-made official endpoints with user-owned credentials plus an explicit advanced custom option. |
| Image AI | OpenAI-compatible Images API + Automatic1111/Forge + ComfyUI | User-selected hosted or fully local workflow generation with one durable review boundary. |
| Packaging | Native launcher plus optional Docker Compose | A normal localhost install first, with a reproducible container option. |

## Process layout

```text
Browser → 127.0.0.1:3000 (Next.js)
                    ↓ same-origin /api proxy
          127.0.0.1:8000 (FastAPI)
                    ↓
          data/socium.db (SQLite WAL)
                    ↓
          local scheduler / worker
                    ↓ outbound connections only
          AI, Telegram, Slack, social and data APIs
```

The browser never calls the internal API port directly. This avoids cross-origin configuration and keeps a single public localhost surface. Native startup launches the API before the web console. Compose places both processes on an internal network and publishes only port `3000` to loopback.

## Runtime rules

- Bind the web console and native API to `127.0.0.1`, never `0.0.0.0`, by default.
- Store the SQLite database, master encryption key, exports, and generated media under one configurable local data directory.
- Keep connector secrets encrypted with a local 256-bit master key. Never return decrypted secrets to the browser or logs.
- Persist connector accounts separately from provider settings. Validate every config key, secret key, and requested scope against the adapter manifest before encrypting it.
- Use SQLite WAL, foreign keys, a busy timeout, short write transactions, and one durable writer workflow.
- Persist schedules before acknowledging them. If the computer is off, record and apply an explicit catch-up policy after restart.
- Bind each publish job to an exact content revision and a unique idempotency key. A duplicate scheduling request returns the existing job.
- Do not automatically retry an ambiguous remote publish. Mark it for review so a network timeout cannot silently create duplicate posts.
- Do not add PostgreSQL, Redis, Kubernetes, remote authentication, billing, or multi-tenancy to the core distribution.

## Control flow

```text
Trigger (schedule / UI / local connector listener)
  → durable local job
  → agent task with scoped context and provider budget
  → structured draft
  → deterministic schema and policy checks
  → approval request
  → version-bound human decision
  → connector action with idempotency key
  → normalized result and metrics
  → append-only audit event
```

The connector action never consumes free-form model output directly. Every payload is parsed into a versioned schema, validated, policy-checked, and frozen when submitted for approval. Editing after approval creates a new revision and invalidates the previous decision.

The singleton `workspace` row is also the durable brand profile. It stores business identity and factual context, content preferences and guardrails, visual direction, selected Media Library IDs, a monotonically increasing profile revision, and confirmation timestamps. The public state resolves selected media to path-free summaries. A save rejects unknown media IDs and appends `brand_profile.confirmed` to the audit log. Updating only the legacy basic workspace fields clears confirmation, so partially edited data cannot silently become trusted AI context.

Generation always receives the basic business name and description for compatibility with existing installations. Expanded brand fields are added only when the stored profile is both complete and explicitly confirmed. The prompt names the confirmed revision and treats restricted claims as prohibitions. Phase 4 sends text preferences and visual directions to the selected text model; referenced logo and image bytes remain local unless a later operator-approved media workflow explicitly uses them.

The local scheduler claims one due SQLite job at a time, recovers stale locks on restart, and applies a bounded catch-up window. Preflight failures can retry with backoff. Once a Telegram, WordPress, Facebook Page, Instagram, LinkedIn Member, or LinkedIn Company Page delivery has been reserved and attempted, an uncertain response becomes a failed review item instead of an automatic retry; the operator must explicitly review it before another attempt.

The media library stores metadata in `media_assets` and bytes under the configurable data directory's `media/` folder. Uploads and provider-generated bytes are bounded before decoding, verified from content rather than declared MIME claims, restricted to JPEG/PNG/WebP, protected by pixel and dimension limits, named with generated UUIDs, and deduplicated by SHA-256. Previews and preset transforms are newly encoded WebP files. Content endpoints resolve only database-owned storage names inside the media directory and send `nosniff`; the list API never exposes filesystem paths. Metadata may contain an operator-supplied public HTTPS source, but Socium never treats a loopback content URL as remotely publishable.

Image generation has a separate singleton `image_provider_settings` row so its encrypted credential, model, endpoint, and optional ComfyUI API-format workflow never overwrite the text provider. The hosted adapter sends a single prompt to an operator-selected OpenAI-compatible `/v1/images/generations` endpoint and expects base64 image data. Automatic1111/Forge receives a bounded `txt2img` request and may temporarily override a configured checkpoint. ComfyUI receives a copy of the stored workflow after explicit placeholders are replaced with the validated request; arbitrary node discovery or model-selected workflow mutation is not performed. The adapter submits `/prompt`, polls `/history/{prompt_id}` and `/queue`, reads the first image output through `/view`, and deletes or interrupts only the tracked prompt when cancellation is requested.

The browser queues `media.generate` work in `local_jobs` and receives immediately. The single SQLite worker owns provider execution, records monotonic stage progress, stores a provider prompt reference when available, observes a durable cancellation flag, retries safe generation failures with bounded backoff, and writes the resulting media asset ID on completion. A queued job snapshots the provider kind, model, and settings revision; changing provider settings makes the old job fail closed until the operator explicitly retries it. `media_generations` records every successful generation, including duplicate outputs, while `media_assets` carries the primary non-secret prompt, provider, model, and parameters displayed for review. No generation route creates a post or invokes a publisher.

## Local lead vault

Lead imports enter FastAPI as validated structured rows after the browser parses an operator-selected CSV locally. The SQLite `leads` table stores the current business/contact record, pipeline state, source evidence, and suppression state. A separate `lead_identities` table holds unique normalized email, domain, phone, and business-plus-location keys so duplicates can merge without replacing existing values.

Suppression is durable state, not deletion. A suppressed lead retains its identities and cannot be reactivated by a later CSV, CRM, or LinkedIn-export import; only an explicit local restore action can make it active again. Every import, status change, suppression, and restore operation appends an audit event. The global state contains only summary counts, while paginated lead records load from the dedicated lead endpoint so normal dashboard polling does not copy the entire vault.

Google Places discovery uses the official Text Search (New) endpoint through an encrypted, scoped connector. The API applies an explicit field mask and returns `Cache-Control: no-store`; Places content exists only in the current browser state with Google Maps and provider attribution. Socium does not persist search results. When the operator selects a result's public website, a separate source-independent crawl may create lead evidence from that website; the Google result is not treated as stored lead data.

The static website crawler resolves every request and redirect target before connecting and rejects non-public IP addresses, credentials, unsupported schemes, cross-domain redirects, oversized bodies, and non-HTML pages. It identifies itself, reads `robots.txt`, uses the declared crawl delay or a conservative default, serializes local crawl jobs, and visits at most four same-site homepage/contact/about pages. The extracted preview is no-store and reaches SQLite only after the operator explicitly imports it.

The singleton `icp_profiles` row contains versioned business-fit criteria, never model prompts or sensitive-trait rules. Saving a profile applies a deterministic 0–100 function to every lead in one local transaction. Each score stores its profile version, timestamp, and structured reason codes with signed point changes. New and merged imports use the current profile immediately. The high-intent view uses the effective score, while a manual correction is stored separately with a required reason so the original rule score and explanation remain available. Profile changes refresh the rule score but do not silently discard a human correction.

Outreach eligibility is a separate deterministic gate on the lead row: suppression must be clear, an email must exist, the legal basis and consent state must be compatible, the purpose/evidence note must be present, and the retention review date must be current. The `outreach_drafts` table stores provider provenance, editable subject/body copy, revision, decision state, and approval/export timestamps. Generation rechecks eligibility before and after the provider call. Every edit increments the revision and clears approval. CSV export requires that same approved revision and rechecks eligibility; there is no outreach delivery operation in the core. Per-lead JSON export supports portability, while typed permanent deletion removes the lead, identities, and drafts through SQLite foreign-key cascades and leaves a non-personal audit event.

The Local SEO lab reuses the crawler's URL normalization, public-address validation, same-site redirect, robots, response type, timeout, and size boundaries. The audit fetches one initial HTML response and deterministically evaluates 18 weighted checks across technical, on-page, content, and social categories. `seo_audit_snapshots` stores only the final URL, score, derived metrics, checks, crawler identity, and timing; raw HTML is discarded. Manual runs execute through a dedicated API while future one-off runs use `seo.audit` jobs in the durable SQLite worker. Publication jobs remain the only jobs returned in the global dashboard state, so SEO read-only work cannot be presented as outbound delivery.

## Local approval transports

- Dashboard decisions are always available and require no external callback.
- Telegram uses `getUpdates` long polling from the local worker; a public webhook is neither requested nor required.
- Slack account health checks call `auth.test` for the bot token and `apps.connections.open` for the app token. Verified, enabled accounts run a supervised Socket Mode connection; every envelope is acknowledged before a configured-channel, revision-bound decision is applied.
- WordPress uses the official REST API with an operator-created Application Password. Remote sites require HTTPS, credentials remain encrypted locally, and approved Blog revisions can publish immediately or through the durable scheduler.
- Meta Pages uses the official Graph API with an operator-supplied Page ID and Page Access Token. The adapter pins an explicit API version, verifies Page identity, requires the publishing scopes in its connector manifest, uses bearer authorization instead of token query strings, and publishes only exact approved Facebook revisions to the Page feed.
- Instagram Professional uses the modern Instagram Login API with an operator-supplied numeric account ID and encrypted token. It requires `instagram_business_basic` plus `instagram_business_content_publish`, verifies the account identity, and does not require a linked Facebook Page. The frozen post revision includes a public HTTPS image URL because Meta fetches the media remotely; localhost, private-network, credential-bearing, and fragment URLs are rejected. Publishing creates a media container, polls its status to `FINISHED`, and only then sends the container to `media_publish` with bearer authorization.
- LinkedIn Member publishing uses an operator-owned developer app and a member-authorized 3-legged OAuth token with `openid`, `profile`, and `w_member_social`. The connector verifies that `/v2/userinfo` returns the configured member ID, encrypts the token locally, and publishes only frozen approved text revisions through `/rest/posts`. Every publish supplies bearer authorization, `X-Restli-Protocol-Version: 2.0.0`, and an operator-pinned `Linkedin-Version` header. Browser cookies, passwords, page scraping, and simulated engagement are outside the connector boundary.
- LinkedIn Company Page publishing remains separate from member publishing because its authorization boundary is organization-specific and access gated. The connector requires `w_organization_social` plus `rw_organization_admin`, binds the token to the configured OIDC member, and checks `ORGANIC_SHARE_CREATE` through `/rest/organizationAuthorizations` for the exact `urn:li:organization:{id}`. Only a verified connector can send a frozen approved `linkedin-company` revision through `/rest/posts`; LinkedIn product approval, Page roles, and scope grants remain external prerequisites that Socium never attempts to bypass.
- Google Places uses official outbound Text Search requests; attributed results are transient and only public website-derived evidence may enter the lead vault.

## Adapter families

Adapters publish an ID, version, capability list, config schema, secret fields, health check, required scopes, rate-limit hints, and data-retention policy.

The connector registry is the public catalog and validation boundary. Account rows contain non-secret configuration and one encrypted JSON secret envelope. Public state projects only per-field presence flags; decrypted runtime data stays inside connector services and is never serialized into an API response.

### AI provider

The text-provider setting stores a provider kind, endpoint, model ID, and encrypted key. Hosted presets pin their official API root so a credential cannot be redirected to a different host through the normal settings API. OpenAI, Gemini, OpenRouter, and NVIDIA use their OpenAI-compatible chat contracts; Anthropic and custom Anthropic-compatible servers use the Messages contract and required version header. Ollama and custom adapters retain editable local/base URLs. Public state contains only a key-presence flag.

Local-AI inspection reports system memory, an optional NVIDIA GPU, Ollama process/API availability, installed models, and the configured durable model directory. A bounded recommendation selects a compact model tier. Ollama pulls stream newline-delimited progress through the loopback proxy; the service fills every crossed integer percentage, verifies the model through `/api/tags`, and only then stores it. Generation sets a short Ollama `keep_alive` so inference memory can unload while Socium is idle.

Custom provider discovery is deliberately two-stage. Credential-free auto mode probes only the entered origin for Ollama and standard `/v1/models` shapes. If the endpoint requires authentication or remains ambiguous, the API returns candidate protocols without accepting a secret. An operator-selected protocol then performs one minimal model-list request with the key and never sprays it across candidate contracts.

```python
class ModelProvider(Protocol):
    def list_models(self) -> list[ModelDescriptor]: ...
    def health(self) -> HealthResult: ...
    def generate(self, request: GenerateRequest) -> GenerateResult: ...
```

Image providers follow a narrower generate-one contract and return bytes rather than public URLs. The media verification boundary owns format detection and persistence; adapters never write arbitrary provider filenames or filesystem paths.

### Approval channel

```python
class ApprovalChannel(Protocol):
    def send(self, request: FrozenApprovalRequest) -> ExternalApprovalRef: ...
    def poll(self) -> list[ApprovalDecision]: ...
```

### Publisher

```python
class Publisher(Protocol):
    def validate(self, item: FrozenContentVersion) -> None: ...
    def publish(self, item: FrozenContentVersion, idempotency_key: str) -> PublishResult: ...
```

### Lead source

```python
class LeadSource(Protocol):
    def search(self, query: LeadQuery, cursor: str | None = None) -> LeadPage: ...
    def retention_policy(self) -> SourceRetentionPolicy: ...
```

## Security boundaries

- Only loopback traffic reaches native HTTP services.
- Connector credentials are encrypted at rest and decrypted only inside the local API/worker operation that needs them.
- Approval decisions are content-revision-bound and replay-protected by the provider update ID.
- Outbound provider URLs reject embedded credentials and unexpected schemes; crawlers add DNS/IP, redirect, size, and timeout controls.
- Crawled content is untrusted data and cannot override system policies or request tools/secrets.
- Publisher operations reserve an exact revision before the remote call and verify the reservation before finalizing it.
- Logs redact secrets and sensitive lead fields.

## Installation target

The primary stable installation is `npx socium onboard`. The small npm CLI resolves the current OS/CPU target from the published release manifest, requires HTTPS, verifies SHA-256 before extraction, validates bundle metadata, and atomically records the active immutable runtime. FastAPI is shipped as a native executable with migrations embedded; Next.js is shipped as a standalone server with flattened production dependencies. Python, uv, pnpm, Docker, and a source checkout are therefore not end-user prerequisites.

Mutable state is never placed inside the versioned runtime. SQLite, `master.key`, media, exports, logs, downloads, and the installation record live under the native application-data root documented in [INSTALLATION.md](INSTALLATION.md). `socium update` can replace runtime files without touching business data, while normal uninstall removes runtimes and preserves data unless the operator explicitly adds `--purge-data`.

Source development (`pnpm install`, `pnpm backend:sync`, `pnpm dev`) and Docker Compose remain supported secondary paths. Every mode opens only `http://127.0.0.1:3000`. The application continues working offline for local data, drafts, dashboard approvals, and Ollama; provider-backed features naturally require their provider connection.
