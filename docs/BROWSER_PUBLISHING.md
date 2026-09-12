# Browser publishing: implementation contract

Socium remains the existing Next.js / FastAPI / SQLite Business OS. Browser publishing is an additional local transport, not a second backend, scheduler, post model, or approval system. Existing API connectors and existing approved posts keep their current transport.

## First implementation slice

- Add `app/social_automation/` with typed contracts, a registry, profile/browser ownership, account/job persistence, publishing coordination, and an isolated LinkedIn adapter.
- Reuse `Post`, `LocalJob`, revision-bound approvals, the local scheduler, media integrity validation, and audit events.
- Add an explicit local-browser section to Integrations using existing Base UI components. Download Chromium on demand, connect through a visible login window, and opt an account into new LinkedIn drafts.
- Freeze account ID and identity on each new draft. Changing the preferred account must never redirect an already approved post.
- Publish through the existing job queue. Persist a pre-click intent before the final button; ambiguous results block another click for that revision even after restart or a generic job retry.
- Start with LinkedIn member text/single-image posts. Other platforms remain unavailable until separately implemented and verified. Live-site reliability is not inferred from mocked tests.

## Files and data

New files: this contract; migration `20260910_0025`; `backend/app/social_automation/{contracts,browser,store,manager,routes,registry,linkedin}.py`; `src/components/social-browser-card.tsx`; backend browser-publishing tests. The small reference adapter keeps selectors, authentication, publisher and verifier together in `linkedin.py`, separate from shared infrastructure.

Existing integration points: `models.py`, `store.py`, `main.py`, `scheduler.py`, `services/publishing.py`, approval message builders, `growth-console.tsx`, `automations-workspace.tsx`, shared frontend types, dependency locks, PyInstaller packaging, ignore rules, and architecture documentation.

Schema: local social accounts and revision/account-bound browser publish attempts; nullable browser destination fields on existing posts. Migration is additive and never recreates production tables. Browser cookies/profiles are filesystem data, not API responses. Profile directories are UUID-derived beneath the selected data directory. Chromium binaries are separate from profiles.

API: `GET /api/social-browser`; `POST /api/social-browser/install`; `POST /api/social-browser/accounts`; `POST /api/social-browser/accounts/{id}/{connect,verify,prefer}`; `DELETE /api/social-browser/accounts/{id}`; `POST /api/social-browser/jobs/{id}/cancel`. Setup operations return durable jobs immediately. Existing `/api/posts/{id}/publish` returns HTTP 202 for browser-bound posts. Public responses never include cookies, browser profile paths, raw browser exceptions, or authentication headers.

## Safety and lifecycle

- User logs in on the actual website. Socium never asks for the social password.
- No CAPTCHA solving, MFA interception, private endpoint reverse engineering, stealth plugins, fingerprint spoofing, or anti-bot evasion.
- One browser operation at a time, with an OS-released lock, bounded operation times, and context/process cleanup.
- Login is visible for up to three minutes; session checks and publishing are headless. Challenges require the operator to reopen login. A session is not promised to last forever. Restart cancels pending/interrupted login operations rather than reopening windows unexpectedly.
- Uncertain publication remains review-required, never automatically repeated. Verification requires a new identifiable post, not merely a closed composer or successful click.
- Browsers close after work. Local browser profiles contain sensitive session data; local ownership is not a claim of whole-profile encryption.
- Website automation may violate platform policies. LinkedIn prohibits third-party automation of website activity. The UI must disclose this risk before connection; official API mode remains available. No account-safety or permanent headless compatibility promise is made.
- Chromium increases download/disk requirements. Source and packaged runtime browser bootstrap must both use the pinned Playwright distribution without requiring the user to install developer tools.

## Verification and later phases

Use isolated SQLite databases and deterministic browser fixtures for approval guards, account binding, concurrent claims, stale/restarted attempts, challenge handling, selector failures, image validation, cancellation, and packaging checks. Never publish to a real account during automated acceptance tests.

Later slices: user-approved live LinkedIn validation; policy-reviewed Instagram/Facebook/X adapters; per-target multi-platform fan-out and richer media; expanded diagnostics. Multi-account records and locking belong in the foundation, not a later retrofit. This document is not a release announcement.

## Using the v1.4.2 experimental browser mode

1. Open **Integrations → Publish through your browser**.
2. Install the optional Chromium download. The driver is bundled with Socium; Chromium is stored in the selected models directory under `browser-runtime`. The download has a cancellable status indicator (not a fabricated percentage) and a 30-minute worker limit. Linux can require Chromium OS libraries; visible login needs a desktop session, so this flow is not a headless Docker login solution.
3. Review the platform-risk notice, add an account label and choose **Open login**. Complete login/MFA yourself; this does not reuse your everyday browser cookies. The initial adapter requires an English LinkedIn interface.
4. After verification choose **Use for new drafts**. New LinkedIn drafts freeze this account and public profile identity. Existing API drafts keep their original destination.
5. Generate and approve the content kit, then publish or schedule it. The usual Slack/Telegram approvals also apply; their API credentials are still required. Local AI avoids cloud AI API charges; choosing a cloud AI provider does not make that provider free.
6. If a result is uncertain, inspect the real profile. The stored attempt blocks a second automatic click for that exact revision. Do not edit/recreate a post just to work around an uncertain result.

Removing a login deletes only that account's owned session directory and retains the account identity and publishing history. Session cookies are sensitive filesystem data, **not encrypted by Socium's API-key vault**. Protect your data directory and backups; do not upload a browser profile to a public issue or repository. Media upload accepts one local PNG/JPEG/WebP up to 10 MB, with the draft's approved alt text; unsupported/changed controls stop before publishing.

## Checks

`uv run --directory backend pytest tests/test_social_browser.py` exercises database guards and real Chromium against intercepted fixture pages—no real social posting. Install development Chromium with `pnpm exec playwright install chromium` first. `pnpm exec playwright test -g 'browser publishing setup'` checks consent, cancellable setup states, WCAG checks and 375/768/1024/1440px layouts. `pnpm backend:bundle` followed by `pnpm backend:bundle:smoke` checks the packaged driver alongside the normal local API smoke checks.

These checks do not certify live LinkedIn selectors or acceptance of browser automation by the platform. Native installation support is separately gated by the six-platform release workflow. Check the GitHub v1.4.2 release status before expecting this feature in a public installer.

### Implemented checkpoint

The first slice is implemented in the existing application: additive migration, dedicated accounts/profiles, optional Chromium bootstrap, queued connect/verify/cancel controls, frozen destinations, shared approvals, durable publish intent, text/single-image adapter, and status/error handling. The automated browser fixtures intercept all requests and exercise both text and image/alt-text paths. The new UI uses existing shadcn/Base UI styling and Lucide controls; its consent and job states pass automated accessibility checks at all four supported widths. The complete 10-test Playwright suite and the Windows backend packaging/driver smoke check pass locally. Live-account validation and other platforms remain the next phase. This slice is included in the v1.4.2 release candidate; older installers require an update after publication.
