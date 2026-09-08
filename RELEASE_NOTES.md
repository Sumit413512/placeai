# PlaceAI Release Notes

## 3.1.3 — Production Security & Persistence Hardening

- Added rotating, database-backed refresh sessions with replay prevention and logout revocation.
- Added `auth_version` invalidation so password reset immediately invalidates older access and refresh credentials.
- Added durable database-backed file storage for Vercel production uploads while retaining local development storage.
- Hardened cross-institution references across attendance, communications, interviews, and incident workflows.
- Enforced attendance opening/closing windows and invalid time-range rejection.
- Added production startup guards for HTTPS base URL/CORS, distinct strong JWT secrets, PostgreSQL, and migration-only schema changes.
- Require verified Google account email claims.
- Added database-backed throttling for signup, login, refresh, Google auth, password-reset requests and public demo requests with hashed bucket identifiers and `Retry-After` responses.
- Raised new/reset/provisioned password policy to 12+ characters with uppercase, lowercase, numeric and symbol requirements.
- Added upload magic-byte validation, OOXML package validation for DOCX/XLSX, UTF-8 text enforcement, filename path stripping and rejection of legacy `.doc`/`.xls` payloads.
- Added bounded auth/provider payload sizes to reduce resource-abuse surface.
- Added prompt-injection guardrails around untrusted resume/job/profile/interview data.
- Bounded PDF extraction to 30 pages and 50,000 extracted characters; migrated from vulnerable/deprecated PyPDF2 to maintained `pypdf==6.18.0`.
- Removed access-token persistence from browser storage; access tokens are memory-only and restored after reload through the rotating HttpOnly refresh session.
- Strip password-reset tokens from the browser URL immediately after parsing.
- Aligned all browser password controls with the backend 12-character policy and removed the non-functional “Keep me signed in” control.
- Expanded regression coverage for security/session/storage/tenant boundaries, auth limits, PDF limits and browser token hygiene (12 tests).

### Compatibility
- Schema additions align with the live `auth_version`, `refresh_sessions`, and `stored_files` production baseline.
- Existing V3.1.2 features and API paths are retained.

## 3.1.2 — Student Opportunity & QR Reliability

A focused student-login correction and regression pass over the Open Opportunities, search, dialog and QR attendance workflows.

### Fixed
- Open Opportunities job-type selection now immediately filters results instead of requiring a separate search-box event.
- Opportunity search now covers role, company, skills, location, type, compensation, experience and related role metadata, with an accurate visible-result count and clear no-results state.
- Student command search only returns opportunities the signed-in student is authorized to see; pending/unapproved campus jobs remain hidden.
- Opportunity table columns now use stable semantic widths and alignment for role, company, skills, type, deadline and action data.
- Generic dialogs now keep an explicit Cancel/Close action visible at normal zoom while long content scrolls internally; Escape also closes active dialogs.
- QR attendance fetches the protected image with the authorization header, reports loading/failure states, and renders the returned PNG reliably.
- Locally generated QR links no longer encode `localhost` when the workspace is being accessed through another host; configured production `BASE_URL` values are still honored.
- QR responses disable caching to avoid stale attendance codes.

### Validation
- Full automated backend suite passes.
- JavaScript syntax and Python module compilation pass.
- Student opportunity filtering/search, modal visibility and QR rendering were exercised in Chromium at 1440×900 and 1280×720 viewport sizes.
- Added regression coverage preventing pending campus opportunities from leaking into student command search.

### Compatibility
- No database schema change.
- Existing V3.1 databases remain compatible.

## 3.1.1 — UX Corrections Final

A final viewport and navigation reliability pass over V3.1, based on live laptop testing at normal browser zoom.

### Additional fixes
- Sidebar navigation keeps a stable scrollbar gutter so labels do not shift as the navigation becomes scrollable.
- Mobile navigation now has a proper dismissible backdrop and locks background-page scrolling while the drawer is open.
- Placement Policy cards can expand across a wider operational workspace instead of staying artificially narrow when only one policy exists.
- Retains V3.1 fixes for independent sidebar scrolling, active-item visibility, duplicate action removal, human-readable policy rules, viewport-safe tables/modals and long workspace names.

### Compatibility
- No database schema change.
- No API contract change.
- Existing V3.0/V3.1 databases remain compatible.

## 3.1.0 — UX Corrections & Navigation Reliability

This maintenance release keeps the V3.0 Enterprise Suite feature set intact and fixes usability problems found during live local testing.

### Fixed
- Institution/recruiter/student sidebars now scroll independently at normal browser zoom, including short laptop displays.
- Sidebar header, workspace identity, AI policy notice and sign-out area remain accessible while only the navigation list scrolls.
- Active navigation entries are automatically scrolled into view after navigation.
- Mobile sidebar closes after selecting a destination instead of covering the newly loaded page.
- Duplicate page-level primary actions were removed; the sticky top bar is now the single action location.
- Placement Policy Engine no longer exposes raw JSON as the primary UI. Rules are rendered as human-readable operational settings.
- Single-policy screens use a wider responsive policy layout instead of leaving most of the workspace empty.
- Wide tables, enterprise panels and modal content are constrained to the usable viewport and scroll internally when needed.
- Long institution/workspace names truncate safely and expose the full value on hover.
- Short-height desktop layouts compact sidebar spacing so more navigation is visible without reducing browser zoom.

