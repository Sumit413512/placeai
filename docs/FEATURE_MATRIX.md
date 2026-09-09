# PlaceAI V3.0 Feature Matrix

## Public / sales
- Responsive B2B marketing website and product positioning.
- Demo-request capture feeding the Platform Admin sales-lead pipeline.
- Security/privacy messaging and separate role workspaces.

## Student
- Institution-linked account, academic/profile management and institution-specific custom fields.
- Sensitive academic profile changes routed through placement-office approval.
- Resume upload/download, AI parsing, AI summary, job matching, skill-gap and mock-interview support.
- Explainable drive eligibility across CGPA, 10th/12th/diploma, backlogs, academic gaps, degree/branch/year, skills, certifications, required documents, work authorization and policy state.
- Placement Readiness Score with seven evidence components and recommended next actions.
- Public/campus job discovery, application tracking and configurable placement-drive pipeline visibility.
- Interview/assessment schedule with meeting details, attendance and result visibility.
- Offer Centre with accept/decline and authorized offer-letter download.
- Student document vault with controlled visibility.
- QR attendance check-in.
- Persistent notification centre and notification preferences.
- Announcements, placement calendar and role-aware AI Placement Assistant.
- Confidential recruiter/company/job incident reporting.
- Ctrl/Cmd + K role-scoped search.

## Recruiter
- Controlled recruiter provisioning and company profile.
- Company Verification Centre with evidence checks, authorization-letter upload, verification status/confidence and risk flags.
- Public/campus job creation and campus approval state.
- Applicant pipeline with AI rank + explanation, human-controlled stage movement and recruiter notes.
- Configurable drive pipeline visibility.
- Interview scheduling/rescheduling, attendance/results and structured human evaluation.
- Offer lifecycle, compensation, PPO/joining data and offer-letter PDF management.
- Persistent notifications and preferences.
- Recruiter/TPO communication threads with document attachments.
- Recruiter Analytics 2.0: applications, qualified candidates, stage distribution, interview/offer conversion, skill availability and authorized campus comparison.
- Role-aware AI Placement Assistant and command search.

## Institution / TPO
- Institution tenant scope, student provisioning/import/export and verification.
- Recruiter provisioning and institution-linked recruiter governance.
- Company Verification review for linked recruiters.
- Campus job approval/rejection and configurable placement drives.
- Advanced eligibility rules and explainable student eligibility.
- Placement Policy Engine for offer limits, placed-student restrictions, salary progression, internship and dream-company exceptions.
- Advanced drive pipeline configuration.
- Interview/assessment scheduling, attendance/results and human evaluation.
- Offer management and offer-letter access.
- QR attendance session creation.
- Persistent notifications/preferences and Announcement Centre.
- Attention Centre for operational student follow-up queues.
- Placement Analytics 2.0 and recruiter activity intelligence.
- Recruiter communication hub with controlled attachments.
- Confidential incident review/resolution.
- Seven one-click report families in CSV/XLSX/PDF.
- Custom student field definitions and value review.
- Unified placement calendar.
- Student academic/profile change approval workflow.
- Tenant-scoped audit trail and command search.

## Platform admin
- Institution tenant creation and TPO provisioning.
- Recruiter provisioning.
- Platform overview and inbound access-request pipeline.
- Lead status management.
- Cross-platform audit/admin foundation retained for future billing, feature flags and support operations.

## Security / production controls
- Argon2 password hashing.
- JWT access + rotating refresh workflow with HttpOnly refresh cookie.
- Hashed password-reset tokens and non-enumerating recovery.
- Strict script CSP and common security headers.
- Cross-tenant campus isolation and recruiter candidate-access boundaries.
- Controlled server-side file access for resumes, student documents, offer letters, authorization letters and communication attachments.
- Validated PDF/document size/type rules.
- Audit events for placement/governance changes.
- Gemini configured only through environment variables; AI fallback disabled by default.
- PostgreSQL production path, SQLite development, Alembic migrations and automated release checks.
