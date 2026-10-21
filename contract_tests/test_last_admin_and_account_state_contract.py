"""Source-only contract: never allow admin lockout or stale pending account work."""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_admin_removal_is_serialized_and_requires_a_recovery_account():
    source = (ROOT / "employee_movements" / "services" / "account_security.py").read_text(encoding="utf-8")
    assert ".with_for_update()" in source
    assert "def can_remove_admin_role" in source
    assert "return any(remaining.values())" in source
    assert "return bool(remaining)" in source


def test_admin_ui_guards_role_removal_deactivation_and_deletion():
    source = (ROOT / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    assert "not can_remove_admin_role(i)" in source
    assert "BLOCK_LAST_ADMIN_ROLE_CHANGE" in source
    assert "BLOCK_LAST_ADMIN_DEACTIVATION" in source
    assert "BLOCK_LAST_ADMIN_ACCOUNT_DELETE" in source


def test_assistant_role_revocation_uses_same_admin_guard():
    source = (ROOT / "employee_movements" / "assistant" / "manager_execution.py").read_text(encoding="utf-8")
    role_block = source.split("elif kind in ('role_grant','role_revoke'):", 1)[1]
    assert "role == 'مسؤول التطبيق' and not can_remove_admin_role(u.id)" in role_block
    assert "invalidate_user_workflows(u.id)" in role_block


def test_sensitive_account_transitions_invalidate_pending_assistant_state_and_ticket_drafts():
    source = (ROOT / "employee_movements" / "services" / "account_security.py").read_text(encoding="utf-8")
    assert "AssistantSessionState.query.filter_by(user_id=user_id).delete" in source
    assert "MissionTicketImageDraft.query.filter_by(uploaded_by=user_id).delete" in source
    users = (ROOT / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    assert "invalidate_user_workflows(i)" in users
    auth = (ROOT / "employee_movements" / "blueprints" / "auth.py").read_text(encoding="utf-8")
    assert "invalidate_user_workflows(u.id)" in auth
