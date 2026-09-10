from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "tests/test_core_flows.py"
MANIFEST = ROOT / "MANIFEST.sha256"
WORKFLOW = ROOT / ".github/workflows/hardening-batch-autofix.yml"
SELF = Path(__file__).resolve()

OLD = '''    assert r.status_code == 202, r.text
    request = r.json()
    assert request["status"] == "new"
    request_id = request["request_id"]

    platform = login("platform@placeai.example.com", "PlatformPass123!")
    r = client.get("/platform/access-requests", headers=auth(platform))
    assert r.status_code == 200 and any(x["id"] == request_id for x in r.json())

    r = client.patch(
        f"/platform/access-requests/{request_id}",
        headers=auth(platform),
        json={"status": "under_review", "review_note": "Validated institutional request."},
    )
    assert r.status_code == 200 and r.json()["status"] == "under_review"
'''

NEW = '''    assert r.status_code == 202, r.text
    assert set(r.json()) == {"message"}
    assert "request_id" not in r.json()
    assert "status" not in r.json()

    db = SessionLocal()
    try:
        from app.access_models import AccessRequest
        access_request = db.query(AccessRequest).filter(
            AccessRequest.work_email == "priya@college.example.com",
            AccessRequest.requested_role == "institution_admin",
        ).order_by(AccessRequest.created_at.desc()).first()
        assert access_request is not None
        request_id = access_request.id
    finally:
        db.close()

    platform = login("platform@placeai.example.com", "PlatformPass123!")
    r = client.get("/platform/access-requests", headers=auth(platform))
    assert r.status_code == 200 and any(x["id"] == request_id for x in r.json())

    r = client.patch(
        f"/platform/access-requests/{request_id}",
        headers=auth(platform),
        json={"status": "under_review", "review_note": "Validated institutional request."},
    )
    assert r.status_code == 200 and r.json()["status"] == "under_review"
'''


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    text = CORE.read_text(encoding="utf-8")
    if OLD in text:
        CORE.write_text(text.replace(OLD, NEW, 1), encoding="utf-8")
    elif NEW not in text:
        raise SystemExit("Expected access-request regression block was not found")

    # These helper files are deliberately one-shot and must not enter the release.
    if WORKFLOW.exists():
        WORKFLOW.unlink()
    if SELF.exists():
        SELF.unlink()

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        _old_digest, relative = raw.split(maxsplit=1)
        relative = relative.strip()
        file_path = ROOT / relative
        if not file_path.is_file():
            raise SystemExit(f"Manifest path missing: {relative}")
        entries.append((relative, sha256(file_path)))
        seen.add(relative)

    for relative in (
        "app/routers/hardening.py",
        "tests/test_production_hardening_batch31.py",
    ):
        if relative not in seen:
            file_path = ROOT / relative
            if not file_path.is_file():
                raise SystemExit(f"New release path missing: {relative}")
            entries.append((relative, sha256(file_path)))
            seen.add(relative)

    MANIFEST.write_text(
        "".join(f"{digest}  {relative}\n" for relative, digest in entries),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
