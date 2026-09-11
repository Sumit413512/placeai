from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTERPRISE_PATH = ROOT / "app/routers/enterprise.py"
HARDENING_PATH = ROOT / "app/routers/hardening2.py"
REPORT_PATH = ROOT / "app/routers/report_export_safe.py"
APP_PATH = ROOT / "app/app.py"


def parse(text: str) -> ast.Module:
    return ast.parse(text)


def node_start(node: ast.AST) -> int:
    starts = [getattr(node, "lineno")]
    starts.extend(getattr(dec, "lineno") for dec in getattr(node, "decorator_list", []))
    return min(starts)


def node_block(text: str, node: ast.AST) -> str:
    lines = text.splitlines(keepends=True)
    return "".join(lines[node_start(node) - 1 : getattr(node, "end_lineno")])


def find_function(text: str, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in parse(text).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise RuntimeError(f"Function {name!r} not found")


def find_assignment(text: str, name: str) -> ast.Assign:
    for node in parse(text).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node
    raise RuntimeError(f"Assignment {name!r} not found")


def replace_function(text: str, name: str, replacement: str) -> str:
    node = find_function(text, name)
    lines = text.splitlines(keepends=True)
    start = node_start(node) - 1
    end = getattr(node, "end_lineno")
    return "".join(lines[:start]) + replacement.rstrip() + "\n\n" + "".join(lines[end:]).lstrip("\n")


def rename_function(block: str, old_name: str, new_name: str) -> str:
    block, count = re.subn(
        rf"(^\s*(?:async\s+)?def\s+){re.escape(old_name)}(\s*\()",
        rf"\1{new_name}\2",
        block,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise RuntimeError(f"Could not rename {old_name} -> {new_name}")
    return block


def strip_enterprise_prefix_from_decorators(block: str) -> str:
    result = []
    for line in block.splitlines(keepends=True):
        if line.lstrip().startswith("@router."):
            line = line.replace('("/enterprise/', '("/', 1)
        result.append(line)
    return "".join(result)


def insert_after(text: str, marker: str, payload: str) -> str:
    if marker not in text:
        raise RuntimeError(f"Insertion marker not found: {marker!r}")
    return text.replace(marker, marker + "\n\n" + payload.rstrip() + "\n", 1)


enterprise = ENTERPRISE_PATH.read_text(encoding="utf-8")
hardening = HARDENING_PATH.read_text(encoding="utf-8")
report = REPORT_PATH.read_text(encoding="utf-8")

# The canonical enterprise router needs delete_file for replacement-safe uploads.
old_storage_import = (
    "from app.storage import file_download_response, save_file, safe_upload_filename, validate_upload_signature"
)
new_storage_import = (
    "from app.storage import delete_file, file_download_response, save_file, safe_upload_filename, validate_upload_signature"
)
if old_storage_import not in enterprise:
    raise RuntimeError("Expected enterprise storage import not found")
enterprise = enterprise.replace(old_storage_import, new_storage_import, 1)

# Bring the hardened helper invariants into the canonical enterprise owner.
assignment_names = [
    "PLACED_OFFER_STATUSES",
    "VALID_OFFER_STATUSES",
    "STUDENT_OFFER_DECISIONS",
    "OPERATOR_OFFER_STATUSES",
]
helper_names = [
    "_utc_naive_now",
    "_utc_naive",
    "_announcement_active",
    "_announcement_state",
    "_announcement_payload",
    "_ensure_announcement_notification",
    "_drive_for_institution",
    "_pipeline_payload",
    "_recalculate_student_placement_status",
]
hardened_helpers = [node_block(hardening, find_assignment(hardening, name)) for name in assignment_names]
hardened_helpers.extend(node_block(hardening, find_function(hardening, name)) for name in helper_names)
router_marker = 'router = APIRouter(prefix="/enterprise", tags=["Enterprise Placement Operations"])\n'
enterprise = insert_after(enterprise, router_marker, "\n".join(block.rstrip() for block in hardened_helpers))

# Replace retired enterprise implementations with their already-tested hardened equivalents.
handler_map = {
    "list_announcements": "hardened_list_announcements",
    "create_announcement": "hardened_create_announcement",
    "install_default_pipeline": "hardened_install_default_pipeline",
    "add_pipeline_stage": "hardened_add_pipeline_stage",
    "update_offer": "hardened_update_offer",
    "upload_authorization_letter": "hardened_upload_authorization_letter",
    "upload_offer_letter": "hardened_upload_offer_letter",
    "download_offer_letter": "hardened_download_offer_letter",
}
for canonical_name, hardened_name in handler_map.items():
    replacement = node_block(hardening, find_function(hardening, hardened_name))
    replacement = rename_function(replacement, hardened_name, canonical_name)
    replacement = strip_enterprise_prefix_from_decorators(replacement)
    enterprise = replace_function(enterprise, canonical_name, replacement)

# Fold safe, institution-scoped report generation into the canonical enterprise router.
report_assignments = ["_DANGEROUS_FORMULA_PREFIXES", "_LEADING_CONTROL_CHARS"]
report_helpers = ["spreadsheet_safe_cell", "_safe_rows", "_institution_report_rows"]
report_payload = [node_block(report, find_assignment(report, name)) for name in report_assignments]
report_payload.extend(node_block(report, find_function(report, name)) for name in report_helpers)
report_marker = "# -----------------------------------------------------------------------------\n# Priority 20: Institution reports (CSV/XLSX/PDF)\n# -----------------------------------------------------------------------------\n"
if report_marker not in enterprise:
    raise RuntimeError("Report insertion marker missing")
enterprise = enterprise.replace(
    report_marker,
    "\n".join(block.rstrip() for block in report_payload) + "\n\n\n" + report_marker,
    1,
)
report_handler = node_block(report, find_function(report, "export_report_safe"))
report_handler = rename_function(report_handler, "export_report_safe", "export_report")
enterprise = replace_function(enterprise, "export_report", report_handler)

ENTERPRISE_PATH.write_text(enterprise, encoding="utf-8")

# App bootstrap no longer imports shadow routers or filters canonical enterprise paths at runtime.
app_source = APP_PATH.read_text(encoding="utf-8")
for line in (
    'report_export_safe = _import_router("report_export_safe")\n',
    'hardening2 = _import_router("hardening2")\n',
):
    if line not in app_source:
        raise RuntimeError(f"Expected bootstrap import missing: {line.strip()}")
    app_source = app_source.replace(line, "", 1)

block_start = app_source.find("\n\nif enterprise is not None:\n")
block_end = app_source.find("\nfor module in (\n", block_start)
if block_start == -1 or block_end == -1:
    raise RuntimeError("Enterprise bootstrap shadow-filter block not found")
app_source = app_source[:block_start] + "\n\n" + app_source[block_end:]
for entry in ("    report_export_safe,\n", "    hardening2,\n"):
    if entry not in app_source:
        raise RuntimeError(f"Expected router tuple entry missing: {entry.strip()}")
    app_source = app_source.replace(entry, "", 1)
APP_PATH.write_text(app_source, encoding="utf-8")

# Point static/source-integrity tests to the canonical owner and add duplicate-route regressions.
report_test = ROOT / "tests/test_report_export_security.py"
text = report_test.read_text(encoding="utf-8")
old = "from app.routers.report_export_safe import spreadsheet_safe_cell"
new = "from app.routers.enterprise import spreadsheet_safe_cell"
if old not in text:
    raise RuntimeError("Report security test import reference not found")
report_test.write_text(text.replace(old, new, 1), encoding="utf-8")

offer_test = ROOT / "tests/test_offer_authority.py"
text = offer_test.read_text(encoding="utf-8")
old = 'source = (ROOT / "app/routers/hardening2.py").read_text(encoding="utf-8")'
new = 'source = (ROOT / "app/routers/enterprise.py").read_text(encoding="utf-8")'
if old not in text:
    raise RuntimeError("Offer authority source reference not found")
offer_test.write_text(text.replace(old, new, 1), encoding="utf-8")

ownership_test = ROOT / "tests/test_router_ownership.py"
text = ownership_test.read_text(encoding="utf-8")
first_anchor = '    assert not Path("app/routers/hardening.py").exists()\n'
if first_anchor not in text:
    raise RuntimeError("Router ownership test anchor missing")
first_extra = (
    '    assert "_retired_enterprise_route" not in source\n'
    '    assert \'report_export_safe = _import_router("report_export_safe")\' not in source\n'
    '    assert \'hardening2 = _import_router("hardening2")\' not in source\n'
    '    assert not Path("app/routers/report_export_safe.py").exists()\n'
    '    assert not Path("app/routers/hardening2.py").exists()\n'
)
text = text.replace(first_anchor, first_anchor + first_extra, 1)
text += '''\n\ndef test_enterprise_paths_have_single_canonical_owner():\n    expected = [\n        ("/enterprise/announcements", "GET"),\n        ("/enterprise/announcements", "POST"),\n        ("/enterprise/drives/{drive_id}/pipeline/default", "POST"),\n        ("/enterprise/drives/{drive_id}/pipeline", "POST"),\n        ("/enterprise/offers/{offer_id}", "PATCH"),\n        ("/enterprise/company-verification/authorization-letter", "POST"),\n        ("/enterprise/offers/{offer_id}/letter", "POST"),\n        ("/enterprise/offers/{offer_id}/letter", "GET"),\n        ("/enterprise/reports/{kind}.{fmt}", "GET"),\n    ]\n    for path, method in expected:\n        matches = [\n            route\n            for route in app.routes\n            if getattr(route, "path", None) == path\n            and method in (getattr(route, "methods", set()) or set())\n        ]\n        assert len(matches) == 1, (path, method, [getattr(route, "name", None) for route in matches])\n\n    schema = app.openapi()["paths"]\n    assert "update_offer" in schema["/enterprise/offers/{offer_id}"]["patch"]["operationId"]\n    assert "export_report" in schema["/enterprise/reports/{kind}.{fmt}"]["get"]["operationId"]\n'''
ownership_test.write_text(text, encoding="utf-8")

# The shadow-router modules are now obsolete by construction.
HARDENING_PATH.unlink()
REPORT_PATH.unlink()

# Basic source-level invariants before the full CI suite takes over.
ast.parse(ENTERPRISE_PATH.read_text(encoding="utf-8"))
ast.parse(APP_PATH.read_text(encoding="utf-8"))
assert "_retired_enterprise_route" not in APP_PATH.read_text(encoding="utf-8")
assert not HARDENING_PATH.exists()
assert not REPORT_PATH.exists()
print("Canonical enterprise route consolidation completed")
