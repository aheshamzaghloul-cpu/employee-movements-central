"""Source contracts for safe form retention and filter-aware empty states."""
from pathlib import Path
import importlib.util
import sys
from types import ModuleType
from unittest.mock import patch

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "employee_movements"

FORM_STATE = (APP / "form_state.py").read_text(encoding="utf-8")
EMPLOYEES_ROUTE = (APP / "blueprints/employees.py").read_text(encoding="utf-8")
MOVEMENTS_ROUTE = (APP / "blueprints/movements.py").read_text(encoding="utf-8")
USERS_ROUTE = (APP / "blueprints/users.py").read_text(encoding="utf-8")
DELEGATIONS_ROUTE = (APP / "blueprints/delegations.py").read_text(encoding="utf-8")
MISSIONS_ROUTE = (APP / "blueprints/missions.py").read_text(encoding="utf-8")
EMPLOYEES_TEMPLATE = (APP / "templates/employees.html").read_text(encoding="utf-8")
EMPLOYEE_EDIT_TEMPLATE = (APP / "templates/employee_edit.html").read_text(encoding="utf-8")
MOVEMENTS_TEMPLATE = (APP / "templates/movements.html").read_text(encoding="utf-8")
USERS_TEMPLATE = (APP / "templates/users.html").read_text(encoding="utf-8")
DELEGATIONS_TEMPLATE = (APP / "templates/delegations.html").read_text(encoding="utf-8")
MISSION_TEMPLATE = (APP / "templates/mission_reports.html").read_text(encoding="utf-8")
TICKET_TEMPLATE = (APP / "templates/mission_from_screenshot.html").read_text(encoding="utf-8")


def test_form_retention_is_request_local_bounded_and_excludes_sensitive_values():
    assert "from flask import request" in FORM_STATE
    assert "from flask import session" not in FORM_STATE
    assert "_MAX_FIELDS = 40" in FORM_STATE
    assert "_MAX_VALUES_PER_FIELD = 12" in FORM_STATE
    assert "_MAX_VALUE_LENGTH = 500" in FORM_STATE
    assert "_MAX_TOTAL_CHARACTERS = 3000" in FORM_STATE
    for sensitive in ("password", "csrf", "access_token", "refresh_token", "upload", "image_data"):
        assert f'"{sensitive}"' in FORM_STATE
    assert "client-side cookie" in FORM_STATE
    assert "def _is_sensitive_name(name: str) -> bool:" in FORM_STATE
    assert "parts & _SENSITIVE_TOKENS" in FORM_STATE
    assert "letters ``file``" in FORM_STATE


