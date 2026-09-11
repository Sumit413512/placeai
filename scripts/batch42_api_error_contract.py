from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"Expected source anchor not found in {path}: {old[:100]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Shared assets load before all workspace consumers.
replace_once(
    "app/app.py",
    "        '<link rel=\"stylesheet\" href=\"/static/access-portal.css\">\\n'\n",
    "        '<link rel=\"stylesheet\" href=\"/static/api-errors.css\">\\n'\n"
    "        '<link rel=\"stylesheet\" href=\"/static/access-portal.css\">\\n'\n",
)
replace_once(
    "app/app.py",
    "        '<script src=\"/static/access-portal.js\" defer></script>\\n'\n",
    "        '<script src=\"/static/api-errors.js\" defer></script>\\n'\n"
    "        '<script src=\"/static/access-portal.js\" defer></script>\\n'\n",
)

# Core workspace API wrapper.
app_path = Path("app/static/app.js")
app_js = app_path.read_text(encoding="utf-8")
if "const apiErrors = window.PlaceAIApiErrors;" not in app_js:
    anchor = "  const fmtDate = v =>"
    if anchor not in app_js:
        raise SystemExit("app.js fmtDate anchor not found")
    app_js = app_js.replace(anchor, "  const apiErrors = window.PlaceAIApiErrors;\n" + anchor, 1)
old_error_block = """    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      if (contentType.includes('application/json')) {
        const data = await response.json().catch(() => ({}));
        detail = typeof data.detail === 'string' ? data.detail : (Array.isArray(data.detail) ? data.detail.map(x => x.msg).join(', ') : detail);
      }
      const err = new Error(detail); err.status = response.status; throw err;
    }
"""
new_error_block = """    if (!response.ok) {
      const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};
      throw apiErrors.createError(data, response.status);
    }
"""
if old_error_block in app_js:
    app_js = app_js.replace(old_error_block, new_error_block, 1)
elif new_error_block not in app_js:
    raise SystemExit("app.js API error block not found")
old_submit_catch = "}catch(err){toast('Could not complete request',err.message,'error');}"
new_submit_catch = "}catch(err){apiErrors.applyToForm(f,err);toast('Could not complete request',err.message,'error');}"
if old_submit_catch in app_js:
    app_js = app_js.replace(old_submit_catch, new_submit_catch)
elif new_submit_catch not in app_js:
    raise SystemExit("app.js submit catch anchor not found")
old_reset = "}catch(err){toast('Reset failed',err.message,'error')}});return true;}"
new_reset = "}catch(err){apiErrors.applyToForm(form,err);toast('Reset failed',err.message,'error')}});return true;}"
if old_reset in app_js:
    app_js = app_js.replace(old_reset, new_reset, 1)
elif new_reset not in app_js:
    raise SystemExit("app.js reset catch anchor not found")
app_path.write_text(app_js, encoding="utf-8")

# Public access portal: retire its duplicate parser.
access_path = Path("app/static/access-portal.js")
access = access_path.read_text(encoding="utf-8")
if "const apiErrors = window.PlaceAIApiErrors;" not in access:
    updated, count = re.subn(
        r"\n  function apiErrorMessage\(data, status\) \{.*?\n  \}\n\n  async function requestJson",
        "\n  const apiErrors = window.PlaceAIApiErrors;\n\n  async function requestJson",
        access,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("access-portal duplicate parser block not found")
    access = updated
access = access.replace(
    "    if (!response.ok) throw new Error(apiErrorMessage(data, response.status));",
    "    if (!response.ok) throw apiErrors.createError(data, response.status);",
    1,
)
access = access.replace(
    "      showError('role-login-error', error.message);\n      setBusy(form, false);",
    "      apiErrors.applyToForm(form, error, $('#role-login-error'));\n      setBusy(form, false);",
    1,
)
access = access.replace(
    "      showError('role-create-error', error.message);\n      setBusy(form, false);",
    "      apiErrors.applyToForm(form, error, $('#role-create-error'));\n      setBusy(form, false);",
    2,
)
if "function apiErrorMessage" in access or "apiErrorMessage(data" in access:
    raise SystemExit("access-portal still contains legacy error parsing")
access_path.write_text(access, encoding="utf-8")

# First-login password rotation uses the shared parser and field renderer.
security_path = Path("app/static/account-security.js")
security = security_path.read_text(encoding="utf-8")
if "const apiErrors = window.PlaceAIApiErrors;" not in security:
    updated, count = re.subn(
        r"\n  function validationMessage\(data, status\) \{.*?\n  \}\n",
        "\n  const apiErrors = window.PlaceAIApiErrors;\n",
        security,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise SystemExit("account-security duplicate parser block not found")
    security = updated
security = security.replace(
    "        if (!response.ok) throw new Error(validationMessage(data, response.status));",
    "        if (!response.ok) throw apiErrors.createError(data, response.status);",
    1,
)
security = security.replace(
    "        error.textContent = err?.message || 'Password update failed.';\n        error.classList.add('is-visible');",
    "        apiErrors.applyToForm(form, err, error);",
    1,
)
if "function validationMessage" in security or "validationMessage(data" in security:
    raise SystemExit("account-security still contains legacy error parsing")
security_path.write_text(security, encoding="utf-8")

# Mock Interview Coach uses the same contract.
mock_path = Path("app/static/mock-interview.js")
mock = mock_path.read_text(encoding="utf-8")
if "const apiErrors = window.PlaceAIApiErrors;" not in mock:
    marker = "  const state = { token:'', jobs:[], session:null };"
    if marker not in mock:
        raise SystemExit("mock-interview state anchor not found")
    mock = mock.replace(marker, "  const apiErrors = window.PlaceAIApiErrors;\n" + marker, 1)
mock = mock.replace(
    "    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`);",
    "    if (!response.ok) throw apiErrors.createError(data || {}, response.status);",
    1,
)
old_mock_catch = "    } catch (error) {\n      toast(error.message,'error');\n    } finally {"
new_mock_catch = "    } catch (error) {\n      apiErrors.applyToForm(form, error);\n      toast(error.message,'error');\n    } finally {"
if old_mock_catch in mock:
    mock = mock.replace(old_mock_catch, new_mock_catch, 2)
elif new_mock_catch not in mock:
    raise SystemExit("mock-interview submit catch anchor not found")
mock_path.write_text(mock, encoding="utf-8")

# Dedicated mock-interview HTML must load shared CSS/JS before its consumer.
replace_once(
    "app/templates/mock-interview.html",
    '  <link rel="stylesheet" href="/static/mock-interview.css">\n',
    '  <link rel="stylesheet" href="/static/api-errors.css">\n  <link rel="stylesheet" href="/static/mock-interview.css">\n',
)
replace_once(
    "app/templates/mock-interview.html",
    '  <script src="/static/mock-interview.js" defer></script>\n',
    '  <script src="/static/api-errors.js" defer></script>\n  <script src="/static/mock-interview.js" defer></script>\n',
)

print("batch42 API error contract transformation complete")
