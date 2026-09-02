# Socium v1.2 release contract

Version 1.2 turns the local-first v1.1 foundation into a guided, end-to-end social automation workflow. A non-technical operator can connect one primary AI provider, import editable brand context, create a recurring rule, review the generated post and image in Socium, Slack, or Telegram, and publish an exact approved revision without copying publishing tokens into ordinary forms.

## Shipped scope

- Website-assisted brand import with safe crawling, editable facts, colors, typography, and header/footer logo candidates.
- One primary local or hosted AI connection shared by copy, hashtags, calls to action, alt text, image planning, and supported image generation.
- A durable local media library that stores generated and uploaded assets with revision provenance.
- Guided Slack, Telegram, and LinkedIn connections with encrypted local credentials and actionable health states.
- Revision-bound approval actions for the post and image, including approve, edit, regenerate post, regenerate image, and skip.
- At-most-once publish job creation even when multiple approval channels act on the same revision.
- Recurring automation create, edit, pause, duplicate, delete, exact-day scheduling, and overdue recovery.
- Native Windows folder selection and tray lifecycle controls without PowerShell-based desktop integration.
- Dynamic loopback ports, bounded workers, sleeping listeners, provider timeouts, and restart-safe queues.

## Release evidence

- TypeScript, ESLint, Ruff, CLI, broker, and 101 FastAPI acceptance tests pass.
- Eight real Chromium workflows pass, including onboarding, provider setup, publishing, approvals, automations, media, accessibility, keyboard navigation, backups, and runtime controls.
- Production JavaScript, portable runtime, and synchronized Python dependency audits report no known vulnerabilities.
- The native Windows helper unit tests and optimized build pass; the bundled FastAPI executable passes isolated migration, encryption, and health smoke checks.
- Release version sources and lockfiles are synchronized and validated before a version tag can publish.

Release readiness: complete for v1.2.0.
