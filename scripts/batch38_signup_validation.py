from pathlib import Path
import hashlib

path = Path("app/static/access-portal.js")
src = path.read_text(encoding="utf-8")

old = """  async function requestJson(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'include',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
    if (!response.ok) {
      const detail = typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`;
      throw new Error(detail);
    }
    return data;
  }
"""
new = """  function apiErrorMessage(data, status) {
    const detail = data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    if (Array.isArray(detail)) {
      const messages = detail.map(item => {
        if (typeof item === 'string') return item.trim();
        if (!item || typeof item !== 'object') return '';
        const rawMessage = typeof item.msg === 'string' ? item.msg.replace(/^Value error,\\s*/i, '').trim() : '';
        const loc = Array.isArray(item.loc) ? item.loc.filter(part => part !== 'body') : [];
        const field = loc.length ? String(loc[loc.length - 1]).replace(/_/g, ' ') : '';
        if (!rawMessage) return '';
        return field ? `${field.charAt(0).toUpperCase()}${field.slice(1)}: ${rawMessage}` : rawMessage;
      }).filter(Boolean);
      if (messages.length) return [...new Set(messages)].join(' ');
    }
    return `Request failed (${status})`;
  }

  async function requestJson(path, options = {}) {
    const response = await fetch(path, {
      credentials: 'include',
      ...options,
      headers: {'Content-Type': 'application/json', ...(options.headers || {})}
    });
    const contentType = response.headers.get('content-type') || '';
    const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
    if (!response.ok) throw new Error(apiErrorMessage(data, response.status));
    return data;
  }
"""
if old not in src:
    raise SystemExit("requestJson source block not found")
src = src.replace(old, new, 1)

marker = "  async function studentSignupSubmit(form) {\n"
validator = """  function validateStudentSignup(body) {
    const username = String(body.username || '').trim();
    const password = String(body.password || '');
    if (!/^[A-Za-z0-9._-]{3,80}$/.test(username)) {
      throw new Error('Username may only contain letters, numbers, dot, underscore, and hyphen.');
    }
    if (password.length < 12) throw new Error('Password must be at least 12 characters long.');
    if (!/[a-z]/.test(password)) throw new Error('Password must contain a lowercase letter.');
    if (!/[A-Z]/.test(password)) throw new Error('Password must contain an uppercase letter.');
    if (!/[0-9]/.test(password)) throw new Error('Password must contain a number.');
    if (!/[^A-Za-z0-9]/.test(password)) throw new Error('Password must contain a symbol.');
  }

"""
if marker not in src:
    raise SystemExit("studentSignupSubmit marker not found")
src = src.replace(marker, validator + marker, 1)

old_submit = """      const body = Object.fromEntries(new FormData(form).entries());
      await requestJson('/auth/signup', {method: 'POST', body: JSON.stringify({username: body.username, email: body.email, password: body.password, role: 'student', organization_slug: body.organization_slug || null})});
      const login = await requestJson('/auth/login-role', {method: 'POST', body: JSON.stringify({email: body.email, password: body.password, role: 'student'})});
"""
new_submit = """      const body = Object.fromEntries(new FormData(form).entries());
      body.username = String(body.username || '').trim();
      body.email = String(body.email || '').trim();
      body.organization_slug = String(body.organization_slug || '').trim();
      validateStudentSignup(body);
      await requestJson('/auth/signup', {method: 'POST', body: JSON.stringify({username: body.username, email: body.email, password: body.password, role: 'student', organization_slug: body.organization_slug || null})});
      const login = await requestJson('/auth/login-role', {method: 'POST', body: JSON.stringify({email: body.email, password: body.password, role: 'student'})});
"""
if old_submit not in src:
    raise SystemExit("student signup submit source block not found")
src = src.replace(old_submit, new_submit, 1)

old_password = '<label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="128" required placeholder="12+ chars, upper/lowercase, number and symbol"></label>'
new_password = '<label>Password<input type="password" name="password" autocomplete="new-password" minlength="12" maxlength="128" required aria-describedby="student-password-help" placeholder="12+ chars, upper/lowercase, number and symbol"><small id="student-password-help">Use 12+ characters with uppercase, lowercase, a number and a symbol.</small></label>'
if old_password not in src:
    raise SystemExit("student password field source block not found")
src = src.replace(old_password, new_password, 1)
path.write_text(src, encoding="utf-8")

test = Path("tests/test_signup_validation_ui.py")
test.write_text('''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_signup_ui_surfaces_fastapi_validation_details() -> None:\n    source = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")\n    assert "function apiErrorMessage(data, status)" in source\n    assert "Array.isArray(detail)" in source\n    assert "item.msg.replace" in source\n    assert "Request failed (${status})" in source\n\n\ndef test_signup_ui_enforces_backend_password_policy_before_submit() -> None:\n    source = (ROOT / "app/static/access-portal.js").read_text(encoding="utf-8")\n    assert "function validateStudentSignup(body)" in source\n    assert "Password must contain an uppercase letter." in source\n    assert "Password must contain a lowercase letter." in source\n    assert "Password must contain a number." in source\n    assert "Password must contain a symbol." in source\n    assert "validateStudentSignup(body);" in source\n''', encoding="utf-8")

manifest = Path("MANIFEST.sha256")
entries = {}
for line in manifest.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    digest, filename = line.split("  ", 1)
    entries[filename] = digest
for filename in ["app/static/access-portal.js", "tests/test_signup_validation_ui.py"]:
    entries[filename] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
manifest.write_text("".join(f"{entries[name]}  {name}\n" for name in sorted(entries)), encoding="utf-8")
