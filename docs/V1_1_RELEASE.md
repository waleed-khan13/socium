# Socium v1.1 release contract

Version 1.1 is the local-first consumer edition. It keeps the v1.0 social-publishing core, removes setup that does not serve that workflow, and makes a clean install usable by a non-technical operator without requiring a Socium cloud account.

The existing v1.0 contract remains frozen in [V1_RELEASE.md](V1_RELEASE.md). Work for v1.1 is developed on `feature/v1.1-local-first` and reaches `main` only after the release-candidate acceptance suite passes.

## Product promise

A new operator can install Socium, choose where durable data and local models live, connect either local or hosted AI, confirm a brand profile, generate a channel-aware post and image, request human approval, and publish the exact approved revision. When the operator enables autostart, the application starts after login, consumes minimal resources while idle, recovers safely after restart, and reports updates inside the dashboard.

## Fixed product boundaries

- Socium remains open source, localhost-first, and loopback-bound by default.
- A Socium account, hosted Socium database, telemetry service, and Docker are not required.
- Local AI is the recommended setup. Hosted AI is optional and clearly identifies the data that leaves the computer.
- Dashboard approval is built in. Telegram and Slack are the only remote approval transports in v1.1.
- WhatsApp configuration, notifications, runtime code, tests, and documentation are removed in v1.1. A migration deletes its encrypted connector record without exposing the credential.
- Existing official social publishers remain available. Socium may open official setup pages and prefill non-secret configuration, but it never captures passwords, bypasses CAPTCHA or 2FA, or simulates prohibited account activity.
- Lead intelligence and Local SEO remain opt-in Labs previews and are not part of the v1.1 stability guarantee.
- The computer must be running to execute local work. An overdue task is never silently published after restart; Socium asks whether to run now, reschedule, or skip it.

## Delivery order

1. [x] Freeze the baseline and release contract.
2. [x] Remove WhatsApp and narrow approval scope.
3. [x] Separate runtime, durable data, and AI-model storage.
4. [x] Add the durable brand profile and content preferences.
5. [x] Replace documentation-led setup with a first-run wizard.
6. [x] Make local AI installation and hosted/custom provider discovery guided and testable.
7. [x] Generate brand-aware posts, hashtags, calls to action, and image prompts.
8. [x] Add revision-bound Approve, Regenerate, Edit, and Skip actions to dashboard, Telegram, and Slack.
9. [x] Replace always-heavy execution with a lightweight supervisor and bounded workers.
10. [x] Add native autostart, tray controls, in-product updates, backup, and rollback.
11. [x] Pass release hardening and publish `v1.1.0`.

### Phase 1 evidence

- Dashboard approval remains built in; Telegram and Slack are the only connector manifests with approval capability.
- The removed adapter is rejected by the connector API, and its legacy generation option is rejected instead of being ignored.
- Alembic revision `20260823_0013` deletes only legacy WhatsApp connector rows, including their encrypted secret envelopes, while preserving other connector accounts.
- Connector UI, delivery services, external-service mocks, credential guidance, and active product documentation no longer expose the retired integration.
- The complete `pnpm check` passed on 2026-08-23: CLI 9 of 9, backend 43 of 43, Playwright 6 of 6, accessibility checks, and the optimized production build.

### Phase 2 evidence

- Installation schema v2 stores independent runtime, durable-data, and local-model paths; existing schema-v1 installs migrate without moving or deleting their data.
- First install accepts `--data-dir` and `--models-dir`, and runtime updates retain both selections.
- A Socium storage marker prevents a disconnected or deleted configured drive from falling back to a new blank database.
- `socium storage move` requires the managed runtime to be stopped, copies SQLite/WAL, encryption keys, media, logs, exports, backups, and models, verifies file sizes and SHA-256 hashes, atomically activates the destinations, and preserves both sources.
- The dashboard reports all three locations, storage type, category usage, drive free space, and low-space/network/removable/cloud-sync warnings.
- The complete `pnpm check` passed on 2026-08-23: CLI 14 of 14, backend 43 of 43, Playwright 6 of 6 including accessibility and mobile-keyboard coverage, and the optimized production build. A follow-up unsafe-model-directory guard increased the CLI suite to 15 of 15 and its focused rerun also passed.

### Phase 3 evidence

