from pathlib import Path

p = Path('docs/CLIENT_HANDOFF.md')
text = p.read_text(encoding='utf-8')
text = text.replace('- Inbound demo-request sales pipeline.\n', '- Controlled privileged-access request pipeline.\n')
text = text.replace('- Demo seed, bootstrap tooling and Postman API collection.\n', '- Bootstrap tooling and Postman API collection.\n')
text = text.replace('9. Remove demo data and keep `ENABLE_AI_DEMO_FALLBACK=false`.\n', '9. Verify the environment contains no sample, seeded or synthetic production records.\n')
start = text.find('\n## Demo accounts\n')
end = text.find('\n## Commercial boundaries\n', start)
if start != -1 and end != -1:
    text = text[:start] + text[end:]
p.write_text(text, encoding='utf-8')

p = Path('docs/SECURITY_RELEASE_CHECKLIST.md')
text = p.read_text(encoding='utf-8')
text = text.replace('- Keep `ENABLE_AI_DEMO_FALLBACK=false`.\n', '- Require AI provider failures to fail explicitly; never substitute synthetic AI output in production.\n')
text = text.replace('- Review all institution/recruiter accounts and remove demo users/data.\n', '- Review all institution/recruiter accounts and remove unauthorized test users/data before launch.\n')
p.write_text(text, encoding='utf-8')

Path('scripts/retire_demo_docs.py').unlink(missing_ok=True)
