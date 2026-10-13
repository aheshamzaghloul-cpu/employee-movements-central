from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "employee_movements/static/css/pages/home.css").read_text(encoding="utf-8")
EMPLOYEES_CSS = (ROOT / "employee_movements/static/css/pages/employee-directory.css").read_text(encoding="utf-8")
VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()


def test_page_stylesheets_are_loaded_only_for_their_page_families():
    assert "request.path == '/'" in BASE
    assert "css/pages/home.css" in BASE
    assert "request.path == '/employees'" in BASE
    assert "css/pages/employee-directory.css" in BASE
    assert BASE.index("css/app.css") < BASE.index("css/pages/home.css") < BASE.index("css/pages/employee-directory.css")
    assert f"?v={VERSION}" in BASE


def test_home_redesign_preserves_business_workflow_hooks():
    for hook in (
        "homeMovementForm", "homeMovementType", "homeAssignmentGovernorate",
        "homeAssignmentBranch", "data-movement-action", "data-status-metric",
        "entry-role-inline-panel", "homeEmployeeSearchForm", "employee-search",
        "movement-register", "home-mission-print",
    ):
        assert hook in HOME or hook in HOME_SEARCH
    assert "ds-home-page" in HOME
    assert "ds-home-actions" in HOME
    assert "ds-home-monitor-grid" in HOME
    assert "ds-home-tools-grid" in HOME


def test_home_page_css_is_scoped_and_mobile_first_for_primary_workflows():
    assert ".ds-home-page" in HOME_CSS
    assert "@media (max-width: 820px)" in HOME_CSS
    assert "@media (max-width: 520px)" in HOME_CSS
    assert "@media (max-width: 360px)" in HOME_CSS
    assert ".ds-home-page [hidden] { display: none !important; }" in HOME_CSS
    assert "@media (prefers-reduced-motion: reduce)" in HOME_CSS


def test_directory_redesign_preserves_search_scope_and_action_hooks():
    for hook in (
        "data-employees-page", "employees_search_input", "employees-search-form",
        "employee_governorate_filter", "employee_branch_filter", "data-employee-row",
        "data-server-query", "employee-add",
    ):
        assert hook in EMPLOYEES
    assert "ds-directory-page" in EMPLOYEES
    assert "aria-live=\"polite\"" in EMPLOYEES


def test_changed_server_query_does_not_misrepresent_stale_rows_as_new_results():
    assert "matchesPrevious=normalize(r.dataset.search).includes(initialServerQuery)" in EMPLOYEES
    assert "النتائج الحالية تخص البحث السابق" in EMPLOYEES
    assert "تطبيق البحث الجديد" in EMPLOYEES


def test_employee_quick_add_anchor_opens_the_details_panel():
    assert "document.querySelectorAll('a[href=\"#employee-add\"]')" in EMPLOYEES
    assert "addPanel.open=true" in EMPLOYEES
    assert "window.location.hash==='#employee-add'" in EMPLOYEES


def test_directory_page_css_is_scoped_and_has_safe_narrow_layouts():
    assert ".ds-directory-page" in EMPLOYEES_CSS
    assert "@media (max-width: 780px)" in EMPLOYEES_CSS
    assert "@media (max-width: 560px)" in EMPLOYEES_CSS
    assert "@media (max-width: 350px)" in EMPLOYEES_CSS
    assert "grid-template-columns: minmax(0,1fr)" in EMPLOYEES_CSS
    assert "@media (prefers-reduced-motion: reduce)" in EMPLOYEES_CSS


def test_shared_and_page_stylesheets_keep_versioned_asset_urls_in_sync():
    assert BASE.count(f"v={VERSION}") == 13
    assert "68.23.0" not in BASE
    assert re.search(r"version\s*=\s*\"" + re.escape(VERSION) + r"\"", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
