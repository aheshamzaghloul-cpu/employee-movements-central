"""Source-only release guards for assistant-manager account and scope plans.

These contracts are intentionally not executed during the static-only review round.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_user_create_revalidates_roles_email_and_governorate_scope_at_execution():
    source = _source("employee_movements/assistant/manager_execution.py")
    block = source.split("elif kind == 'user_create':", 1)[1].split("elif kind == 'user_toggle':", 1)[0]
    assert "not isinstance(raw_roles, list)" in block
    assert "role not in LOGIN_ROLES" in block
    assert "email.strip().lower()" in block
    assert "func.lower(func.trim(User.email)) == email" in block
    assert "يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة" in block
    assert "except IntegrityError:" in block
    assert "CUSTOM_PERMISSION_SET_MARKER" in block


def test_legacy_user_branch_plan_is_rejected_before_any_assignment_mutation():
    source = _source("employee_movements/assistant/manager_execution.py")
    block = source.split("elif kind == 'user_set_branches':", 1)[1].split("elif kind == 'user_password_reset':", 1)[0]
    assert "return False" in block
    assert "UserBranch.query.filter_by(user_id=u.id).delete()" not in block
    planner = _source("employee_movements/assistant/manager_plan_users.py")
    planner_block = planner.split("if intent == 'user_set_branches':", 1)[1].split("if intent == 'user_create':", 1)[0]
    assert "'error':" in planner_block
    assert "'plan':" not in planner_block


def test_user_edit_has_a_field_allowlist_and_keeps_linked_employee_in_sync():
    source = _source("employee_movements/assistant/manager_execution.py")
    block = source.split("elif kind == 'user_edit':", 1)[1].split("elif kind == 'movement_delete':", 1)[0]
    assert "allowed_fields = {'full_name', 'email', 'job_title', 'job_code'}" in block
    assert "set(updates).issubset(allowed_fields)" in block
    assert "alias_owner_conflict('employee_name'" in block
    assert "conflicting_employee_code(" in block
    assert "setattr(linked_employee, key, value)" in block
    assert "func.lower(func.trim(Employee.email)) == normalized_updates['email']" in block


def test_boolean_plan_values_are_not_truthiness_coerced_and_scope_cannot_be_cleared_accidentally():
    source = _source("employee_movements/assistant/manager_execution.py")
    assert "def _strict_plan_bool(plan, key):" in source
    assert "return value if type(value) is bool else None" in source
    block = source.split("elif kind == 'user_set_governorates':", 1)[1].split("elif kind == 'user_set_branches':", 1)[0]
    assert "if ids is None or not ids:" in block
    assert "if not isinstance(plan, dict):" in source


def test_manager_transaction_returns_clean_conflict_for_integrity_errors():
    source = _source("employee_movements/assistant/manager.py")
    assert "from sqlalchemy.exc import IntegrityError" in source
    block = source.split("def execute(plan):", 1)[1].split("def _execute(plan):", 1)[0]
    assert "except IntegrityError:" in block
    assert "db.session.rollback()" in block
    assert "لم يتم تثبيت أي تغيير" in block
