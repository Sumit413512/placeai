from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise SystemExit(f"Expected source block not found in {path}: {old[:120]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Load the shared error contract before every workspace script.
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

# Core workspace API wrapper: one normalized error type instead of raw Pydantic joins/statuses.
replace_once(
    "app/static/app.js",
    "  const esc = (v = '') => String(v ?? '').replace(/[&<>'\\\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',\"'\":'&#39;','\\\"':'&quot;'}[c]));\n",
    "  const esc = (v = '') => String(v ?? '').replace(/[&<>'\\\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',\"'\":'&#39;','\\\"':'&quot;'}[c]));\n"
    "  const apiErrors = window.PlaceAIApiErrors;\n",
)
replace_once(
    "app/static/app.js",
    "    if (!response.ok) {\n      let detail = `Request failed (${response.status})`;\n      if (contentType.includes('application/json')) {\n        const data = await response.json().catch(() => ({}));\n        detail = typeof data.detail === 'string' ? data.detail : (Array.isArray(data.detail) ? data.detail.map(x => x.msg).join(', ') : detail);\n      }\n      const err = new Error(detail); err.status = response.status; throw err;\n    }\n",
    "    if (!response.ok) {\n      const data = contentType.includes('application/json') ? await response.json().catch(() => ({})) : {};\n      throw apiErrors.createError(data, response.status);\n    }\n",
)
replace_once(
    "app/static/app.js",
    "    }catch(err){toast('Could not complete request',err.message,'error');}\n  });\n\n\n  // ─────────────────────────────────────────────────────────────\n",
    "    }catch(err){apiErrors.applyToForm(f,err);toast('Could not complete request',err.message,'error');}\n  });\n\n\n  // ─────────────────────────────────────────────────────────────\n",
)
replace_once(
    "app/static/app.js",
    "    }catch(err){toast('Could not complete request',err.message,'error');}\n  });\n\n  // Ctrl/Cmd + K command palette",
    "    }catch(err){apiErrors.applyToForm(f,err);toast('Could not complete request',err.message,'error');}\n  });\n\n  // Ctrl/Cmd + K command palette",
)
replace_once(
    "app/static/app.js",
    "}catch(err){toast('Reset failed',err.message,'error')}});return true;}",
    "}catch(err){apiErrors.applyToForm(form,err);toast('Reset failed',err.message,'error')}});return true;}",
)

# Public access portal: remove its duplicate Pydantic parser and use the shared contract.
access_path = Path("app/static/access-portal.js")
access = access_path.read_text(encoding="utf-8")
access = re.sub(
    r"\n  function apiErrorMessage\(data, status\) \{.*?\n  \}\n\n  async function requestJson",
    "\n  const apiErrors = window.PlaceAIApiErrors;\n\n  async function requestJson",
    access,
    count=1,
    flags=re.S,
)
if "function apiErrorMessage" in access:
    raise SystemExit("access-portal duplicate error parser was not removed")
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
access_path.write_text(access, encoding="utf-8")

# Password rotation: use the same API error object and field renderer.
security_path = Path("app/static/account-security.js")
security = security_path.read_text(encoding="utf-8")
security = re.sub(
    r"\n  function validationMessage\(data, status\) \{.*?\n  \}\n",
    "\n  const apiErrors = window.PlaceAIApiErrors;\n",
    security,
    count=1,
    flags=re.S,
)
if "function validationMessage" in security:
    raise SystemExit("account-security duplicate error parser was not removed")
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
security_path.write_text(security, encoding="utf-8")

# Mock interview uses the same API contract and field-level form feedback.
mock_path = Path("app/static/mock-interview.js")
mock = mock_path.read_text(encoding="utf-8")
mock = mock.replace(
    "  const esc = (value = '') => String(value ?? '').replace(/[&<>'\\\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',\"'\":'&#39;','\\\"':'&quot;'}[c]));\n",
    "  const esc = (value = '') => String(value ?? '').replace(/[&<>'\\\"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',\"'\":'&#39;','\\\"':'&quot;'}[c]));\n"
    "  const apiErrors = window.PlaceAIApiErrors;\n",
    1,
)
mock = mock.replace(
    "    if (!response.ok) throw new Error(typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`);",
    "    if (!response.ok) throw apiErrors.createError(data || {}, response.status);",
    1,
)
mock = mock.replace(
    "    } catch (error) {\n      toast(error.message,'error');\n    } finally {",
    "    } catch (error) {\n      apiErrors.applyToForm(form, error);\n      toast(error.message,'error');\n    } finally {",
    2,
)
mock_path.write_text(mock, encoding="utf-8")

# The dedicated mock-interview page must load the shared utility before its app script.
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
