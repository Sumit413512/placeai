from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CSS_PATHS = (
    ROOT / "app/static/ui-fixes.css",
    ROOT / "public/static/ui-fixes.css",
)


def test_mirrored_ui_fix_css_is_synchronized():
    css_copies = [path.read_text(encoding="utf-8") for path in CSS_PATHS]
    assert css_copies[0] == css_copies[1]

    rules = re.findall(
        r"(?P<selector>[^{}]*\.auth-inline-cancel[^{}]*)\{(?P<body>[^{}]*)\}",
        css_copies[0],
        flags=re.DOTALL,
    )
    assert rules
    rule_body = "\n".join(match[1] for match in rules)

    assert re.search(r"\bposition\s*:\s*static\s*;", rule_body)
    assert not re.search(r"\bposition\s*:\s*sticky\s*;", rule_body)
    assert not re.search(r"\bz-index\s*:", rule_body)
    assert not re.search(r"\bbottom\s*:", rule_body)

