from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
COMPONENTS = (ROOT / "employee_movements/static/css/ui-components.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()


def test_shared_ui_component_stylesheet_loads_after_page_and_navigation_styles():
    assert "css/ui-components.css" in BASE
    assert BASE.index("css/ui-components.css") > BASE.index("css/navigation-color-system.css")
    assert "filename='css/ui-components.css', v=app_version" in BASE


def test_flash_alerts_have_an_explicit_accessible_dismiss_control():
    assert "data-dismiss-alert" in BASE
    assert 'aria-label="إغلاق الرسالة"' in BASE
    assert 'role="{% if alert_tone in ' in BASE
    assert "aria-live=" in BASE


def test_dismiss_control_removes_only_its_own_alert_and_moves_focus_predictably():
    assert "document.addEventListener('click'" in APP_JS
    assert "event.target.closest('[data-dismiss-alert]')" in APP_JS
    assert "alert.remove()" in APP_JS
    assert "remaining.focus({ preventScroll: true })" in APP_JS
    assert "main.focus({ preventScroll: true })" in APP_JS


def test_component_styles_unify_tables_forms_validation_and_semantic_alerts():
    for token in (".ui-table-wrap", "table.ui-mission-table", "form.ui-form", "[aria-invalid=\"true\"]", ".ui-alert-warning", ".ui-alert-success", ".ui-alert-error", ".ui-form-actions"):
        assert token in COMPONENTS


def test_responsive_print_and_reduced_motion_rules_are_present():
    assert "@media (max-width: 700px)" in COMPONENTS
    assert "@media (prefers-reduced-motion: reduce)" in COMPONENTS
    assert "@media print" in COMPONENTS
    assert ".enterprise-alert-dismiss" in COMPONENTS


def test_component_release_metadata_uses_the_current_version():
    assert VERSION.count(".") == 2
    assert f"v{VERSION}" in COMPONENTS.splitlines()[0]