def test_sensitive_field_matching_avoids_rejecting_legitimate_profile_name():
    module_path = APP / "form_state.py"
    spec = importlib.util.spec_from_file_location("form_state_tokenizer_contract_target", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    fake_flask = ModuleType("flask")
    fake_flask.request = object()
    with patch.dict(sys.modules, {"flask": fake_flask}):
        spec.loader.exec_module(module)
    assert module._is_sensitive_name("password")
    assert module._is_sensitive_name("access_token")
    assert module._is_sensitive_name("csrf_token")
    assert module._is_sensitive_name("profile_image")
    assert not module._is_sensitive_name("profile")
    assert not module._is_sensitive_name("profile_name")

    class FakeForm:
        def __init__(self, values):
            self.values = values

        def keys(self):
            return self.values.keys()

        def getlist(self, key):
            value = self.values[key]
            return value if isinstance(value, list) else [value]

    sanitized = module._safe_values(FakeForm({
        "profile": "keep-this",
        "full_name": "موظف تجريبي",
        "password": "never-return",
        "_csrf": "never-return",
        "access_token": "never-return",
        "image_data": "never-return",
        "notes": "n" * 900,
        "roles": ["مشرف محافظة", "Manager Application Support"],
    }))
    assert sanitized["profile"] == "keep-this"
    assert sanitized["full_name"] == "موظف تجريبي"
    assert all(key not in sanitized for key in ("password", "_csrf", "access_token", "image_data"))
    assert len(sanitized["notes"]) == 500
    assert sanitized["roles"] == ["مشرف محافظة", "Manager Application Support"]


def test_employee_creation_and_edit_retain_correctable_values_without_session_drafts():
    assert "form_values = form_values_from_request(request.form) if request.method == 'POST' else {}" in EMPLOYEES_ROUTE
    assert "return redirect(url_for('employees.resigned_employees'))" in EMPLOYEES_ROUTE
    for field in ("governorate_id", "branch_id", "full_name", "job_code", "job_title", "email", "hire_date", "company_phone", "personal_phone"):
        assert f"form_values.get('{field}'" in EMPLOYEES_TEMPLATE
    assert "{% if form_values %}open{% endif %}" in EMPLOYEES_TEMPLATE
    assert "def retry_edit(message):" in EMPLOYEES_ROUTE
    assert "if not all([name, email, job_title, job_code, hire_date]):" in EMPLOYEES_ROUTE
    assert "phone fields optional" not in EMPLOYEES_ROUTE
    for field in ("full_name", "email", "job_title", "job_code", "hire_date", "governorate_id", "branch_id", "company_phone", "personal_phone"):
        assert f"form_values.get('{field}'" in EMPLOYEE_EDIT_TEMPLATE
    assert 'name="company_phone"' in EMPLOYEE_EDIT_TEMPLATE and 'هاتف الشركة <small>اختياري</small>' in EMPLOYEE_EDIT_TEMPLATE
    assert 'name="personal_phone"' in EMPLOYEE_EDIT_TEMPLATE and 'الهاتف الشخصي <small>اختياري</small>' in EMPLOYEE_EDIT_TEMPLATE
    assert "stash_form_draft" not in EMPLOYEES_ROUTE
    assert "pop_form_draft" not in EMPLOYEES_ROUTE


def test_movement_creation_releases_locks_and_renders_values_on_validation_failure():
    route = MOVEMENTS_ROUTE.split("def movement_create():", 1)[1].split("@bp.get('/movements')", 1)[0]
    assert "def reject_form(message):" in route
    assert "db.session.rollback()" in route
    assert "g._movement_form_values = form_values_from_request(request.form)" in route
    assert "return movements()" in route
    assert "movement_form_values.get('movement_type')" in MOVEMENTS_ROUTE
    assert "movement_form_values.get('employee_id','')" in MOVEMENTS_TEMPLATE
    for field in ("leave_type", "leave_from_date", "leave_to_date", "assignment_from_date", "assignment_to_date", "destination_branch_id", "permission_date"):
        assert f"movement_form_values.get('{field}'" in MOVEMENTS_TEMPLATE
    assert "movement_form_values.get('return_to')" in MOVEMENTS_ROUTE
    assert "draftDestinationBranchId" in MOVEMENTS_TEMPLATE
    assert "stash_form_draft" not in MOVEMENTS_ROUTE


def test_invalid_movement_filter_fails_closed_and_explains_empty_results():
    assert "invalid_type_filter = bool(raw_filters['movement_type'])" in MOVEMENTS_ROUTE
    assert "filter_error = invalid_numeric_filter or invalid_type_filter" in MOVEMENTS_ROUTE
    query = MOVEMENTS_ROUTE.split("def movement_log_query():", 1)[1].split("log_query = movement_log_query()", 1)[0]
    assert "if filter_error:" in query
    assert "return query.filter(Movement.id == -1)" in query
    assert "movement_filter_error=filter_error" in MOVEMENTS_ROUTE
    assert "إحدى قيم التصفية غير صالحة" in MOVEMENTS_TEMPLATE
    assert "لا توجد حركات تطابق الفلاتر الحالية" in MOVEMENTS_TEMPLATE
    assert "مسح الفلاتر" in MOVEMENTS_TEMPLATE


def test_employee_and_mission_empty_states_distinguish_filtered_empty_from_no_data():
    assert "role=\"status\"" in EMPLOYEES_TEMPLATE
    assert "لا توجد نتائج مطابقة" in EMPLOYEES_TEMPLATE
    assert "مسح الفلاتر والعودة إلى الدليل" in EMPLOYEES_TEMPLATE
    assert "has_mission_filters = selected_governorate" in MISSION_TEMPLATE
    assert "تعذر عرض نتائج هذه التصفية" in MISSION_TEMPLATE
    assert "لا توجد مأموريات تطابق الفلاتر الحالية" in MISSION_TEMPLATE
    assert "لا توجد مأموريات في نطاق العرض الحالي" in MISSION_TEMPLATE
    assert "مسح الفلاتر وعرض المأموريات المتاحة" in MISSION_TEMPLATE


def test_account_creation_retains_non_secret_inputs_and_selected_permissions():
    assert "g._user_form_values = form_values_from_request(request.form)" in USERS_ROUTE
    assert "def rerender_user_form():" in USERS_ROUTE
    for field in ("username", "full_name", "email", "job_title", "job_code"):
        assert f"form_values.get('{field}'" in USERS_TEMPLATE
    for field in ("roles", "governorates", "permissions"):
        assert f"selected_create_{field}" in USERS_TEMPLATE
    assert 'name="password"' in USERS_TEMPLATE
    assert "form_values.get('password'" not in USERS_TEMPLATE


def test_delegation_and_ticket_checkbox_values_survive_correctable_validation_errors():
    assert "g._delegation_form_values = form_values_from_request(request.form)" in DELEGATIONS_ROUTE
    assert "form_values=getattr(g, '_delegation_form_values', {})" in DELEGATIONS_ROUTE
    for field in ("supervisor_id", "delegate_id", "governorate_id", "starts_at", "ends_at"):
        assert f"form_values.get('{field}'" in DELEGATIONS_TEMPLATE
    for field in ("confirm_selected_employee_code_mismatch", "remember_job_code_alias", "remember_basic_branch_alias", "remember_branch_alias"):
        assert f"values.get('{field}') == 'yes'" in TICKET_TEMPLATE
    assert "image_draft_token" in MISSIONS_ROUTE


def test_edited_form_and_filter_templates_remain_parseable_jinja():
    env = Environment()
    for template in (
        EMPLOYEES_TEMPLATE,
        EMPLOYEE_EDIT_TEMPLATE,
        MOVEMENTS_TEMPLATE,
        USERS_TEMPLATE,
        DELEGATIONS_TEMPLATE,
        MISSION_TEMPLATE,
        TICKET_TEMPLATE,
    ):
        env.parse(template)
