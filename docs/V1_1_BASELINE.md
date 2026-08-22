# Socium v1.1 baseline

Phase 0 freezes the starting point for the local-first consumer work.

## Source baseline

- Date: 2026-08-23
- Source branch: `main`
- Source commit: `c03560a` (`Place credential links beside each token field`)
- Development branch: `feature/v1.1-local-first`
- Product version at branch point: `1.0.5`
- Remote: `https://github.com/waleed-khan13/socium.git`

## Verified toolchain

- Node.js `24.11.0`
- pnpm `10.7.0`
- uv `0.11.11`
- Python `3.13.5`

## Baseline verification

The first complete `pnpm check` run established the following:

- TypeScript type checking passed.
- ESLint passed.
- CLI tests passed: 9 of 9.
- Ruff backend lint passed.
- Backend tests passed: 44 of 44.
- Five of six Playwright workflows passed.
- The remaining provider/credential workflow exposed a stale locator: WordPress changes the field-level link label after its site URL is configured. The product rendered the correct official and direct links; the assertion incorrectly assumed the unconfigured label after a prior workflow configured WordPress.

The branch fixes that assertion by scoping it to the stable `WordPress Application Password guide` link inside the WordPress connector card. The targeted Playwright workflow passes both from a clean test database and after the publishing workflow has configured WordPress.

The complete post-fix `pnpm check` passed on 2026-08-23:

- TypeScript type checking passed.
- ESLint passed.
- CLI tests passed: 9 of 9.
- Ruff backend lint passed.
- Backend tests passed: 44 of 44.
- Playwright workflows passed: 6 of 6.
- The optimized Next.js production build passed.

## Frozen v1.1 boundaries

- Local AI remains the recommended default; paid APIs are optional.
- NVIDIA remains a supported hosted preset.
- Dashboard, Telegram, and Slack are the only approval transports.
- WhatsApp is removed in the next implementation phase.
- Lead intelligence and Local SEO remain Labs-only.
- Runtime, durable data, and local-model storage become separate operator choices.
- Background work remains local and cannot execute while the computer is powered off.
- Missed publication requires an explicit run-now, reschedule, or skip decision.
- No Socium cloud account, password capture, CAPTCHA bypass, or provider-account browser automation is introduced.

The complete acceptance contract is [V1_1_RELEASE.md](V1_1_RELEASE.md).
