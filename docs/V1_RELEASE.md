# Socium v1.0 release contract

Version 1.0 is the stable, localhost-only social publishing edition. Its promise is deliberately narrow: an operator can connect an AI provider, generate a channel-aware draft, review an exact revision, approve it, and publish immediately or through the durable local scheduler without a Socium cloud account.

## Stable v1 capabilities

- Next.js console and FastAPI API bound to loopback, with SQLite WAL persistence and encrypted connector secrets.
- Ready-made Ollama, OpenAI, Gemini, Anthropic, OpenRouter, and NVIDIA text generation plus an advanced generic OpenAI-compatible adapter.
- OpenAI-compatible Images API, Automatic1111/Forge, and ComfyUI image generation into a reviewed local media library.
- Dashboard approvals plus Telegram long polling and Slack Socket Mode approval decisions.
- Immediate and scheduled publishing for Telegram, WordPress, Facebook Pages, Instagram Professional single images, LinkedIn Members, and access-approved LinkedIn Company Pages.
- Revision invalidation, idempotent publishing, retries, restart recovery, and a local audit trail.
- WhatsApp Cloud approved-template review notifications. Approval still happens in the dashboard, Telegram, or Slack.
- Checksummed one-command native installation on Windows, macOS, and Linux; source runs remain available for contributors and advanced operators.

## Explicit v1 limitations

- X can be used as a draft channel but has no publishing adapter yet.
- Instagram carousel and Reels publishing are not included.
- Instagram publishing needs a public HTTPS image URL because Meta fetches the asset; localhost media URLs cannot be fetched by Meta.
- WhatsApp interactive approvals are not included because Meta requires a reachable public HTTPS webhook.
- LinkedIn Company publishing depends on LinkedIn product approval, scopes, and Page permissions that Socium cannot grant.
- The computer and application must remain running for local listeners and scheduled work.
- Signed desktop packages, background-service integration, automatic backup/restore, normalized engagement analytics, and signed plugins remain roadmap work.

## Labs boundary

Lead intelligence and Local SEO are retained as opt-in previews, hidden by default. They do not share the v1 stability guarantee. To test them, set the environment variable below before starting the app:

```bash
SOCIUM_ENABLE_LABS=1
```

Labs never enable an HTML scraper for LinkedIn or Google Maps. Discovery uses permitted imports, the official Google Places API, and robots-aware public website crawling.

## Release acceptance

A v1 release candidate is acceptable only when all of the following pass from a clean install:

1. The npm CLI downloads the correct platform bundle, rejects a bad checksum, installs into an empty application-data root, and preserves the separate data directory across updates.
2. `pnpm check` passes type checking, linting, backend tests, browser workflows, accessibility checks, and the production build.
3. The default navigation does not expose Labs modules.
4. The API reports edition `social-v1`, Labs disabled, version `1.0.5`, loopback mode, and SQLite persistence.
5. The real localhost browser workflow proves generation, edit invalidation, approval, immediate publishing, scheduling, media handling, and durable image generation against deterministic provider stand-ins.
6. The installed native runtime boots its bundled FastAPI executable, applies SQLite migrations, serves the Next.js console through loopback, and passes `/api/health`.

## Release sequence

1. Run the complete acceptance suite and inspect generated browser artifacts.
2. Run the native workflow manually against `main` with `publish` disabled; every supported OS/CPU bundle must pass on its native runner.
3. Create a `vX.Y.Z` tag whose root, CLI, backend, and portable-runtime versions match.
4. Let the tag-triggered workflow rebuild the native assets and publish the archives, SHA-256 files, update manifest, and `socium` npm CLI.
5. Track Labs graduation and signed desktop packaging in [ROADMAP.md](ROADMAP.md) rather than expanding the v1 contract after tagging.

The exact maintainer procedure and first npm publication prerequisite are documented in [RELEASING.md](RELEASING.md).
