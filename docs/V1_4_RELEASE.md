# Socium v1.4 Business OS foundation

Release readiness: complete for v1.4.3.

This is the source release contract, not a publication announcement. Tagging remains gated on successful candidate CI and the six-platform native dry-run described in RELEASING.md.

## User promise

Socium is a local-first AI Business OS that runs on the user's computer without a mandatory Socium account or hosted server. Social publishing remains the stable workflow, while confirmed business knowledge, reusable workflows, approvals, inbox work, and operational status now share one durable local foundation.

## Shipped scope

- v1.4.3 publishes manually created drafts as soon as they are approved from Slack or Telegram (when the destination is connected) and fixes browser-publishing session checks, interrupted Chromium installs, and Media Library alt text.
- v1.4.2 adds experimental local-browser LinkedIn member publishing, isolated sessions, optional Chromium installation, frozen draft destinations, and durable final-click guards. See [BROWSER_PUBLISHING.md](BROWSER_PUBLISHING.md) for prerequisites and limitations. This is not a live-account reliability certification or a claim that other platforms are API-free.
- A Next.js 16 App Router console using Tailwind CSS, shadcn/Base UI primitives, Lucide controls, official local platform SVGs, and locally bundled typography.
- A FastAPI and SQLAlchemy backend with SQLite WAL storage, Alembic migrations, foreign keys, busy timeouts, FTS5 knowledge search, and encrypted provider/connector secrets.
- A Business Profile plus source-attributed Knowledge Base. Extracted facts are proposals until a user confirms them; unconfirmed facts never enter prompts.
- Safe website analysis with public-network controls and logo discovery limited to headers, footers, metadata, and structured brand data.
- Durable workflow definitions, runs, steps, approval requests, notification deliveries, inbox items, preference memory, and AI decision logs.
- One shared approval boundary that rejects stale revisions and makes repeated Slack, Telegram, or dashboard decisions harmless.
- A real-data dashboard, current calendar, connected-channel state, upcoming work, approval queue, and explicit empty states when analytics are unavailable.
- Central content kits containing copy, hashtags, a call to action, image direction, exclusions, and alt text, with generated assets saved to the private Media Library.
- Background content generation with immediate job creation, percentage progress, bounded execution, retries, and durable result recovery.
- Additive migration from v1.3.1 without repeating onboarding or replacing the existing workspace profile.

## Data boundaries

- SQLite stores structured records and filesystem paths, not media bytes.
- The encrypted local vault stores API keys and OAuth tokens.
- The selected data directory stores media, documents, exports, and backups.
- The separately selected model directory stores local AI models.
- Temporary files remain outside durable records until verification succeeds.

PostgreSQL, MongoDB, Redis, and a separate vector database are intentionally outside v1.4. The v1.4.1 patch also includes the optional Gmail-thread, approved-reply, and consent-aware lead-campaign foundations. Broader growth features, business goals, analytics connectors, the plugin SDK, and approved SEO fixes remain v1.5/v1.6 work rather than simulated features.

## Acceptance evidence

- Backend migration, knowledge isolation, duplicate approval, job progress, scheduler recovery, and local-resource tests pass.
- Playwright covers onboarding, content generation, exact-revision approval/publishing, automations, media, lifecycle controls, keyboard navigation, automated accessibility, and responsive Business OS views at 375, 768, 1024, and 1440 pixels.
- Release verification requires consistent v1.4.3 versions, dependency/security checks, a production Next.js build, and native installer matrix smoke tests before tagging.

## Native artifacts

- Windows x64: `Socium-Setup-1.4.3.exe`
- Windows ARM64: `Socium-Setup-1.4.3-arm64.exe`
- macOS Apple silicon: `Socium-1.4.3.dmg`
- macOS Intel: `Socium-1.4.3-intel.dmg`
- Linux x64: `Socium-1.4.3.AppImage`
- Linux ARM64: `Socium-1.4.3-arm64.AppImage`

Users of native installers do not need Node.js, Python, Rust, Docker, Git, pnpm, or uv. Signing status is stated per GitHub Release; an application to the SignPath Foundation program is pending and must not be represented as an issued certificate.
