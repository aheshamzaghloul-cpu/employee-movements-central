"""Regression checks for cross-page JavaScript stability and compact page workflows."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
EXCEL = (ROOT / "employee_movements/templates/excel_import.html").read_text(encoding="utf-8")
STRUCTURE = (ROOT / "employee_movements/templates/structure.html").read_text(encoding="utf-8")


def test_retired_home_movement_wizard_script_is_removed_when_no_home_form_exists():
    movements = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
    assert "home-real-movement-form" not in APP_JS
    assert "home-movement-step-employee" not in APP_JS
    assert "hmSyncDynamic" not in APP_JS
    assert 'id="movementCreateForm"' in movements


def test_shell_intro_is_suppressed_when_page_has_its_own_heading():
    assert "{% set page_has_local_heading = (" in BASE
    condition = BASE[BASE.index("{% set page_has_local_heading = ("):BASE.index("<section class=\"premium-page-intro\"")]
    for prefix in ["/structure", "/employees", "/movements", "/reports", "/excel-import", "/users"]:
        assert f"request.path.startswith('{prefix}')" in condition
    assert "and not page_has_local_heading" in BASE


def test_excel_mapping_form_uses_responsive_grid_not_full_width_per_field():
    assert 'class="ui-grid wide excel-map-grid"' in EXCEL
    assert 'class="excel-map-field"' in EXCEL
    assert 'class="ui-grid-full"><b>{{label}}</b>' not in EXCEL
    assert ".ui-grid.wide.excel-map-grid { grid-template-columns: repeat(3, minmax(0, 1fr));" in CSS
    assert "@media (max-width: 1000px) { .ui-grid.wide.excel-map-grid" in CSS
    assert "@media (max-width: 600px) { .ui-grid.wide.excel-map-grid" in CSS


def test_optional_employee_columns_are_explicit_in_excel_mapping_ui():
    assert "excel-map-optional" in EXCEL
    assert "اختياري — يمكن تركه دون مطابقة" in EXCEL
    for field in ["email", "company_phone", "personal_phone", "branch_code"]:
        assert field in EXCEL


def test_admin_hero_mobile_flex_basis_cannot_create_artificial_vertical_space():
    assert ".admin-ai-hero-copy { flex:0 1 auto; width:100%; }" in CSS


def test_admin_command_shortcut_has_a_real_target():
    assert "href:'#admin-intelligence'" in (ROOT / "employee_movements/static/js/smart_ui.js").read_text(encoding="utf-8")
    assert 'id="admin-intelligence"' in STRUCTURE


def test_mobile_sidebar_css_has_one_authoritative_open_state_rule():
    shell = (ROOT / "employee_movements/static/js/shell.js").read_text(encoding="utf-8")
    assert "sidebar.classList.toggle('is-open',shouldOpen)" in shell
    assert CSS.count(".ui-sidebar.is-open,.ui-sidebar.open{transform:translateX(0)") == 1


def test_mobile_sidebar_uses_one_consolidated_responsive_rule():
    assert CSS.count(".ui-sidebar{transform:translateX(110%);transition:transform .2s ease;box-shadow:none}.ui-sidebar.is-open,.ui-sidebar.open{") == 1


def test_excel_import_workflow_buttons_use_the_shared_button_system():
    assert '<button type="submit" class="ui-btn ui-btn-primary">' in EXCEL
    assert 'class="ui-btn ui-btn-secondary" onclick="document.querySelectorAll' in EXCEL
    assert 'button type="submit">✅ اعتماد الإضافة والتحديثات المحددة' not in EXCEL
    assert '<div class="ui-form-actions ui-grid-full"><button>' not in EXCEL


def test_mobile_quick_action_bar_wraps_instead_of_clipping_items():
    assert ".ui-actionbar.premium-commandbar { flex-wrap: wrap; overflow: visible; }" in CSS
    assert "@media (max-width: 700px)" in CSS


def test_report_quick_filter_card_does_not_inherit_compact_launch_tile_grid():
    reports = (ROOT / "employee_movements/templates/reports.html").read_text(encoding="utf-8")
    assert 'class="ui-card ui-report-quick-filter-card"' in reports
    assert 'class="ui-card ui-report-launch-card"' not in reports
    assert ".ui-report-quick-filter-card > .ui-section-title > div:first-child { flex: 1 1 100%;" in CSS
