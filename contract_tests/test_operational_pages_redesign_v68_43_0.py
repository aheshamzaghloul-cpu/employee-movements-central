from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
BRANCHES = (ROOT / "employee_movements/templates/branches.html").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
MISSION_TICKET = (ROOT / "employee_movements/templates/mission_from_screenshot.html").read_text(encoding="utf-8")
DIRECTORY_CSS = (ROOT / "employee_movements/static/css/pages/employee-directory.css").read_text(encoding="utf-8")
WORKSPACE_CSS = (ROOT / "employee_movements/static/css/pages/workspace-pages.css").read_text(encoding="utf-8")
MOVEMENT_CSS = (ROOT / "employee_movements/static/css/pages/movement-forms.css").read_text(encoding="utf-8")


def test_phase_two_release_metadata_and_asset_cache_keys_are_synchronized():
    assert (ROOT / "VERSION.md").read_text(encoding="utf-8").strip() == CURRENT_VERSION
    assert f'version = "{CURRENT_VERSION}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"__version__ = '{CURRENT_VERSION}'" in (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert 'data-app-version="{{app_version}}"' in BASE
    assert BASE.count("v=app_version") == 24


def test_branch_catalogue_uses_consistent_line_icons_not_decorative_text_glyphs():
    assert BRANCHES.count('class="catalog-kpi-icon') == 4
    assert BRANCHES.count('viewBox="0 0 24 24"') >= 6
    assert 'class="catalog-search"><span class="sr-only">بحث في الفروع</span><svg' in BRANCHES
    assert 'catalog-advanced-filters"><summary><svg' in BRANCHES
    assert 'class="catalog-record-symbol" aria-hidden="true"><svg' in BRANCHES
    assert ">▦</span>" not in BRANCHES
    assert ">⌕</span>" not in BRANCHES


def test_branch_catalogue_mobile_disclosures_have_in_flow_fallback():
    assert "@media(max-width:760px)" in WORKSPACE_CSS
    assert ".catalog-add-disclosure[open] .catalog-add-form { position:static" in WORKSPACE_CSS
    assert ".catalog-record-actions .catalog-inline-edit { position:static" in WORKSPACE_CSS


def test_employee_directory_keeps_search_and_scope_filters_and_uses_blue_focus():
    assert 'id="employees-search-form"' in EMPLOYEES
    assert 'name="governorate_id"' in EMPLOYEES
    assert 'name="branch_id"' in EMPLOYEES
    assert "rgba(20,124,173,.14)" in DIRECTORY_CSS
    assert "#268fca" in DIRECTORY_CSS
    assert 'data-expand-branches' in EMPLOYEES and 'data-collapse-branches' in EMPLOYEES


def test_movement_workflow_keeps_server_contract_and_uses_svg_selection_icons():
    assert 'id="movementCreateForm"' in MOVEMENTS
    assert 'action="/movements/create"' in MOVEMENTS
    assert 'name="movement_type"' in MOVEMENTS
    assert 'id="movementCreateEmployeeId"' in MOVEMENTS
    assert 'movement-branch-card-icon\\\" aria-hidden' in MOVEMENTS or 'movement-branch-card-icon\" aria-hidden' in MOVEMENTS
    assert 'movement-card-arrow\" aria-hidden' in MOVEMENTS
    assert "rgba(20,124,173,.18)" in MOVEMENT_CSS


def test_mission_from_screenshot_preserves_endpoints_fields_and_human_review():
    assert 'action="/missions/from-screenshot/scan"' in MISSION_TICKET
    assert 'action="/missions/from-screenshot/create"' in MISSION_TICKET
    for field in ("basic_branch_name", "destination_branch_id", "job_code", "destination_is_basic", "needs_mission", "from_date", "to_date"):
        assert f'name="{field}"' in MISSION_TICKET
    assert 'ticket-image-drop-icon" aria-hidden="true"><svg' in MISSION_TICKET
    assert 'ticket-image-privacy-icon' in MISSION_TICKET
    assert "لا يسجل التطبيق المأمورية بمجرد قراءة الصورة" in MISSION_TICKET


def test_no_legacy_green_tone_is_used_for_operational_brand_focus():
    assert "rgba(8,127,140" not in WORKSPACE_CSS
    assert "rgba(8,127,140" not in MOVEMENT_CSS
    assert "rgba(8,120,132" not in DIRECTORY_CSS
    assert "rgba(20,124,173,.15)" in DIRECTORY_CSS
