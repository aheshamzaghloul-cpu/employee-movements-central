from pathlib import Path


def test_mission_lifecycle_mutations_rollback_on_any_error():
    source = (
        Path(__file__).parents[1]
        / "employee_movements"
        / "services"
        / "mission_lifecycle.py"
    ).read_text(encoding="utf-8")
    assert "def _rollback_on_error(operation):" in source
    assert "except Exception:" in source
    assert "db.session.rollback()" in source
    assert "raise" in source
    for operation in (
        "close_mission",
        "reopen_mission",
        "apply_mission_edit",
        "execute_edit_request",
    ):
        marker = f"def {operation}("
        start = source.index(marker)
        assert source.rfind("@_rollback_on_error", 0, start) > source.rfind("\n\ndef ", 0, start)
