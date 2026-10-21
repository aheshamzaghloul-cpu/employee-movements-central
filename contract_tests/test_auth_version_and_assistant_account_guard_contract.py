"""Source-only release guard for account session revocation and assistant parity.

These checks are intentionally not executed during the current static-only review.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_user_auth_version_is_migrated_and_checked_on_authenticated_requests():
    model = _source("employee_movements/models.py")
    bootstrap = _source("employee_movements/bootstrap.py")
    access = _source("employee_movements/access.py")
    auth = _source("employee_movements/blueprints/auth.py")
    invalidation = _source("employee_movements/services/account_security.py")

    assert "auth_version = db.Column(db.Integer" in model
    assert "'auth_version': 'INTEGER NOT NULL DEFAULT 0'" in bootstrap
    assert "session.get('auth_version', -1)" in access
    assert "session_auth_version != current_auth_version" in access
    assert "session['auth_version'] = int(user.auth_version or 0)" in auth
    assert "target.auth_version = int(target.auth_version or 0) + 1" in invalidation
    assert "session['auth_version'] = target.auth_version" in invalidation


def test_assistant_cannot_disable_the_last_active_application_administrator():
    execution = _source("employee_movements/assistant/manager_execution.py")

    assert "elif kind == 'user_toggle'" in execution
    assert "elif kind == 'user_delete'" in execution
    assert "not can_remove_admin_role(u.id)" in execution
    assert "invalidate_user_workflows(u.id)" in execution


def test_account_scope_and_organizational_replacement_invalidate_old_sessions():
    users = _source("employee_movements/blueprints/users.py")
    structure = _source("employee_movements/blueprints/structure.py")
    employees = _source("employee_movements/blueprints/employees.py")
    delegations = _source("employee_movements/blueprints/delegations.py")

    govs = users.split("def user_update_governorates", 1)[1].split("@bp.post", 1)[0]
    branches = users.split("def user_update_branches", 1)[1].split("@bp.post", 1)[0]
    assert "invalidate_user_workflows(i)" in govs
    assert "invalidate_user_workflows(i)" in branches
    assert "invalidate_user_workflows(old.id)" in structure
    assert "invalidate_user_workflows(new.id)" in structure
    assert "invalidate_user_workflows(linked_user.id)" in employees
    assert "invalidate_user_workflows(sup.id)" in delegations
    assert "invalidate_user_workflows(delegate.id)" in delegations
    assert "invalidate_user_workflows(d.supervisor_id)" in delegations
    assert "invalidate_user_workflows(d.delegate_id)" in delegations
