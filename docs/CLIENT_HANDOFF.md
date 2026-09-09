# Client Handoff Guide

## What is in this package

- FastAPI application and REST API.
- Responsive public marketing site.
- Student workspace.
- Recruiter workspace.
- Institution/TPO workspace.
- Platform administration workspace.
- Inbound privileged access-request review.
- PostgreSQL Docker deployment configuration.
- Alembic schema baseline.
- Automated functional tests and release-safety checker.
- Bootstrap tooling and Postman API collection.

## Recommended pilot deployment

Use managed PostgreSQL and HTTPS. Keep recruiter self-registration disabled. Use one tenant per institution. Configure SMTP before allowing real password resets. Configure Gemini only after the institution approves the AI-processing workflow and privacy notice.

Vercel/production already persists uploaded files in PostgreSQL-backed private storage. For larger/high-volume deployments, migrate binaries to dedicated private object storage with signed or application-authorized downloads and lifecycle policies.

## First-client configuration checklist

1. Replace PlaceAI logo/name/colors if white-labeling is part of the contract.
2. Create the institution tenant and TPO admin with `scripts/bootstrap.py`.
3. Import the first student batch using the CSV template in the TPO Students screen.
4. Provision approved recruiter accounts.
5. Configure campus job approval rules and the first placement drive.
6. Set SMTP and production base URL.
7. Set strong secrets and exact CORS origin.
8. Confirm privacy notice, retention period and AI-processing disclosure with the client.
9. Keep production data verified and configure real AI credentials when AI is enabled.
10. Run `pytest` and `python scripts/release_check.py` on the final artifact.


## Commercial boundaries

PlaceAI V3.1.3 is suitable for pilots and controlled small/medium deployments after environment-specific security/privacy review. Large enterprise procurement may additionally require SSO/SAML, MFA, centralized immutable audit export, dedicated object storage for high-volume binaries, malware scanning/content disarm, edge/WAF rate controls, observability/APM, formal backup/restore testing, penetration testing, DPA/privacy documentation and a support SLA.

## V3.0 go-live additions

Before a client production launch, validate the institution's placement policies, custom eligibility rules, document-retention requirements and incident-handling process. Company Verification is an evidence-screening workflow and must not be represented as statutory or legal certification unless PlaceAI is later connected to authoritative registries and the verification scope is contractually defined.

For current cloud production, these documents are persisted through the private PostgreSQL-backed `stored_files` layer rather than ephemeral disk. At larger scale, move the binary payloads to private object storage while preserving application authorization, retention/deletion rules and auditability. Configure malware scanning/content disarm appropriate to the institution's privacy policy.
