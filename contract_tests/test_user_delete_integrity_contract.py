from pathlib import Path


def test_user_delete_preserves_linked_business_history():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    start = source.index("def user_delete(i):")
    end = source.index("@bp.post('/users/<int:i>/toggle')", start)
    block = source[start:end]
    for required in (
        "has_movement_history",
        "has_employee_record",
        "has_entry_assignments",
        "has_delegations",
        "has_mission_requests",
        "ApprovalDelegation",
        "MissionEditRequest",
        "Employee.query.filter_by(user_id=i)",
        "EntryAssignment.query.filter_by(supervisor_id=i)",
        "استخدم التعطيل للحفاظ على الترابط وسجل التدقيق",
    ):
        assert required in block
