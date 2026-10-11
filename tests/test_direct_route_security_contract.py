"""Static security contracts for direct movement routes and POST CSRF enforcement."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_movement_history_requires_audit_permission_and_record_scope():
    source = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    start = source.index("def movement_history(i):")
    end = source.find("\n@", start)
    body = source[start:end if end != -1 else None]
    assert "not can('view_audit')" in body
    assert "not can_view_movement(m)" in body


def test_global_csrf_hook_rejects_missing_or_invalid_post_tokens():
    source = (ROOT / "employee_movements/hooks.py").read_text(encoding="utf-8")
    start = source.index("def csrf_check():")
    end = source.index("\ndef register_hooks", start)
    body = source[start:end]
    assert "request.method != 'POST'" in body
    assert "hmac.compare_digest(token, expected)" in body
    assert "abort(400, 'CSRF token invalid')" in body


def test_user_scope_assignment_validates_before_deleting_current_assignments():
    source = (ROOT / "employee_movements/blueprints/users.py").read_text(encoding="utf-8")
    for function, delete_marker, validation_marker in (
        ("def user_update_governorates(i):", "UserGovernorate.query.filter_by(user_id=i).delete()", "if not chosen.issubset(allowed):"),
        ("def user_update_branches(i):", "UserBranch.query.filter_by(user_id=i).delete()", "if not submitted.issubset(allowed):"),
    ):
        start = source.index(function)
        end = source.find("\n@", start)
        body = source[start:end if end != -1 else None]
        assert validation_marker in body
        assert body.index(validation_marker) < body.index(delete_marker)
