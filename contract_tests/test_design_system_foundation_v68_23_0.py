from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "employee_movements" / "static" / "css" / "app.css"
VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (ROOT / "employee_movements" / "templates" / "base.html").read_text(encoding="utf-8")

def test_global_design_tokens_have_one_canonical_root():
    css = CSS.read_text(encoding="utf-8")
    # Standalone root rules only; responsive inline :root rules are intentional.
    assert len(re.findall(r"(?m)^:root\s*\{", css)) == 1

def test_design_scale_and_legacy_aliases_are_defined():
    css = CSS.read_text(encoding="utf-8")
    for token in ("--ui-space-1", "--ui-space-4", "--ui-type-base", "--ui-control-md", "--ui-border-strong", "--ui-brand", "--ui-brand-strong"):
        assert re.search(r"--" + re.escape(token[2:]) + r"\s*:", css)

def test_runtime_version_and_asset_cache_busters_match():
    init = (ROOT / "employee_movements" / "__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert VERSION in init and VERSION in pyproject
    assert "v=app_version" in BASE

def test_page_inventory_covers_all_template_files():
    inventory = ROOT / "docs" / "design" / "PAGE_INVENTORY_v68.23.0.json"
    assert inventory.exists()
    html_files = list((ROOT / "employee_movements" / "templates").rglob("*.html"))
    data = inventory.read_text(encoding="utf-8")
    for html in html_files:
        assert str(html.relative_to(ROOT)).replace("\\", "/") in data


def test_mission_print_shortcut_stacks_on_narrow_phones():
    css = CSS.read_text(encoding="utf-8")
    assert ".home-primary-actions > .home-mission-shortcut { grid-template-columns: minmax(0,1fr); align-items: stretch; gap: 10px; }" in css
    assert ".home-mission-shortcut > .ui-btn { grid-column: auto; width: 100%; white-space: normal; }" in css
