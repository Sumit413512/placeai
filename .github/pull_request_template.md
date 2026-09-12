## PlaceAI production change

### Scope
- [ ] Change is limited to PlaceAI.
- [ ] No credentials, tokens, private keys, reset tokens, or production data are included.
- [ ] Tenant/role authorization impact was reviewed.

### Verification
- [ ] PlaceAI CI passes.
- [ ] PlaceAI Security Audit passes.
- [ ] Production smoke passes when the change affects the live path.
- [ ] Database migrations are reviewed and reversible where practical.
- [ ] UI/API validation contracts remain aligned.
- [ ] AI output remains human-reviewed and fails closed when provider configuration is unavailable.

### Release
- [ ] Render production behavior was verified for user-facing changes.
- [ ] Vercel is not treated as the user-facing release authority.
- [ ] Rollback path is understood before merge.