- Integrations now starts with an explicit `Local AI - Recommended` or `Cloud API` choice. Local setup reports detected memory/GPU, Ollama availability, installed models, the configured model directory, and a hardware-sized recommendation.
- Socium can stream an Ollama model pull through the localhost proxy, reports every crossed percentage from 0 through 100, verifies the installed model, saves it as the selected provider, and requests Ollama to release inference memory after two idle minutes.
- Hosted presets remain available for OpenRouter, NVIDIA NIM, OpenAI, Gemini, and Anthropic without requiring a Socium account.
- `Custom / I'm not sure` performs credential-free discovery first. It recognizes Ollama, OpenAI-compatible, and Anthropic-compatible model contracts; when authentication prevents discovery, the operator must select one protocol before the key can be sent to exactly that contract.
- Provider and local-AI contracts have deterministic backend coverage, including the full 1% download sequence and secret-safe discovery. The focused browser tests prove the local/cloud mode switch, all hosted presets, custom discovery, and the existing complete generate/approve/publish workflow.
- The complete `pnpm check` passed on 2026-08-23: TypeScript, ESLint, Ruff, CLI 15 of 15, backend 50 of 50, Playwright 6 of 6 including accessibility and mobile-keyboard coverage, and the optimized production build.

### Phase 4 evidence

- Alembic revision `20260823_0014` extends the singleton workspace with durable identity, audience, offer, goal, voice, content-rule, color, logo, reference-media, visual-style, confirmation, and profile-revision fields while preserving existing workspace rows.
- The Integrations screen provides one complete brand editor built from the existing design system. It validates required facts and preferences, accepts optional verified Media Library assets, reports missing fields, and creates an audit event for every confirmed revision.
- The database stores only media IDs in the profile. Missing asset IDs are rejected, filesystem paths are never exposed, and deleting or changing unrelated credentials is outside the profile transaction.
- Rich brand context enters a generation prompt only when the profile is complete and confirmed. The prompt identifies the exact revision and carries target audience, offer, goals, call to action, voice, pillars, branded hashtags, visual direction, and explicit restricted-claim guardrails.
- Backend tests cover legacy-row migration, validation, asset binding, persistence, revision increments, audit history, and the confirmed-context boundary. A real Chromium workflow confirms the profile and proves that its revision and guardrails reach generation before the exact draft is approved and published.
- The complete `pnpm check` passed on 2026-08-23: TypeScript, ESLint, Ruff, CLI 15 of 15, backend 52 of 52, Playwright 6 of 6 including the expanded accessibility audit and mobile-keyboard coverage, and the optimized production build.

### Phase 5 evidence

- A clean local database opens an accessible modal wizard automatically. Its current step, dismissal, storage confirmation, and completion timestamps are stored in SQLite so setup can be dismissed, resumed, and reviewed without a Socium account.
- The storage step displays the active runtime, durable-data, and model locations with drive availability and free space. Reliability warnings require an explicit acknowledgement; changing locations remains a safe stopped-runtime operation with the exact checksum-verified move command available inside the wizard.
- The AI step recommends local Ollama, detects hardware and installed models, can stream and verify the recommended download, and supports a direct model connection. Cloud setup provides OpenRouter, NVIDIA, OpenAI, Gemini, Anthropic, and an explicitly selected OpenAI-compatible endpoint with official credential links.
- A provider becomes onboarding-ready only after a live test. Verification is bound to a fingerprint of its kind, endpoint, model, and settings revision, so changing those settings invalidates the verified state.
- The brand step reuses the complete confirmed-profile editor and local Media Library boundary from Phase 4. Completion is rejected transactionally until storage, AI, and brand readiness are all true; Telegram, Slack, and publishers remain optional.
- The browser acceptance flow now starts from a fresh installation, completes the wizard, reloads to prove durable completion, and then continues through generation, exact-revision approval, and publishing. Automated WCAG A/AA checks include the first-run welcome screen.
- The complete `pnpm check` passed on 2026-08-23: TypeScript, ESLint, Ruff, CLI 15 of 15, backend 53 of 53, Playwright 6 of 6, and the optimized production build.

### Phase 7 evidence