### Compatibility
- No database schema change.
- No API contract change.
- Existing V3.0 data and demo accounts remain compatible.

# Release Notes

## 3.0.0 — Enterprise Placement Operations Suite

- Added Company Verification Centre with evidence-based verification status, confidence and risk flags. CIN/GSTIN checks are structural evidence checks, not government-registry certification.
- Added configurable multi-stage placement-drive pipelines and application stage movement.
- Added interview/assessment scheduling, rescheduling, mode/venue/link/slot management, attendance, results and structured human evaluation.
- Replaced demo notifications with persistent database-backed notifications and user notification preferences.
- Added evidence-based Student Placement Readiness Score and recommended actions.
- Added role-aware AI Placement Assistant using authorized PlaceAI context.
- Added advanced explainable eligibility and institution Placement Policy Engine.
- Added offer lifecycle, CTC/PPO/joining data and authorized PDF offer-letter upload/download.
- Added student document vault, QR attendance and confidential incident reporting.
- Added TPO Attention Centre and Placement Analytics 2.0 including monthly trends, drive conversion, internship/PPO conversion and unplaced segmentation.
- Added role-scoped Ctrl/Cmd + K search, Announcement Centre, recruiter/TPO communication threads with attachments, custom institution fields, unified placement calendar and academic profile-change approval workflow.
- Added seven institutional report families with PDF/XLSX/CSV export.
- Upgraded typography, sidebar/icon system, responsive tables, applicant pipeline presentation and enterprise UI consistency while retaining the existing PlaceAI frontend architecture.
- Hardened the V3 Alembic migration for both fresh and upgraded installations.
- Added comprehensive V3 workflow tests covering enterprise read/write operations and controlled document downloads.
- Gemini remains environment-configured; no API keys or client secrets are included in the release artifact.

## 2.3.0 — Professional recruiter intelligence

- Replaced checkbox-style sidebar markers with clean stroke icons and a more professional navigation treatment.
- Reworked recruiter skill analytics into an applicant capability snapshot instead of long progress bars.
- Added Company Trust Review with evidence scoring for institution verification, provisioning, website, domain email, LinkedIn and profile completeness.
- Added institution-side Trust Review access for linked recruiters.
- Added AI ranking explanation access in the applicant pipeline.
- Updated the default Gemini model to `gemini-3.8-flash` and added `scripts/check_gemini.py`.
- No API secret is embedded in the release package.

# PlaceAI Commercial V2.2

Targeted patch over V2.1. No redesign or application-architecture replacement.

- Corrected the student Resume & AI Readiness heading typography and removed accented Resume labels that could render inconsistently.
- Added `GEMINI_MODEL` configuration with stable default `gemini-2.5-flash`.
- Added public non-secret `/ai/status` diagnostics so local setup can be verified without a bearer token.
- Improved Gemini failure messages for missing key, missing SDK, or provider/quota/network errors.
- Candidate AI ranking and resume AI now share the same configurable Gemini model.
- Added visible demo Notifications for Student, Recruiter, Institution Admin, and Platform Admin.
- Made the existing Updates button open Notifications and added an unread badge / Mark all read interaction.
- Added `docs/GEMINI_SETUP.md`.

# PlaceAI Commercial V2.1 Release Notes

This is the clean client-safe commercial rebuild of the uploaded student recruitment prototype.

## Delivered

- Professional responsive public B2B website and role-specific application UI.
- Student, recruiter, institution/TPO and platform-admin workspaces.
- Institution multi-tenancy and cross-campus data isolation.
- Verified recruiter provisioning and institution linkage.
- Campus job approval, placement drives and CGPA/branch/batch eligibility.
- Student application pipeline and institution outcome visibility.
- Bulk CSV student import + template + validation report + CSV export.
- Tenant-scoped audit trail for critical placement/account actions.
- Public demo-request form feeding a platform-admin sales lead pipeline.
- AI resume parsing, matching, skill-gap and mock-interview capabilities with production-safe fallback behavior.
- Hardened auth: Argon2 passwords, access/refresh tokens, HttpOnly refresh cookie, hashed reset tokens and non-enumerating reset requests.
- Strict script CSP, security headers, validated PDF uploads and recruiter privacy boundaries.
- PostgreSQL + Docker + Alembic deployment path.
- Demo seed, platform bootstrap, Postman collection, sales/client handoff documentation.
- Automated test suite and release-safety checker.

## Verification

Final source verification completed with:

- `pytest -q` — all tests passed.
- Python `compileall` — passed.
- `node --check app/static/app.js` — passed.
- Live Uvicorn smoke checks for health, homepage, TPO login and public demo-request capture — passed.
- Clean release artifact scan — must pass `python scripts/release_check.py` before distribution.

## Production note

This release is suitable for pilots and controlled client deployments after environment-specific security/privacy review. Large enterprise deployments should add the enterprise controls listed in `docs/CLIENT_HANDOFF.md` and `docs/SECURITY_RELEASE_CHECKLIST.md`.
