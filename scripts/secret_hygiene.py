from __future__ import annotations

import argparse
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


def _scan_text(source: str, text: str, findings: list[str]) -> None:
    for label, pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(f"{source}:{line}: possible {label}")


def scan_tracked_files(findings: list[str]) -> None:
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
        _scan_text(str(relative), text, findings)


def scan_history(findings: list[str]) -> None:
    """Scan every reachable Git revision without ever printing matched secret values."""
    names = subprocess.check_output(  # noqa: S603,S607 - fixed command
        ["git", "log", "--all", "--name-only", "--format=", "-z"],
        cwd=ROOT,
    )
    for raw_name in names.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode("utf-8", errors="replace").strip()
        if not name:
            continue
        path = Path(name)
        if path.name in FORBIDDEN_FILENAMES and path.name != ".env.example":
            findings.append(f"git-history:{name}: environment file was committed")
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            findings.append(f"git-history:{name}: private credential/certificate file was committed")

    process = subprocess.Popen(  # noqa: S603,S607 - fixed command
        [
            "git",
            "log",
            "--all",
            "--patch",
            "--no-ext-diff",
            "--no-color",
            "--format=PLACEAI_COMMIT %H",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Unable to open git history scan streams")

    current_commit = "unknown"
    for line_number, line in enumerate(process.stdout, start=1):
        if line.startswith("PLACEAI_COMMIT "):
            current_commit = line.removeprefix("PLACEAI_COMMIT ").strip() or "unknown"
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append(
                    f"git-history:{current_commit}:{line_number}: possible {label}"
                )

    stderr = process.stderr.read()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"git history scan failed with exit code {return_code}: {stderr.strip()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail if PlaceAI source control contains credential material.")
    parser.add_argument(
        "--history",
        action="store_true",
        help="also scan every reachable Git revision; CI must checkout with fetch-depth: 0",
    )
    args = parser.parse_args()

    findings: list[str] = []
    scan_tracked_files(findings)
    if args.history:
        scan_history(findings)

    if findings:
        print("Secret hygiene check failed:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1

    scope = "tracked files and full reachable Git history" if args.history else "tracked files"
    print(f"Secret hygiene check passed: no credential material detected in {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
