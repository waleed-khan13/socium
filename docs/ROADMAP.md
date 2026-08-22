# Roadmap

Socium is a downloadable, open-source, localhost-only application. It is not a hosted SaaS product. Every core feature must work with data stored on the operator's own computer, and the application binds to loopback by default.

## v1.0 release line

The first stable release is intentionally social-first. The default navigation contains content creation, the approval queue, media, scheduling, integrations, and activity. Milestones 3 and 4 remain available only through the opt-in Labs flag until their remaining acceptance work is complete. This is a scope boundary, not a deletion or rewrite.

## v1.1 local-first consumer line

The next release keeps the v1.0 publishing core and replaces documentation-led setup with a guided consumer workflow. Local AI is recommended, hosted AI remains optional, storage is operator-selectable, background work becomes resource-bounded, and updates move into the product. Dashboard, Telegram, and Slack are the only approval paths; WhatsApp is removed. Lead intelligence and Local SEO remain Labs-only.

The implementation order, fixed boundaries, storage and recovery rules, and release acceptance are defined in [V1_1_RELEASE.md](V1_1_RELEASE.md). Phase 0 evidence is recorded in [V1_1_BASELINE.md](V1_1_BASELINE.md).

## Milestone 0 — working product shell

- [x] Responsive localhost dashboard with custom shadcn-based UI.
- [x] Workspace onboarding, provider setup, approval queue, and audit feed.
- [x] Ollama and generic OpenAI-compatible provider connections.
- [x] Structured content generation with revision-bound approval.
- [x] Telegram notifications and Telegram publishing.
- [x] Encrypted connector secrets and local persistence.
- [x] Checksummed one-command native installation plus loopback-only source and Docker packaging.
- [x] Automated Playwright UI, WCAG A/AA, mobile keyboard, and real localhost workflow tests.

## Milestone 1 — local application core (complete)

- [x] FastAPI service bound only to `127.0.0.1` or the private Compose network.
- [x] SQLite WAL database with SQLAlchemy models and Alembic migrations.
- [x] One-time import from the v0.2 JSON store without exposing saved secrets.
- [x] Next.js same-origin proxy so the browser exposes only port `3000`.
- [x] Telegram long-polling approvals with no public webhook or tunnel.
- [x] Persistent local jobs, retries, idempotency, pause, and catch-up rules for Telegram publishing.
- [x] Native launcher that starts the API, worker, and web console together.
- [x] Backend unit/integration tests and a real localhost browser workflow suite.

**Acceptance:** a fresh install starts locally, connects Ollama or an API provider, generates a draft, receives a Telegram decision through long polling, publishes exactly once, survives a restart, and exposes the complete audit trail without any hosted Socium service.

## Milestone 2 — social publishing (v1 stable core)

- [x] Local connector manifests, capability registry, CRUD API, and encrypted scoped multi-secret token vault.
- [x] Slack account configuration plus real bot identity and Socket Mode token health checks.
- [x] Meta Pages adapter with encrypted Page tokens, health checks, and revision-bound immediate or scheduled Facebook publishing.
- [x] Instagram Professional single-image publishing with modern Instagram Login scopes, encrypted tokens, public-media validation, container status polling, and revision-bound immediate or scheduled delivery.
- [x] LinkedIn Member text publishing with OIDC identity checks, encrypted 3-legged OAuth tokens, pinned version headers, and revision-bound immediate or scheduled delivery.
- [x] Access-gated LinkedIn Company Page text publishing with OIDC identity checks, `ORGANIC_SHARE_CREATE` authorization verification, encrypted tokens, and exact-revision delivery.
- [x] Slack Socket Mode approval listener, outbound Block Kit requests, and version-bound interactive decisions.
- [x] WordPress REST publisher with encrypted Application Passwords, health checks, remote links, and durable Blog scheduling.
- [x] WhatsApp Cloud approved-template notification adapter with encrypted tokens, business-number verification, exact draft previews, and returned message IDs; interactive approval remains excluded because Meta requires a reachable webhook.
- [x] Private local media library with verified raster uploads, SHA-256 deduplication, previews, metadata, audited deletion, and social-size image transforms.
- [x] AI image generation with separately encrypted OpenAI-compatible and local Automatic1111/Forge providers, connection tests, validated ingestion, and durable provenance.
- [x] ComfyUI API-format workflow adapter with explicit placeholders, durable SQLite generation queue, progress, cancellation, retry, restart recovery, and final asset references.
- [ ] Instagram carousels/Reels, cross-channel calendar, and richer publisher failure recovery.
- [ ] Normalized engagement metrics and experiment ledger.

**Acceptance:** edits invalidate approval, scheduled posts cannot publish twice, and expired or revoked tokens produce actionable local recovery steps.

## Milestone 3 — compliant lead intelligence

- [x] Google Places API adapter with encrypted credentials, attribution, and transient no-store results.
- [x] CSV/CRM/LinkedIn-export import, durable identity deduplication, source evidence, pipeline status, and suppression lists.
- [x] Robots-aware public website crawler and contact-page extraction with SSRF, redirect, size, type, timeout, and delay controls.
- [x] Deterministic ICP scoring with versioned bulk rescore, explainable reason codes, high-intent filtering, and audited manual correction.
- [ ] Approved provider SDK; no credential theft, CAPTCHA bypass, or core LinkedIn scraper.
- [x] Outreach draft review, exact-revision approval and CSV export, consent/legal-basis gates, JSON data export, retention review filters, and explicit deletion tools.

## Milestone 4 — local SEO lab

- [x] Lightweight robots-aware HTTP audits with public-address, redirect, type, size, and timeout controls.
- [ ] Explicit Playwright fallback for rendered pages.
- [x] Technical/on-page audits and restart-safe scheduled snapshots.
- [ ] Search Console and PageSpeed/Lighthouse adapters.
- [ ] Keyword map, content briefs, internal links, and cited recommendations.
- [ ] WordPress/Git fix proposals with diff, approval, and rollback.

## Milestone 5 — open-source ecosystem

- [ ] Signed local plugin packages and compatibility metadata.
- [ ] Workflow recipe gallery and portable workspace bundles.
- [ ] Backup/restore, diagnostics, upgrade migrations, and security hardening.
- [x] Cross-platform CLI installer, isolated upgrades, data-preserving uninstall, diagnostics, and native release automation.
- [ ] Signed desktop installers and background-service integration.
- [ ] Contributor documentation and connector test harness.
