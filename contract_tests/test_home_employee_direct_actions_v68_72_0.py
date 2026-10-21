"""Regression contracts for the homepage employee-to-movement workflow."""
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
ROUTES = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
DESIGN_CSS = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")


def test_selected_employee_exposes_only_scope_aware_direct_movement_actions():
    guard = "{% if can('manage_movements') and can_manage_movement() and movement_employee_in_scope %}"
    assert guard in HOME
    actions = HOME.split('class="smart-employee-quick-actions"', 1)[1].split('</section>', 1)[0]
    for movement_type, label in (("إجازة", "تسجيل إجازة"), ("انتداب", "تسجيل مأمورية"), ("إذن", "تسجيل إذن")):
        assert f"movement_type='{movement_type}'" in actions
        assert "employee_id=movement_employee.id" in actions
        assert label in actions
    assert "#movement-create" in actions
    assert "smart-employee-readonly-note" in HOME
    assert "اختر محافظة العمل المطابقة لهذا الموظف" in HOME


def test_movement_prefill_revalidates_employee_state_type_and_scope():
    route = ROUTES.split("# Homepage quick actions may open this page", 1)[1].split(
        "destination_branches =", 1
    )[0]
    assert "requested_employee_id.isdigit()" in route
    assert "requested_employee_id" in route and "initial_movement_type" in route
    assert "candidate.is_active" in route
    assert "candidate.branch.is_active" in route
    assert "candidate.branch.governorate.is_active" in route
    assert "can('manage_movements') or not can_manage_movement() or not can_manage_movement_employee(candidate, initial_movement_type)" in route
    assert "initial_employee_notice" in route
    assert "initial_employee_notice=initial_employee_notice" in ROUTES


def test_failed_prefill_is_explained_to_the_user_in_the_movement_form():
    assert "{% if initial_employee_notice %}" in MOVEMENTS
    assert 'class="ui-alert ui-alert-warning movement-prefill-notice"' in MOVEMENTS
    assert 'role="status" aria-live="polite"' in MOVEMENTS
    assert "movement-prefill-notice" in DESIGN_CSS


def test_retired_homepage_wizard_has_no_javascript_without_matching_markup():
    assert "home-real-movement-form" not in APP_JS
    assert "home-movement-step-employee" not in APP_JS
    assert "home-movement-review-grid" not in APP_JS
    assert "home-movement-wizard" not in APP_JS
    assert "movementCreateForm" not in APP_JS  # the actual wizard remains in movements.html
    assert "movementCreateForm" in MOVEMENTS


def test_workflow_templates_remain_valid_jinja():
    env = Environment()
    env.parse(HOME)
    env.parse(MOVEMENTS)
