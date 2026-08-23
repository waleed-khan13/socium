# Socium — Product definition

## What it is

Socium is a downloadable, localhost-only growth operations console. A business defines its brand, goals, channels, policies, budget, and approval rules. Specialized AI agents then prepare work, but connector actions are executed only by deterministic local workflows with explicit permissions.

It borrows the useful control-plane ideas from agent-management products—goals, roles, heartbeats, budgets, approvals, adapters, and auditability—while focusing on the daily work of marketing, lead research, and SEO.

## Release tracks

- **Stable v1:** AI-assisted social and blog drafting, exact-revision approval, media preparation, official publishing connectors, durable scheduling, and local auditability.
- **Labs:** Lead intelligence and Local SEO stay compiled and locally usable behind `SOCIUM_ENABLE_LABS=1`, but are not part of the v1 stability promise.
- **v1.1 consumer lifecycle:** guided setup, managed background starts, daily update checks, verified local backups, and one-release rollback are implemented on the v1.1 branch.
- **Future updates:** richer media formats, metrics, discovery, SEO execution, plugins, and signed native installers graduate independently after their acceptance criteria pass.

## Who it serves

- Solo founders who need a repeatable content and lead workflow.
- Small businesses that want local control of customer and brand data.
- Agencies managing isolated client workspaces on their own machines.
- Developers who want an open adapter SDK instead of another closed automation SaaS.

## Product principles

1. **Approval before impact.** Public posts, outreach, destructive edits, and meaningful spend require a policy gate.
2. **Local data ownership.** Local AI and local storage are first-class, not degraded fallbacks.
3. **Official actions.** Publishing uses documented platform APIs. Data collection respects source terms, robots directives, consent, and applicable law.
4. **Agents propose; workflows execute.** LLM output is untrusted structured input. Deterministic code validates and performs actions.
5. **Everything is attributable.** Runs record inputs, model/provider, cost, policy result, approver, connector response, and rollback data.
6. **No hosted dependency.** SQLite, local listeners, CSV import/export, and generic OpenAI-compatible endpoints keep the core useful without a Socium cloud service.

## Core objects

| Object | Purpose |
| --- | --- |
| Workspace | Isolated business or agency client with its own secrets and policies. |
| Brand | Voice, offers, audience, claims, prohibited phrases, assets, and knowledge. |
| Goal | Measurable outcome tied to campaigns and agent tasks. |
| Agent | Role configuration such as Strategist, Copywriter, Lead Scout, or SEO Analyst. |
| Provider | Cloud or local model endpoint plus capabilities, limits, health, and cost rules. |
| Campaign | Goal, channels, audience, budget, dates, and content pillars. |
| Content item | Versioned draft with per-channel variants, assets, provenance, and schedule. |
| Approval | Immutable decision request: approve, regenerate, edit, skip, or expire. |
| Connector | Typed integration for approvals, publishing, lead sources, analytics, or CMS. |
| Lead | Permission-aware prospect record with source, evidence, score, and retention state. |
| SEO audit | Crawl snapshot, issue set, proposed fix, and before/after evidence. |
| Workflow run | Durable state machine instance with retries, idempotency, and audit events. |

## Agent team

- **Growth Strategist:** turns a goal into campaign themes, channel mix, and measurable experiments.
- **Researcher:** gathers cited industry/news inputs and marks freshness and source rights.
- **Copywriter:** produces platform-specific variants based on the brand voice.
- **Creative Director:** prepares image briefs and routes them to local or cloud image models.
- **Policy Reviewer:** checks claims, prohibited topics, duplication, PII, and platform constraints.
- **Publisher:** schedules approved content through official connectors; it cannot approve its own work.
- **Lead Scout:** searches licensed sources and public business sites, deduplicates, and captures evidence.
- **SEO Analyst:** audits technical/on-page SEO and proposes reversible changes.
- **Performance Analyst:** joins content with metrics and recommends the next experiment.

## Feature map

### Model hub

- Ollama, LM Studio, LocalAI, and generic OpenAI-compatible base URLs.
- Cloud adapters for OpenAI, Anthropic, Google, Groq, Mistral, and others.
- Capability routing for text, vision, embeddings, and image generation.
- Fallback chains, timeout limits, health checks, token/cost budgets, and per-agent model policies.
- Test console that never exposes a stored secret back to the browser.

### Brand and knowledge

- Guided brand profile, products/services, target personas, geographies, offers, proof, and tone.
- File/URL knowledge ingestion with citations and source expiration.
- Guardrails for claims, competitors, regulated terms, and phrases that must never be used.
- Multilingual output and reusable prompt/version registry.

### Content operations

- Campaign brief and content pillars.
- Weekly/monthly calendar with recurrence and channel-specific variants.
- Text, image brief, carousel outline, short-video script, blog, and newsletter drafts.
- Duplicate/claim checks, UTM builder, hashtag suggestions, and asset library.
- Approval from the dashboard, Telegram long polling, or Slack Socket Mode.
- Official publisher adapters for Meta, LinkedIn, X, Telegram channels, and WordPress as access permits.

### Lead intelligence

- Google Places adapter, licensed lead-provider adapters, CSV/CRM import, forms, and public website discovery.
- Domain crawler for contact pages and business metadata with robots/rate-limit controls.
- Deduplication, company/contact separation, ICP scoring, reason codes, and evidence URLs.
- Consent/legal-basis fields, suppression list, retention policy, and export/delete tools.
- Personalized outreach *drafts* with approval; no unsolicited mass-send engine in the core.

### SEO lab

- Robots, sitemap, canonical, metadata, headings, image alt text, link, schema, and indexability checks.
- Lighthouse/PageSpeed and Search Console connectors.
- Keyword-to-page map, content gaps, briefs, internal-link suggestions, and cannibalization warnings.
- WordPress or Git-based fix proposals with diff preview, approval, rollback, and scheduled re-audit.

### Operations and governance

- Visual workflow recipes and local event/schedule/connector triggers.
- Event-driven queue health with one local worker, durable leases, bounded timeouts/retries, crash-loop protection, and no idle rapid polling.
- Explicit Run now, Reschedule, or Skip recovery for overdue publication; missed work never auto-publishes after restart.
- Dead-letter runs, idempotency keys, and rate limits.
- Per-workspace/provider/agent budgets and stop switches.
- Encrypted local secret vault, scoped connector permissions, and audit export.
- Local multi-workspace agency view with strict data isolation.
- Local plugin SDK, import/export, and optional loopback MCP gateway.

## Extra features worth adding

- **Opportunity inbox:** turns analytics, SEO changes, mentions, and lead signals into ranked suggestions.
- **Content repurposer:** one webinar/blog becomes a controlled set of posts without copying unsupported claims.
- **Experiment ledger:** records hypothesis, variant, metric, result, and learning so the model improves from evidence.
- **Competitor watch:** monitors user-supplied public URLs and produces cited diffs; never impersonates or bypasses access controls.
- **Brand drift score:** compares every draft against approved examples and explains deviations.
- **Cost simulator:** estimates model and channel cost before a campaign is launched.
- **Portable workspace bundle:** exports configuration and non-secret data for backup or migration.

## Non-goals

- CAPTCHA solving, proxy rotation, account farming, or access-control bypass.
- Fake engagement, mass unsolicited messaging, or autonomous claims without review.
- Storing third-party source data beyond its license or platform policy.
- Letting an LLM directly hold unrestricted credentials or execute arbitrary shell/browser actions.
- Requiring a Socium-hosted account, remote database, or public deployment for core features.