- Text providers now return a structured content kit containing title, channel-ready body, unique hashtags, an explicit call to action, a production-ready image prompt, visual exclusions, planned alt text, and rationale.
- Deterministic post-processing applies channel-specific body and hashtag limits, normalizes tags, carries confirmed branded hashtags, includes the CTA once in publishable copy, creates safe visual fallbacks for weaker local models, and rejects output containing an explicitly restricted brand claim.
- Alembic revision `20260823_0015` adds the complete kit and exact confirmed brand-profile revision to every durable post while preserving existing drafts with safe defaults. Editing any kit field creates a new post revision and invalidates prior approval through the existing boundary.
- The approval queue exposes every generated field for human review. **Create image from this brief** opens Media Studio with prompt, exclusions, and alt text prefilled; generated assets retain that alt text alongside their local AI provenance.
- Provider, migration, persistence, durable media-worker, and real Chromium workflow coverage prove structured generation, legacy-row compatibility, exact revision edits, one-click visual handoff, approval, and publishing.
- The complete `pnpm check` passed on 2026-08-23: TypeScript, ESLint, Ruff, CLI 15 of 15, backend 57 of 57, Playwright 6 of 6, and the optimized production build.

### Phase 8 evidence

- Dashboard, Telegram, and Slack now expose the same four human actions: **Approve** locks the exact revision, **Regenerate** creates a fresh pending revision, **Edit** opens the exact revision in the local dashboard, and **Skip** records an explicit non-publication state.
- Alembic revision `20260823_0016` adds one-time approval-action records bound to post, revision, transport, issue time, 72-hour expiry, remote reference, selected action, and terminal state. Callback payloads contain only the opaque local action ID.
- Every remote click is checked inside a SQLite write transaction. Wrong-transport, stale-revision, expired, already-used, unauthorized-channel, and Telegram update replays fail closed; deciding or changing a revision supersedes its remaining buttons.
- Remote regeneration uses the current verified provider and confirmed brand snapshot, then sends a new approval request for the new revision. Interrupted in-memory actions become visible failed records on restart instead of remaining stuck in a processing state.
- A remote Edit request is durable across restart, opens the matching dashboard dialog during the next local state refresh, and is acknowledged only after the browser receives it. Saving includes the expected revision and cannot overwrite a newer draft.
- Backend acceptance coverage exercises all four actions, migration compatibility, expiry, transport binding, replay rejection, remote-edit recovery, and interrupted-action recovery. The real Chromium workflow covers dashboard Regenerate, Edit, Approve, Skip, stale-decision rejection, and exact approved publication.
- The complete `pnpm check` passed on 2026-08-23: TypeScript, ESLint, Ruff, CLI 15 of 15, backend 60 of 60, Playwright 6 of 6 including accessibility and mobile-keyboard coverage, and the optimized production build.

### Phase 9 evidence

- The SQLite scheduler is now an event-and-deadline supervisor. With no queued deadline it waits indefinitely; due work starts one bounded worker and that worker exits after the job reaches a durable state.
- Durable lease tokens reject stale worker completion, recover after expiry, and are cleared on retry or completion. External work has a configurable timeout, bounded exponential retry for safe failures, and crash-loop protection that stops the supervisor in `Needs attention` after repeated control-loop failures.
- Alembic revision `20260823_0017` adds lease and recovery metadata. Any publication overdue after restart or pause is marked `missed`; the exact revision cannot run until the operator chooses **Run now**, **Reschedule**, or **Skip**. A changed revision and a repeated recovery action fail closed.
- Telegram long polling and Slack Socket Mode sleep without a live approval action. Slack activation is capped at one Socket Mode worker, and both transports wake only when approval work is created or changed.
- The scheduler card reports idle/working/faulted mode, the next wake, active worker count, idle time, and recovery count. A reload-safe accessible dialog exposes all three overdue decisions and never silently publishes.
- Phase-specific backend tests cover explicit recovery, revision rejection, leases, expiry recovery, timeouts, exponential retry, one-worker concurrency, crash loops, listener hibernation, and a 20,000-wake memory/coalescing soak. The real Chromium workflow covers restart-style reload, WCAG A/AA recovery UI, rescheduling, cancellation, and scheduler telemetry.
- The complete `pnpm check` passed on 2026-08-24: TypeScript, ESLint, Ruff, CLI 15 of 15, backend 67 of 67, Playwright 6 of 6 including accessibility and mobile-keyboard coverage, and the optimized production build.

### Phase 10 evidence

