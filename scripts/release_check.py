#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BANNED_PARTS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache"}
BANNED_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pyc"}
BANNED_NAMES = {".env"}
violations = []

for path in ROOT.rglob("*"):
    rel = path.relative_to(ROOT)
    if any(part in BANNED_PARTS for part in rel.parts):
        violations.append(str(rel))
        continue
    if path.is_file() and (path.name in BANNED_NAMES or path.suffix.lower() in BANNED_SUFFIXES):
        violations.append(str(rel))
    if path.is_file() and rel.as_posix().startswith("uploads/") and path.name != ".gitkeep":
        violations.append(str(rel))

if violations:
    print("RELEASE CHECK FAILED")
    for item in sorted(set(violations))[:100]:
        print(" -", item)
    sys.exit(1)
print("RELEASE CHECK PASSED: no databases, uploaded user documents, logs, environments, caches, or Git internals found.")
