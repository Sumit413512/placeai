# PlaceAI release readiness — 12 September 2026

Baseline: PlaceAI Commercial V3.1.3 with final production hardening.

## Release architecture

- **User-facing production:** `https://placeai-recovery.onrender.com`
- **Render role:** authoritative public release gateway and release-smoke target.
- **Backend runtime:** Vercel FastAPI backend remains an upstream dependency behind the Render gateway; automatic Vercel Git deployment is intentionally frozen to avoid build/function quota churn.
- **Database:** Supabase PostgreSQL project `cnpsvfpcxbrygynihlxs` in `ap-southeast-1`.
- **Schema:** Alembic production head is `20260911_0008`.
- **Transactional email:** production health requires an operational configured delivery transport; Brevo HTTPS transactional delivery is supported independently of SMTP.

## Verified release controls

- Production startup fails closed for invalid database/JWT/CORS/HTTPS/schema/reset-token-debug configuration.
- Role and tenant authorization are enforced by backend dependencies rather than frontend visibility alone.
- Refresh sessions are database-backed, rotated and revocable; password changes/reset invalidate older authentication state.
- Password recovery uses one-time server-side token state and does not enumerate accounts.
- Provisioned accounts require first-login permanent-password rotation.
- TPO/student/recruiter temporary provisioning passwords are cryptographically generated in-browser, policy compliant, read-only, copyable/regeneratable, and preserved across failed submits.
- The obsolete capture-phase temporary-password clearing behavior has been removed from the account-security layer.
- Frontend/API validation contracts are regression tested.
- File uploads use bounded/signature-aware validation; production file persistence is durable and database backed.
- Security headers include HSTS, CSP, frame denial, nosniff, strict referrer policy and restricted browser permissions.
- AI output is never fabricated when Gemini is unavailable. AI controls and Mock Interview Coach degrade safely when provider readiness is false; core placement workflows remain usable.
- CI generates a per-commit SHA-256 integrity artifact.
- Security CI runs tracked-secret hygiene, Bandit and production dependency auditing.
- CODEOWNERS, security policy and a production PR checklist are committed.
- Production smoke verifies Render health, release assets, auth boundaries, password-reset failure handling and the privacy-safe AI readiness contract.

## Infrastructure verification

- Supabase security advisor: zero current security lints.
- Supabase performance advisor: informational unused-index notices only; indexes are intentionally retained until real production workload data exists.
- Recent Render request-log inspection: no 5xx and no 422/502/503 responses in the queried window.
- Recent Render resource usage is well below the current free-tier CPU and memory limits.
- Render runs one instance in Singapore.

## External owner actions before a larger commercial rollout

These are governance/availability actions, not application defects:

1. Change the GitHub repository from **public** to **private** in repository Settings.
2. Protect `main` with a GitHub ruleset requiring at least PlaceAI CI, PlaceAI Security Audit and PlaceAI Production Smoke, and disallow direct force-push/deletion.
3. Upgrade the active Render service from the free tier before depending on paid-production availability characteristics or higher traffic. This is a billing action and must be approved by the account owner.
4. Add a valid `GEMINI_API_KEY` only when AI features are intended to be enabled. Until then, PlaceAI now presents those features as unavailable instead of allowing a broken provider call.
5. Replace temporary platform URLs with the final PlaceAI custom domain when available, then set `PUBLIC_APP_URL`/CORS accordingly.

## Release decision

Application release is permitted only when the exact release revision has green **PlaceAI CI**, **PlaceAI Security Audit**, and **PlaceAI Production Smoke** results and the matching Render deployment is live. Do not infer readiness from source code alone.