- Release bundles now contain a managed Node runtime, a versioned controller, and a stable launcher that resolves the active runtime from the installation record. Windows onboarding creates Start-menu and desktop shortcuts, can opt into start-after-login, and exposes a notification-area controller for opening the dashboard, restarting, and stopping Socium without a visible terminal.
- macOS LaunchAgent and Linux XDG autostart records use the stable launcher when explicitly enabled, so they follow an activated update instead of retaining a versioned path. Phase 11 applies the same installed-runtime lifecycle smoke contract to every native release target.
- The System screen checks at most once per 24 hours, shows installed/latest versions and release notes, and sends only a Socium version/platform user agent to the HTTPS manifest endpoint. Installing an update is disabled outside the managed release runtime and while a bounded worker is active.
- Every update downloads with byte/percentage progress, verifies the published SHA-256, creates a durable pre-update archive, activates an isolated runtime, runs migrations through a temporary loopback health check, and restores the prior runtime plus data snapshot if that check fails.
- Online backups use SQLite's consistent backup API, exclude transient locks/WAL files, include the encryption key and durable assets, and receive a SHA-256 sidecar. Offline CLI commands list and restore archives while preserving the replaced data directory; one prior runtime remains available for one-click rollback.
- Normal uninstall removes shortcuts and replaceable runtimes while preserving durable data and backups. Permanent deletion still requires both `--yes` and `--purge-data`.
- Phase-specific tests cover online SQLite backup consistency, minimal update metadata, unmanaged-action rejection, semantic version selection, checksum-backed offline backup/restore, and preservation of the pre-restore directory. The real Chromium System workflow covers backup creation, managed-control gating, and WCAG A/AA accessibility.
- The complete `pnpm check` passed on 2026-08-24: TypeScript, ESLint, Ruff, CLI 18 of 18, backend 71 of 71, Playwright 7 of 7, accessibility checks, and the optimized production build.
- The Windows x64 native artifact was rebuilt locally and passed both bundled-API migration/encryption smoke and the disposable clean-install smoke through its own managed Node/controller, including checksum install, doctor, loopback health, and explicit disposable teardown.

### Phase 11 evidence

- Every release version source, the locked Python project, portable web runtime, changelog, health response, CLI, and release documentation now agree on `1.1.0`. Release verification rejects an incomplete Phase 11 contract or missing dated changelog entry.
- Full-drive backup failure is atomic and actionable: incomplete archives and sidecars are removed. Interrupted downloads retain the active runtime, and failed migration health checks restore both the prior runtime and its verified durable snapshot.
- The migration-check process is terminated and awaited before activation completes, with a bounded forced-stop fallback for frozen macOS/Linux binaries; this prevents runtime locks from racing a later rollback. Normal uninstall continues to remove replaceable launchers/runtimes while preserving durable data and backups.
- The native smoke now proves checksum install, doctor, optional autostart, stable launcher/controller status and stop, in-place update, rollback, and data-preserving uninstall. The release workflow runs that contract for Windows x64/ARM64, macOS Intel/Apple silicon, and Linux x64/ARM64 before publication.
- Manifest assembly requires all six supported target fragments and includes the matching changelog notes. npm publication remains provenance-backed trusted publishing after the GitHub Release succeeds.
- Production JavaScript, portable runtime, and synchronized Python dependencies pass the high-severity audit gate with no known vulnerabilities. The complete local acceptance suite covers CLI 24 of 24, backend 72 of 72, real Chromium workflows, WCAG A/AA checks, and the optimized production build.

## Storage contract

- Runtime files are replaceable and never contain mutable business data.
- The operator chooses a durable data directory during onboarding. It contains SQLite, its WAL files, the matching encryption key, media, logs, exports, and backups.
- The operator may choose a separate local-model directory because model files are usually the largest assets.
- Settings reports per-category usage, free space, and low-space warnings.
- Moving data pauses workers, closes SQLite, copies all related files, verifies them, activates the destination atomically, and preserves the source until the operator confirms deletion.
- A missing destination pauses work and reports `Data drive unavailable`; Socium must not create a new empty database at the default path.
- Cloud-synced, network, and removable locations receive explicit SQLite reliability warnings.

## AI setup contract

The first-run choice is `Local AI - Recommended` or `Cloud AI`.

Local setup detects hardware, recommends a compatible model, lets the operator choose the model directory, reports every download percentage, verifies the model, and unloads heavy inference resources after an idle timeout.

