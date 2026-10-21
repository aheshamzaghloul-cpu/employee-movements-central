"""Regression contracts for safe employee-to-movement navigation."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
NAVIGATION_PATH = ROOT / "employee_movements/navigation.py"
spec = spec_from_file_location("employee_movements_navigation_test_target", NAVIGATION_PATH)
navigation = module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(navigation)
safe_local_return_to = navigation.safe_local_return_to

EMPLOYEE = (ROOT / "employee_movements/templates/employee.html").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
MOVEMENT_EDIT = (ROOT / "employee_movements/templates/movement_edit.html").read_text(encoding="utf-8")
ROUTES = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
UI_CSS = (ROOT / "employee_movements/static/css/ui-components.css").read_text(encoding="utf-8")


def test_return_to_allows_same_origin_paths_with_query_and_fragment():
    path = "/employee/42?tab=history#movement-history"
    assert safe_local_return_to(path, "/fallback") == path


def test_return_to_rejects_external_protocol_relative_and_backslash_targets():
    for value in ("https://example.invalid/", "//example.invalid/x", r"/\\example.invalid", "/%2f%2fexample.invalid"):
        assert safe_local_return_to(value, "/safe") == "/safe"


def test_return_to_rejects_blank_malformed_and_control_character_targets():
    for value in (None, "", "   ", "/employee/1\r\nLocation: https://example.invalid", "/path\x00x"):
        assert safe_local_return_to(value, "/safe") == "/safe"


def test_employee_profile_offers_explicit_movement_type_choices():
    assert 'data-employee-movement-menu' in EMPLOYEE
    assert 'aria-label="اختيار نوع الحركة للتسجيل"' in EMPLOYEE
    for movement_type, label in (("إجازة", "تسجيل إجازة"), ("انتداب", "تسجيل مأمورية"), ("إذن", "تسجيل إذن")):
        assert f"movement_type='{movement_type}'" in EMPLOYEE
        assert label in EMPLOYEE
        assert "employee_id=e.id" in EMPLOYEE
    assert "return_to=url_for('employees.employee_card', i=e.id, _anchor='movement-history')" in EMPLOYEE
    assert "movements.movement_edit', i=m.id, return_to=url_for('employees.employee_card'" in EMPLOYEE
    assert 'href="/movements?employee_id={{e.id}}"' not in EMPLOYEE
    assert 'href="/movements?employee_id={{e.id}}"' not in EMPLOYEE.split('smart-employee-side', 1)[1]


def test_employee_profile_shortcuts_remain_in_the_authorized_work_scope():
    assert "can('manage_movements') and branch_ok(e.branch_id)" in EMPLOYEE
    assert "not e.deleted_at and e.is_active" in EMPLOYEE


def test_movement_form_uses_sanitized_return_target_from_get_request():
    assert "movement_return_to = safe_local_return_to(" in ROUTES
    assert "movement_return_to=movement_return_to" in ROUTES
    assert '<input type="hidden" name="return_to" value="{{ movement_return_to }}">' in MOVEMENTS


def test_validation_errors_rerender_prefilled_form_and_success_keeps_return_target():
    create_route = ROUTES.split("def movement_create():", 1)[1].split("@bp.get('/movements')", 1)[0]
    assert "return_to = safe_local_return_to(request.form.get('return_to')" in create_route
    assert "def reject_form(message):" in create_route
    assert "db.session.rollback()" in create_route
    assert create_route.count("return reject_form(") >= 4
    assert "return redirect(return_to)" in create_route  # success returns to the originating workflow
    assert "def _render_movement_edit_form(m, form_values=None, return_to=None)" in ROUTES
    assert "movement_return_to=safe_local_return_to(return_to, '/movements#movement-current')" in ROUTES
    assert '<input type="hidden" name="return_to" value="{{ movement_return_to }}">' in MOVEMENT_EDIT


def test_home_manual_mission_action_preserves_search_context_on_success():
    assert "return_to=url_for('dashboard.home'" in HOME
    assert "movement_name=movement_name_query or None" in HOME
    assert "movement_governorate_id=search_gov_id or None" in HOME
    assert "movement_branch_id=search_branch_id or None" in HOME
    assert "employee_id=movement_employee.id if movement_employee else None" in HOME


def test_editing_from_employee_profile_returns_to_the_same_history_context():
    edit_route = ROUTES.split("def movement_edit(i):", 1)[1].split("@bp.post('/movements/<int:i>/submit')", 1)[0]
    assert "safe_local_return_to(request.values.get('return_to'), '/movements#movement-current')" in edit_route
    assert "return _render_movement_edit_form(m, f.to_dict(), return_to)" in edit_route
    assert "return redirect(return_to)" in edit_route
    assert 'name="return_to" value="{{ movement_return_to }}"' in MOVEMENT_EDIT


def test_profile_action_menu_closes_on_escape_and_outside_click():
    assert "const openSelector = '[data-employee-movement-menu][open]'" in APP_JS
    assert "document.querySelectorAll(openSelector)" in APP_JS
    assert "event.key !== 'Escape'" in APP_JS
    assert "summary.focus({ preventScroll: true })" in APP_JS
    assert "event.target.closest('.smart-employee-register-options a')" in APP_JS


def test_profile_action_menu_has_responsive_and_keyboard_focus_styles():
    assert ".smart-employee-register-menu" in UI_CSS
    assert ".smart-employee-register-options a:focus-visible" in UI_CSS
    assert "@media(max-width:760px)" in UI_CSS
    assert "@media(prefers-reduced-motion:reduce)" in UI_CSS


def test_cross_page_templates_remain_parseable_jinja():
    env = Environment()
    env.parse(EMPLOYEE)
    env.parse(HOME)
    env.parse(MOVEMENTS)
