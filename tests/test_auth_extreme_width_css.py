from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_extreme_auth_summary_css_is_mirrored_and_contained():
    app_css = (ROOT / "app/static/access-portal.css").read_text(encoding="utf-8")
    public_css = (ROOT / "public/static/access-portal.css").read_text(encoding="utf-8")

    assert app_css == public_css
    assert "@media(max-width:240px)" in app_css
    assert ".access-selection-summary{display:grid;grid-template-columns:10px minmax(0,1fr);align-items:start}" in app_css
    assert ".access-role-dot{display:block;width:10px;height:10px;min-width:10px;min-height:10px;overflow:hidden;font-size:0;line-height:0;color:transparent;margin-top:2px}" in app_css
    assert ".access-selection-summary>div>b,.access-selection-summary>div>span{display:block;min-width:0;overflow-wrap:break-word;word-break:normal}" in app_css