Cloud setup provides OpenRouter, NVIDIA NIM, OpenAI, Gemini, and Anthropic presets. `Custom / I'm not sure` accepts a base URL and optional key, detects supported OpenAI-compatible, Anthropic-compatible, or local endpoints, reads available models where the endpoint permits it, and performs only an operator-approved minimal test. A secret is never sprayed across candidate providers.

`Let Socium choose` is the default model policy. Advanced operators may pin a model. Provider secrets remain encrypted locally and are never returned to the browser or logs.

## Brand and content contract

The durable brand profile includes business identity, website, industry, products or services, target audience, location, goals, call to action, language, tone, content pillars, restricted claims, branded hashtags, logo, colors, reference media, and preferred visual style.

Website-assisted setup produces an editable preview; imported text never becomes trusted brand truth until the operator confirms it. Post copy, hashtags, alt text, and image prompts use the confirmed brand profile and remain pending human review.

Generation time and publish time are separate. A default lead time gives the operator time to review before delivery.

## Approval state contract

The durable flow is:

```text
scheduled_generation -> generating -> awaiting_approval -> approved -> scheduled_publish -> publishing -> published
```

- Approve locks the exact revision.
- Regenerate creates a new revision and requires fresh approval.
- Edit opens the exact revision in Socium; saving invalidates approval.
- Skip records an explicit non-publication decision.
- Old, repeated, expired, or mismatched revision actions are rejected transactionally.
- If approval arrives after the planned publish time, Socium asks to publish now, reschedule, or skip.

## Resource and recovery contract

- Idle scheduling is event-driven; there is no rapid polling loop.
- A lightweight supervisor owns the next deadline and starts bounded workers only for due work or pending remote approval activity.
- Local generation concurrency defaults to one. Every external operation has a timeout, bounded retries, exponential backoff, and an observable terminal state.
- Heavy inference processes unload after idle and worker processes exit after completion so the operating system reclaims memory.
- Crash-loop protection stops repeated restarts and marks the task `Needs attention`.
- Restart recovery uses durable leases, revision checks, idempotency keys, and explicit handling for ambiguous publish responses.
- A long-running soak test must show no unbounded idle-memory growth.

## Installation and update contract

- The prompt-free CLI entry is `npx -y socium@latest onboard`.
- The consumer path is a native installer, starting with Windows, followed by macOS and Linux packages.
- Installation offers data and model locations, creates shortcuts, and can enable start-after-login.
- A tray controller can open the dashboard, report state, and stop or restart Socium.
- The update checker runs at most once per day while idle and sends only current version and platform metadata needed to resolve an artifact.
- Updates display release notes and byte-accurate progress, wait for active work, back up durable state, verify the published checksum/signature, apply migrations, and roll back the runtime on failure.
- Normal uninstall preserves durable data; permanent deletion remains explicit.

## v1.1 acceptance

A release candidate is acceptable only when all of the following pass:

1. `pnpm check` passes type checking, lint, CLI tests, backend lint/tests, Playwright workflows, accessibility checks, and the production build.
2. A fresh operator can select a non-system drive for data and models and complete onboarding without reading external Socium documentation.
3. Local AI and every hosted preset, including NVIDIA, have deterministic connection tests; custom endpoints fail safely and explain the missing requirement.
4. Brand information drives reviewed copy, hashtags, and image prompts without inventing restricted claims.
5. Dashboard, Telegram, and Slack prove Approve, Regenerate, Edit, Skip, stale-action rejection, and restart recovery.
6. Scheduled publication remains exactly-once, and overdue work always requires the configured explicit recovery decision.
7. Full-disk, missing-drive, offline-provider, revoked-token, worker-crash, interrupted-update, and migration-failure scenarios preserve data and surface actionable errors.
8. Windows clean install, autostart, tray, update, rollback, uninstall, and data preservation pass on a native runner. macOS and Linux native targets pass the same installed CLI lifecycle contract, with tray controls remaining Windows-specific.
9. A memory soak demonstrates bounded idle usage and release of heavy local-AI resources after work.
10. The release contains no WhatsApp product surface or runtime path, and Labs remain disabled by default.

## Explicit non-goals

- Publishing at an exact time while the computer is powered off.
- A required Socium cloud account or hosted scheduler.
- Password collection, CAPTCHA or 2FA bypass, browser-cookie extraction, or fragile automation of provider account settings.
- LinkedIn or Google Maps scraping outside approved APIs, operator-owned exports, and the existing compliance boundary.
- Graduating Lead intelligence or Local SEO into the stable navigation during v1.1.
