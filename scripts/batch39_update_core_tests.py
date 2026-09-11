from pathlib import Path
import hashlib

path = Path("tests/test_core_flows.py")
src = path.read_text(encoding="utf-8")
old = '''client = TestClient(app)\n\n\ndef auth(token: str):\n    return {"Authorization": f"Bearer {token}"}\n\n\ndef login(email: str, password: str):\n    r = client.post("/auth/login-json", json={"email": email, "password": password})\n    assert r.status_code == 200, r.text\n    return r.json()["access_token"]\n'''
new = '''client = TestClient(app)\nROTATED_PASSWORDS: dict[str, str] = {}\nROTATED_TEST_PASSWORD = "PlaceAIRotated456!"\n\n\ndef auth(token: str):\n    return {"Authorization": f"Bearer {token}"}\n\n\ndef login(email: str, password: str):\n    current_password = ROTATED_PASSWORDS.get(email, password)\n    r = client.post("/auth/login-json", json={"email": email, "password": current_password})\n    assert r.status_code == 200, r.text\n    token = r.json()["access_token"]\n    me = client.get("/auth/me", headers=auth(token))\n    assert me.status_code == 200, me.text\n    if me.json().get("must_change_password"):\n        changed = client.post(\n            "/auth/change-password",\n            headers=auth(token),\n            json={"current_password": current_password, "new_password": ROTATED_TEST_PASSWORD},\n        )\n        assert changed.status_code == 200, changed.text\n        token = changed.json()["access_token"]\n        ROTATED_PASSWORDS[email] = ROTATED_TEST_PASSWORD\n    return token\n'''
if old not in src:
    raise SystemExit("core login helper block not found")
src = src.replace(old, new, 1)
old_direct = '''    r = client.post("/auth/login-json", json={"email": "student@northstar.example.com", "password": "StudentPass123!"})\n    assert r.status_code == 200\n'''
new_direct = '''    r = client.post("/auth/login-json", json={\n        "email": "student@northstar.example.com",\n        "password": ROTATED_PASSWORDS.get("student@northstar.example.com", "StudentPass123!"),\n    })\n    assert r.status_code == 200\n'''
if old_direct not in src:
    raise SystemExit("password reset direct login block not found")
src = src.replace(old_direct, new_direct, 1)
path.write_text(src, encoding="utf-8")

manifest = Path("MANIFEST.sha256")
entries = {}
for line in manifest.read_text(encoding="utf-8").splitlines():
    if line.strip():
        digest, filename = line.split("  ", 1)
        entries[filename] = digest
entries["tests/test_core_flows.py"] = hashlib.sha256(path.read_bytes()).hexdigest()
manifest.write_text("".join(f"{entries[name]}  {name}\n" for name in sorted(entries)), encoding="utf-8")
