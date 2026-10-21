from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_assistant_history_isolated_by_active_role_and_old_schema_is_migrated():
    models = (ROOT / "employee_movements" / "models.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "employee_movements" / "bootstrap.py").read_text(encoding="utf-8")
    routes = (ROOT / "employee_movements" / "assistant" / "routes.py").read_text(encoding="utf-8")
    session_state = (ROOT / "employee_movements" / "assistant" / "session_state.py").read_text(encoding="utf-8")

    assert "active_role = db.Column(db.String(80), nullable=True)" in models
    assert "ix_assistant_message_user_role_created" in models
    assert "'assistant_message': {\n        'active_role': 'VARCHAR(80)'," in bootstrap
    assert "ix_assistant_message_user_role_created" in bootstrap
    assert "filter_by(user_id=user.id, active_role=history_role)" in routes
    assert "active_role=_assistant_history_role()" in routes
    assert "roles(user)" in session_state


def test_assistant_read_directory_uses_global_read_permission_not_work_write_scope():
    source = (ROOT / "employee_movements" / "assistant" / "directory.py").read_text(encoding="utf-8")
    assert "from ..access import bids, can, me, readable_branch_ids" in source
    assert "def _lookup_branch_ids():" in source
    assert "Employee.branch_id.in_(allowed_branches) if allowed_branches else False" in source
    assert source.count("if can('view_reports'):") >= 1
    assert "Branch.id.in_(allowed)" in source
    assert "Employee.is_active == True" in source
    assert "'مسؤول التطبيق' in rs or 'مشرف محافظة' in rs" not in source
