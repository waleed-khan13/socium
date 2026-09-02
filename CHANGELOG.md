# Changelog

All notable user-facing changes are documented here.

## Unreleased

## 1.2.0 - 2026-09-02

### Added

- Added guided website analysis that drafts editable business facts, voice, colors, typography, and header/footer logo candidates for the brand profile.
- Added one-click Slack and LinkedIn OAuth handoff, automatic Telegram chat discovery, connector health feedback, and direct setup links where provider action is still required.
- Added recurring automation creation, editing, pausing, duplication, deletion, exact weekday schedules, per-rule approval routes, and missed-run recovery controls.
- Added a centralized generation pipeline that uses the primary AI connection for post copy, hashtags, calls to action, alt text, image prompts, and generated campaign media.
- Added a native Windows helper for folder selection and tray lifecycle controls, plus dynamic loopback port selection when the preferred port is occupied.

### Changed

- Unified generated images with the local media library and attached the exact revision and visual to Slack and Telegram approval requests.
- Made approval decisions idempotent across the dashboard, Slack, and Telegram so simultaneous approvals cannot create duplicate publish jobs.
- Reduced approval and regeneration latency with bounded work, explicit timeouts, status feedback, and idle listeners that wake only when work is pending.
- Improved readability, scheduling controls, connector guidance, and empty-state feedback across the local console.

### Security and privacy

- Kept OAuth credentials and provider secrets in the encrypted local vault while the public handoff broker stores only short-lived, single-use exchanges.
- Restricted website brand imports to safe public crawls and limited logo selection to header, footer, metadata, and structured brand candidates.
- Added signature verification, revision-bound action tokens, duplicate-action rejection, and cross-origin protection to approval and local control flows.

## 1.1.0 - 2026-08-24

### Added

- Added a resumable first-run wizard for storage, local or hosted AI, and a confirmed brand profile without requiring a Socium account.
- Added guided local Ollama setup plus OpenRouter, NVIDIA NIM, OpenAI, Gemini, Anthropic, and safely detected custom provider connections.
- Added brand-aware content kits with reviewed copy, hashtags, calls to action, image briefs, exclusions, alt text, and exact profile-revision provenance.
- Added revision-bound Approve, Regenerate, Edit, and Skip actions across the dashboard, Telegram, and Slack.
- Added a bounded, restart-safe scheduler supervisor with explicit overdue Run now, Reschedule, and Skip recovery.
- Added the System screen, daily idle-only update checks, checksum-backed backups, migration health checks, one-click rollback, stable native launchers, optional autostart, and Windows tray controls.

### Changed

- Separated immutable runtimes, durable SQLite data, and local model storage so operators can select suitable drives and safely relocate storage.
- Made Local AI the recommended path and kept hosted APIs optional, with clear disclosure when business data leaves the computer.
- Moved Lead intelligence and Local SEO behind the disabled-by-default Labs boundary and narrowed remote approval to Telegram and Slack.
- Replaced persistent heavy execution with deadline-based wakeups, one bounded worker, hibernating approval listeners, and an Ollama idle-unload window.

### Security and privacy

- Retired the WhatsApp product surface and delete only its legacy encrypted connector record during migration.
- Added atomic backup cleanup for full drives, checksum verification before activation, rollback after failed migrations, loopback-only random-token runtime controls, and release dependency audits.
- Added deterministic acceptance coverage for stale approvals, interrupted updates, migration failure, missing drives, crash loops, bounded memory, Labs isolation, and data-preserving uninstall.

## 1.0.5 - 2026-08-22

### Changed

- Changed release-download reporting to update at every completed percentage point in both interactive terminals and redirected output.

## 1.0.4 - 2026-08-21

### Added

- Added live release-download progress with percentage, downloaded and total size, transfer speed, and estimated time remaining in interactive terminals.
- Added throttled percentage milestones for redirected or non-interactive installer output.

## 1.0.3 - 2026-08-20

### Fixed

- Changed release downloads from a total-duration limit to a progress-based idle timeout, allowing very slow but active connections to finish.

## 1.0.2 - 2026-08-19

### Fixed

- Increased the native release archive download window so slower connections can complete the checksummed localhost installation.

## 1.0.1 - 2026-08-18

### Changed

- Rebranded the complete product and distribution surface as Socium, including the UI, `socium` npm/CLI package, `SOCIUM_*` configuration, native runtime assets, local application-data paths, documentation, and release automation.

## 1.0.0 - 2026-08-10

### Added

- Stable social-first release profile for local AI drafting, approval, publishing, scheduling, media, and audit workflows.
- Official publishing support for Telegram, WordPress, Facebook Pages, Instagram Professional single images, LinkedIn Members, and authorized LinkedIn Company Pages.
- Telegram and Slack approval decisions plus WhatsApp approved-template review notifications.
- Durable SQLite queues for scheduled publishing and AI image generation, including restart recovery, progress, cancellation, and retry.
- Opt-in Labs flag for the retained Lead intelligence and Local SEO preview workspaces.
- `npx socium onboard` installer and lifecycle CLI for checksummed Windows, macOS, and Linux native bundles.
- Standalone FastAPI runtime with embedded migrations and a portable Next.js production runtime; end users need only Node.js 20.9+.
- Tag-driven CI release automation for per-platform builds, native smoke tests, SHA-256 assets, the update manifest, and npm publication.

### Changed

- Default navigation now exposes only the v1 social publishing product surface.
- Runtime identity and documentation now describe the `social-v1` edition and its explicit limitations.
- Docker is now an optional advanced path rather than a prerequisite for the primary localhost installation.

### Security and privacy

- Local services bind to loopback by default, application data stays in the operator-controlled data directory, and saved connector secrets remain encrypted at rest.
- Native installers reject insecure remote manifests and archives with mismatched SHA-256 checksums; production web dependencies pass the high-severity audit gate.
