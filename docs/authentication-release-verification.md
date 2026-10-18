# Authentication release verification

All pull requests and main releases run the complete test suite in PlaceAI CI.
Authentication changes must retain these checks; passing a source or layout check
alone is insufficient evidence that a person can enter the workspace.

- `test_google_signin_browser.py` exercises a first-time student and a returning
  Google identity, signature rejection, reopening the sign-in panel, the optional
  authenticator prompt, actual workspace access, cookie restoration after reload,
  logout, and a rejected password login. It uses an isolated database, an ephemeral
  RSA key and Google's real token verifier. Only the external button and certificate
  transport are simulated. This is not proof that Google's live account chooser,
  consent configuration or a particular browser's popup policy is working.
- `test_google_auth_role_integrity.py` verifies audience, nonce, replay protection,
  account provisioning and binding, disabled accounts, privileged-role restrictions,
  existing MFA and concurrent account binding.
- `test_browser_smoke.py` verifies password login, optional authenticator setup,
  authenticator/recovery verification, email verification and password recovery UI.
- `test_auth_security_audit.py`, `test_auth_browser_origin.py` and the PostgreSQL
  authentication tests verify server enforcement, origin checks and concurrency.
- `test_unified_student_access.py` verifies current shared student access for old
  direct registrations and college-linked students. It also asserts that shared
  tools do not grant administration rights. The explicit segmented-policy tests
  preserve compatibility coverage for the optional future mode.
- `test_page_layout_browser.py` traverses all role navigation views with real
  isolated data on mobile, tablet and desktop.

After deployment, check the exact main SHA and production health on Vercel and
Render, production smoke, platform-access smoke and fallback convergence. Where
an authorized Google browser session is available, also complete the real Google
chooser, verify `/auth/me`, reload and sign out. Report an incomplete live-provider
check explicitly; never describe simulated provider verification as live consent.

Current rollout: `STUDENT_UNIFIED_ACCESS=true` by default. Students share feature
availability without changing organization membership or private-record scopes.
Payments and public creation of privileged accounts remain disabled. Changing
the access mode later requires explicit product approval and regression checks.
