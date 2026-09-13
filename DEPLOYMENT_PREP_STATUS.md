# PlaceAI release readiness — 13 September 2026

Baseline: PlaceAI Commercial V3.1.4 with the Vercel-primary production workspace and Render retained as a recovery fallback.

## Release architecture

- **Public product site:** `https://placeai-rxpp.vercel.app/`
- **Authenticated production workspace:** `https://placeai-rxpp.vercel.app/workspace`
- **Backend runtime:** the same Vercel production origin serves FastAPI APIs and static application assets.
- **Render fallback:** `https://placeai-recovery.onrender.com` remains a secondary recovery path only. It is not the release authority.
- **Database:** Supabase PostgreSQL project `cnpsvfpcxbrygynihlxs` in `ap-southeast-1`.
- **Schema:** Alembic production head is `20260911_0008`.
- **Transactional email:** production health requires the delivery transport to report operational.
- **AI provider:** production smoke requires `/ai/status` to report both `configured=true` and `sdk_available=true`; only `configured`, `sdk_available` and `model` are exposed.

The primary application is deliberately same-origin: public site, secure workspace, API, cookies, AI endpoints and password-reset actions use the Vercel production origin. This removes the Render proxy hop from the normal user path while preserving Render as an independent fallback.

## Verified application controls

- Production startup fails closed for invalid database/JWT/CORS/HTTPS/schema/reset-token-debug configuration.
- Backend dependencies enforce role and tenant authorization; frontend visibility is not authorization.
- Unverified students cannot discover protected campus opportunities; draft/inactive/expired/cross-tenant placement data is filtered at server boundaries.
- Recruiter candidate/interview visibility is employer-scoped.
- Institution application feeds are institution-scoped.
- Refresh sessions are database-backed, rotated and revocable; password change/reset invalidates older authentication state.
- Password reset is one-time, digest-backed and non-enumerating.
- Provisioned users use strong generated temporary credentials and permanent-password rotation/setup flows.
- Recruiter provisioning sends a one-time setup link to the approved work email rather than requiring an administrator-chosen permanent password.
- File uploads are bounded and signature-aware; production persistence is database-backed.
- Security headers include HSTS, CSP, frame denial, nosniff, strict referrer policy and restricted browser permissions.
- AI output is never fabricated when provider readiness is unavailable; human review remains required.
- CI produces per-commit release integrity evidence.
- Security CI runs tracked-secret hygiene, Bandit and production dependency auditing.
- `CODEOWNERS`, `SECURITY.md` and the production PR checklist are committed.

## Vercel-primary cutover controls

- Root `/` stays the public product/marketing surface.
- `/workspace` serves the complete authenticated PlaceAI workspace using the latest hardened frontend assets.
- Public role links resolve to same-origin `/workspace` rather than looping back to the marketing page.
- Password-reset links default to the Vercel `/workspace` in production; an exact stale Render override is ignored during Vercel production startup.
- Explicit custom production domains remain supported through `PUBLIC_APP_URL`.
- Legal pages and Mock Interview Coach are served through the FastAPI production routes instead of obsolete static rewrites.
- `VERSION` is aligned to `3.1.4`.
- Production smoke is now blocking on the exact Vercel release and verifies the public site, `/workspace`, latest release assets, legal pages, AI readiness, authorization boundaries and password-reset failure contract.
- Render fallback availability is checked separately and is intentionally non-blocking.

## Infrastructure state

- **GitHub repository:** private.
- **GitHub release gates:** PlaceAI CI, PlaceAI Security Audit and PlaceAI Production Smoke.
- **Supabase security:** prior release verification returned zero security-advisor lints; current schema head remains `20260911_0008`.
- **Render fallback:** healthy at the last live smoke, but its current private-repository integration cannot fetch new private commits. Do not make the repository public to repair this; reconnect Render to the private repository if fallback updates are required.
- **Render plan:** free. Do not treat it as a paid-SLA production tier.
- **Custom production domain:** not yet the release URL. The platform URL remains the authoritative public origin until domain/DNS changes are intentionally approved.

## Remaining owner/billing actions for larger commercial rollout

These are infrastructure/governance choices rather than unresolved application defects:

1. **Protected main / repository ruleset:** enable through the GitHub plan/settings if the account supports private-repository rulesets. Repository privacy must not be weakened to obtain branch rules.
2. **Provider paid/SLA tiers:** choose Vercel/Render/Supabase plans appropriate to contractual institutional traffic before promising paid-tier availability. This can incur charges and is not changed automatically.
3. **Custom domain:** connect the final PlaceAI domain, then validate `PUBLIC_APP_URL`, DNS/TLS, password-reset links, sitemap and provider origin settings.

## Release decision

**GO only after the Vercel-primary revision is merged to `main`, deployed to the Vercel production origin and the live PlaceAI Production Smoke workflow passes on that exact revision.**

Until that live gate is green, the currently healthy Render/Vercel hybrid remains the active production fallback. This document intentionally distinguishes application readiness from paid infrastructure and custom-domain decisions.
