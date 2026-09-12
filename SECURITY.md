# PlaceAI Security Policy

PlaceAI handles student, recruiter, institution, and placement workflow data. Security reports should not include real candidate records, passwords, password-reset tokens, API keys, database credentials, or other secrets in public issues.

## Supported production line

The currently deployed production line is the latest verified `main` revision and the Render production gateway that has passed the repository CI, security audit, and production smoke workflows.

## Reporting a vulnerability

Report suspected vulnerabilities privately to the repository owner or the authorized PlaceAI security contact. Do not publish exploit details, credentials, personal data, or proof-of-concept payloads containing production records in GitHub issues.

Include the affected component, reproducible steps using non-production data, expected behavior, observed behavior, and impact. If credentials are suspected to be exposed, rotate them first and then investigate history and logs.

## Release security requirements

Production changes must preserve role and tenant authorization, avoid secret material in Git, keep password/reset credentials out of logs and telemetry, fail closed when dependent services are unavailable, and pass the automated security and production smoke gates before release.
