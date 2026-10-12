# PlaceAI security review — 12 October 2026

## Tool assessment

The supplied video shows [Strix](https://github.com/usestrix/strix), an Apache-2.0 AI penetration-testing agent. It supports source review, live API/browser testing, and exploit validation. It is suitable as an additional controlled staging assessment, with synthetic users, an explicit scope and request/model budgets. It is not a security certification or proof that an application has zero vulnerabilities.

Its local runtime requires a running Docker engine and an LLM connection. Docker was installed but its Linux engine was unavailable during this review, so **no Strix scan was performed**. No Strix cloud account was created, no repository/account credentials were shared with it, and no autonomous exploit crawl was run against student data.

The review instead used source inspection, isolated authentication/authorization attack regressions, Bandit, dependency advisory checks, reachable-history secret scanning, Supabase privilege/advisor queries, and bounded production HTTP checks.

## Verified findings and corrections

1. **Login CSRF / foreign browser authentication.** A synthetic account in an isolated database could be signed in through `/auth/login` with a foreign `Origin`; the response set a refresh cookie. Browser CORS alone does not prevent form submission or cookie changes. The shared middleware now rejects unsafe `/auth/` requests with an unapproved Origin before authentication, session rotation, logout or cookie mutation. Browser requests declaring `Sec-Fetch-Site: cross-site` without an Origin also fail closed. Same-origin requests, explicitly configured frontend origins and nonbrowser requests without browser-origin headers remain supported. Google's nonce verification and normal cookie protections remain in place.

2. **Authenticated response caching.** Invalid-token and other bearer-authenticated responses lacked a universal explicit no-store guarantee. They now receive `private, no-store` and `Pragma: no-cache`. Existing endpoint-specific `no-store` responses retain their contract.

3. **Unsafe meeting links.** Meeting URL input accepted arbitrary strings, including script schemes. HTML escaping alone does not validate URL protocols. Creation/update now validate HTTP(S) URLs without embedded credentials or control characters. The student reader also filters legacy unsafe URLs before constructing an anchor; normal meeting links and query passcodes remain supported.

4. **Development dependency advisories.** The development test runner was pinned to pytest 8.4.2, affected by a shared Unix temporary-directory advisory. It is updated to the patched 9.0.3 release. The local development pip is updated to 26.2.1. These change development/CI tooling, not the application's production dependencies; production Docker/CI already upgrade pip during builds.

## Scope and evidence

- Regression tests cover foreign/null/lookalike origins, successful same-origin/configured-origin/nonbrowser login, authentication cookie-mutation routes, cross-site fetch metadata and authenticated response/error caching. A pre-fix isolated regression returned HTTP 200 where HTTP 403 was required.
- Existing ownership, role, tenant, privileged provisioning, report/export, upload, token rotation, password, Google identity and Learning Hub reference-fetching tests remain part of the full CI suite.
- Before the patch, the main site's bounded HTTP check passed 18 of 21 assertions: the three failures were the cache guarantee and the two foreign-browser authentication checks.
- `scripts/security_surface_check.py` checks only the three named PlaceAI hosts. It checks release/database readiness, security headers, unavailable private artifacts/docs, authentication-required routes, invalid tokens, foreign browser authentication and CORS. It sends no credentials, accesses no authenticated student records and saves no response bodies.
- `PlaceAI Production Security Surface` runs after a successful Release Integrity workflow, daily and on manual dispatch. It requires all three hosts to serve the current main SHA and stores a sanitized check report. A failed request or failed assertion fails the workflow; a scan error is not treated as a pass.
- The live database privilege query found no `anon`/`authenticated` table read/write grants. Learning Hub tables have RLS enabled. Core backend tables use restricted browser grants and backend-only access. No public storage buckets were present; Supabase security advisors returned no lints. Application authorization remains necessary on backend routes.
- Bandit's configured medium/high-severity scan and tracked/reachable-history secret hygiene passed. The pinned production dependency audit found no known advisories; development environment findings are tracked separately from production packages.

## Running the bounded live check

```sh
python scripts/security_surface_check.py --expected-sha "$(git rev-parse HEAD)" --output security-surface.json
```

The script performs a small fixed number of requests per host. It does not brute-force accounts, crawl third-party systems, test volumetric denial of service, revoke real sessions, or mutate student assessment data. This assessment does not substitute for an independent professional penetration test, restore exercise, or ongoing operational security review. Payments remain deferred.
