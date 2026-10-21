"""Regression contracts for the homepage and employee-directory visual pass."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
POLISH = (ROOT / "employee_movements/static/css/pages/home-directory-polish.css").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")


def test_scoped_stylesheet_is_conditionally_loaded_after_canonical_design_tokens():
    assert "request.path == '/' or request.path == '/employees'" in BASE
    assert BASE.index("css/design-system-cyan.css") < BASE.index("css/pages/home-directory-polish.css")
    assert BASE.index("css/pages/home-directory-polish.css") < BASE.index("css/pages/home-journey.css")
    assert BASE.count("v=app_version") == 24


def test_visual_rules_are_scoped_to_home_and_employee_directory_only():
    assert 'body[data-workspace-path="/"] .ds-home-page' in POLISH
    assert 'body[data-workspace-path="/employees"] .ds-directory-page' in POLISH
    assert "body:not(" not in POLISH
    assert "body[data-page=\"movements\"]" not in POLISH


def test_home_visual_polish_retains_global_search_and_workflow_cards():
    assert "homeEmployeeSearchForm" in HOME_SEARCH
    assert "ds-home-flow-search" in HOME
    assert "ds-home-flow-ticket" in HOME
    assert "ds-home-flow-manual" in HOME
    assert "smart-search-filters" in POLISH
    assert "homeEmployeeSearchForm" in HOME_SEARCH
    assert "ds-home-quick-action" in POLISH


def test_directory_visual_polish_retains_governorate_and_branch_search_filters():
    assert 'id="employee_governorate_filter"' in EMPLOYEES
    assert 'id="employee_branch_filter"' in EMPLOYEES
    assert "data-directory-branch" in EMPLOYEES
    assert "smart-employee-search-form" in POLISH
    assert "smart-directory-branch" in POLISH


def test_visual_pass_includes_narrow_layout_focus_and_reduced_motion_rules():
    for width in ("1120px", "780px", "560px", "360px"):
        assert width in POLISH
    assert ":focus-visible" in POLISH
    assert "prefers-reduced-motion: reduce" in POLISH
    assert "overflow-wrap: anywhere" in POLISH


def test_sidebar_and_role_scope_remain_in_base_template():
    assert 'id="appSidebar"' in BASE
    assert "can('manage_movements')" in BASE
    assert "scope_selected" in BASE
    assert "switch-role" in BASE


def test_version_is_synchronized_across_package_and_python_app():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    init = (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"__version__ = '{version}'" in init
    assert f'version = "{version}"' in pyproject
