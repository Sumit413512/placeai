import json
from pathlib import Path


def test_vercel_permissions_policy_allows_first_party_proctor_media():
    config = json.loads(Path("vercel.json").read_text(encoding="utf-8"))
    headers = config["headers"]
    global_rule = next(rule for rule in headers if rule["source"] == "/:path*")
    values = {item["key"]: item["value"] for item in global_rule["headers"]}
    policy = values["Permissions-Policy"]
    assert "camera=(self)" in policy
    assert "microphone=(self)" in policy
    assert "camera=()" not in policy
    assert "microphone=()" not in policy
    assert "geolocation=()" in policy
