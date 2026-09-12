from __future__ import annotations

import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 2_000_000

FORBIDDEN_FILENAMES = {".env"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("Brevo API key", re.compile(r"xkeysib-[0-9A-Za-z_-]{20,}")),
    ("OpenAI API key", re.compile(r"sk-(?:proj-)?[0-9A-Za-z_-]{20,}")),
    ("GitHub token", re.compile(r"(?:ghp_[0-9A-Za-z]{36}|github_pat_[0-9A-Za-z_]{40,})")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    (
        "Private key material",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    ),
)


def tracked_paths() -> list[Path]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)  # noqa: S603,S607 - fixed command
    return [ROOT / value.decode("utf-8") for value in raw.split(b"\0") if value]


def main() -> int:
    findings: list[str] = []

    for path in tracked_paths():
        relative = path.relative_to(ROOT)
        if path.name in FORBIDDEN_FILENAMES and path.name != ".env.example":
            findings.append(f"{relative}: tracked environment file is forbidden")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"{relative}: tracked private credential/certificate file is forbidden")
        if not path.is_file() or path.stat().st_size > MAX_TEXT_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{relative}:{line}: possible {label}")

    if findings:
        print("Secret hygiene check failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Secret hygiene check passed: no tracked credential material detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
