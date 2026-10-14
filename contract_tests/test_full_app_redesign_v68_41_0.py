from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
DESIGN = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")

def test_current_release_is_bumped_atomically():
    assert (ROOT / "VERSION.md").read_text(encoding="utf-8").strip() == "68.45.0"
    assert 'version = "68.45.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "__version__ = '68.45.0'" in (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert BASE.count("v=68.45.0") == 18

def test_shared_design_layer_is_loaded_after_all_page_styles():
    assert BASE.index("css/design-system-cyan.css") > BASE.index("css/app.css")
    assert "--ui-brand: #147cad" in APP_CSS
    assert "--ui-brand-strong: #126c9b" in APP_CSS
    assert "v68.40.0 — premium minimal surfaces" not in DESIGN

def test_movements_has_own_permission_gated_navigation_item():
    assert 'href="/movements"' in BASE
    assert "can('manage_movements') and can_manage_movement()" in BASE
    assert 'aria-current="page"' in BASE

def test_layout_system_covers_key_page_families_and_small_screens():
    for selector in [".ui-page-head", ".ui-toolbar", ".ui-table-wrap", ".admin-workspace", ".users-workspace", ".movement-workspace", ".ds-home-page"]:
        assert selector in DESIGN
    assert "@media (max-width: 600px)" in DESIGN
    assert "prefers-reduced-motion: reduce" in DESIGN
    assert ".premium-main.with-shell > *" in DESIGN

def test_legacy_ux_tokens_resolve_to_the_sky_blue_theme():
    assert "--ui-accent: #147cad" in APP_CSS
    assert "--accent-strong: #126c9b" in APP_CSS
    assert "rgba(8,127,140" not in APP_CSS + DESIGN
    assert "--ui-sidebar-text: #405b72" in APP_CSS
