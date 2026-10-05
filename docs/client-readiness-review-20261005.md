# PlaceAI client readiness review — 5 October 2026

## Decision

Do not promise a large simultaneous client exam cohort yet. The website has role-specific workflows and automated ownership/security tests, but the production HR report path has real provider failures and the durable worker rollout is not complete. Green tests are necessary; they do not certify provider uptime, grading accuracy, capacity, or every possible security issue.

## Confirmed defects and changes in this release

| Finding | Evidence | Change |
| --- | --- | --- |
| Opening Mock Interview hides setup and reopens the last report | Entry code reads a saved session ID and calls analysis immediately | Setup always opens first; students explicitly open saved reports from history |
| Analysis appears to finish stages without a completed report | Fixed timers marked four stages done after elapsed time | Stages remain pending until the server confirms the complete report |
| A pending report traps the student on the analysis screen | Only retry was available | Return to setup is available after submission is saved and HR uploads finish; saved history remains available |
| Old async work can overwrite a newly opened assessment | Polling/controller used mutable session state | A generation token cancels obsolete UI updates and polling; ownership of the submitted server record remains unchanged |
| Historical completed reports may never render | Server status is complete but old stored JSON lacks `analysis_status` | Completed saved reports receive the explicit complete contract; invalid stored reports return a safe recovery error |
| History failures are silently hidden | Empty exception handler | Show an actionable loading failure |
| Temporary video provider rejection immediately aborts analysis | Vercel logs show Gemini ServerError with upstream HTTP 503 | One bounded retry reuses the same approved private upload; no retry for authentication or quota rejection; cleanup still runs |
| Runtime validation errors cannot be distinguished in support logs | Vercel also shows RuntimeError without a safe reason code | Allowlisted diagnostic codes identify processing, storage, evidence and segment failures without exposing student content or upstream response bodies |

Real affected submissions and recordings are retained. This release does not invent scores or alter a student's submitted answers. A bounded retry can recover a temporary failure; it cannot guarantee success during a sustained provider outage. Production support must verify pending reports individually through authorized application access.

## Remaining client release gates

| Priority | Gate | Required evidence/action |
| --- | --- | --- |
| High | Sustained provider failures leave HR reports pending | A successful isolated production HR analysis and subsequent saved-result read; reliable quota; queued recovery and alerting for prolonged failures |
| High | Render deployment is failing | Repair the existing runtime database login and approved private-table permissions, then verify a healthy deployment |
| High | Durable assessment queue is disabled | Apply the private queue schema with migration-owner permissions, deploy healthy workers, then enable admission in the application |
| High for large cohorts | Video bytes currently pass through API/database chunks | Direct private resumable object-storage upload, immutable objects, verified retention and owner/reviewer access before 5,000-video cohorts |
| High for capacity claims | No representative production-equivalent cohort test | Test 100/500/1,000/5,000 students in staging with starts, proctoring, video upload, coding execution, synchronized submissions and provider quotas; measure latency, loss, cost and recovery |
| Medium | Several server-managed tables do not have RLS | Current public roles have no CRUD privileges; review backend least privilege and migration ownership without blindly changing policies |
| Medium | Multiple deployment copies of the frontend | Canonical static files, public copies and embedded fallback must stay identical; automate stronger mirror checks rather than rewrite working modules |
| Medium | Grading quality needs a human reference benchmark | Compare consented representative English/HR answers and coding solutions against reviewed rubrics; include regional accents, silent recordings, irrelevant answers and accessibility needs |
| Medium | Operational support/access | Vercel dashboard logs are accessible, but the connector returns 403; provide approved monitoring, pending-report alerts and an incident owner |

See [capacity and rollout](assessment-capacity.md) for workload estimates, worker admission, staged validation and rollback. Pricing there is a planning estimate and must be checked before purchasing infrastructure.

## Security checks and limitations

On this date a read-only production permission query checked all public application tables/views for SELECT, INSERT, UPDATE and DELETE privileges of both `anon` and `authenticated`. None were granted. HR recording, media chunk and Google identity tables have RLS enabled. This is evidence against direct Data API table exposure, not proof of complete database security.

The automated suite covers student ownership, tenant/recruiter separation, private media playback, immutable submission, token rotation, role provisioning, trial/billing gates, size limits, prompt/response handling, queue admission and UI regressions. Release gates also run historical secret scanning, Bandit and dependency auditing. Browser checks use synthetic media; no student's face or voice is exported for testing. Authorization, privileged-role access, billing and retention rules remain release requirements.

The review uses [OWASP Top 10:2025](https://top10.owasp.org/2025/) as an assessment framework. It is not a penetration-test certificate. A scoped independent penetration test and restore/recovery exercise are appropriate before a major institution rollout.

## Competitive comparison

This compares documented assessment workflows, not every competitor or paid tenant configuration.

| Reference | Documented pattern | PlaceAI implication |
| --- | --- | --- |
| [HackerRank evaluation methods](https://candidatesupport.hackerrank.com/articles/3563234324-evaluation-methods-of-your-hackerrank-tests) | MCQs use answer keys; coding uses executed test cases; subjective responses require evaluation | Keep technical knowledge as MCQs, actual coding in the editor, and transparent grading methods; do not award credit for irrelevant text |
| [HackerRank detailed reports](https://support.hackerrank.com/collections/2192436165-test-reports) | Summary and question-specific reports | Keep an explicit saved-report journey, per-question evidence and section-level improvement actions |
| [Mercer Mettl question types](https://support.mettl.com/portal/en/kb/articles/type-of-questions-supported-on-mettl-platform-14-3-2023-1) | Objective questions, coding environments and timed audio/video responses, with preparation options | Retain distinct response modes, clear recording controls and timers; evaluate an optional preparation interval in a reviewed blueprint rather than silently changing live exam timing |

The immediate professional-quality priority is reliable saved submission and honest recovery. Extra badges or decorative elements cannot substitute for a complete, recoverable report and measured operational readiness.
