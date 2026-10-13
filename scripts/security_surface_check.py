"""Bounded, non-destructive checks for PlaceAI's three deployed HTTP surfaces.

No credentials, active exploit crawler, user records, or response bodies are saved.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import httpx

TARGETS = (
    "https://www.placeai.in",
    "https://placeai-rxpp.vercel.app",
    "https://placeai-production.onrender.com",
)


def check_target(base, expected_sha=None):
    results = []
    def record(name, passed, status):
        results.append({"check": name, "passed": bool(passed), "status": status})
    with httpx.Client(base_url=base, timeout=45, follow_redirects=False) as client:
        health = client.get("/health")
        payload = health.json()
        record("release and database readiness", health.status_code == 200
               and payload.get("status") == "healthy" and payload.get("database") == "ok"
               and payload.get("configuration") == "ok"
               and (not expected_sha or payload.get("release_sha") == expected_sha), health.status_code)
        page = client.get("/")
        for header, expected in {
            "x-content-type-options": "nosniff", "x-frame-options": "DENY",
            "strict-transport-security": "max-age=31536000", "content-security-policy": "object-src 'none'",
        }.items():
            record(header, expected in page.headers.get(header, ""), page.status_code)
        policy = page.headers.get("content-security-policy", "")
        record("script injection and framing policy", "'unsafe-eval'" not in policy
               and "script-src 'self'" in policy and "frame-ancestors 'none'" in policy, page.status_code)
        for path in ("/.env", "/.git/config", "/docs", "/openapi.json", "/uploads/security-check.pdf"):
            response = client.get(path)
            record("private artifact unavailable: " + path, response.status_code == 404, response.status_code)
        for path in ("/auth/me", "/students/profile", "/recruiters/dashboard", "/institutions/dashboard",
                     "/learning-hub", "/enterprise/drives"):
            response = client.get(path)
            record("authentication required: " + path, response.status_code in {401, 403}, response.status_code)
        response = client.get("/students/profile", headers={"Authorization": "Bearer invalid-security-check-token"})
        record("invalid token rejected without caching", response.status_code == 401
               and response.headers.get("cache-control") == "private, no-store", response.status_code)
        for headers in ({"Origin": "https://foreign-origin.example.invalid"}, {"Sec-Fetch-Site": "cross-site"}):
            # No cookie is supplied; logout cannot revoke any account session.
            response = client.post("/auth/logout", headers=headers)
            record("foreign browser authentication blocked", response.status_code == 403
                   and "set-cookie" not in response.headers, response.status_code)
        response = client.options("/auth/login-json", headers={"Origin": "https://foreign-origin.example.invalid",
                     "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        record("foreign CORS origin rejected", "access-control-allow-origin" not in response.headers, response.status_code)
    return {"target": base, "checks": results, "passed": all(item["passed"] for item in results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, action="append")
    parser.add_argument("--expected-sha")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = []
    for target in args.target or TARGETS:
        print("Checking", target, flush=True)
        try:
            report.append(check_target(target, args.expected_sha))
        except (httpx.HTTPError, ValueError) as error:
            report.append({"target": target, "passed": False, "checks": [
                {"check": "HTTP verification completed", "passed": False, "status": type(error).__name__}
            ]})
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for target in report:
        print(target["target"], sum(check["passed"] for check in target["checks"]), "/", len(target["checks"]), "passed")
        for check in target["checks"]:
            if not check["passed"]:
                print("FAILED:", check["check"], "status", check["status"])
    return 0 if all(target["passed"] for target in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
