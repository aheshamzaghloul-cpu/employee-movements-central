from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"

def test_manager_gets_global_assignment_rows_but_scoped_leave_and_permission_rows():
    source = MOVEMENTS.read_text(encoding="utf-8")
    assert "global_assignment_actor = bool(rs & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'})" in source
    assert "elif rs & {'مشرف محافظة', 'Manager Application Support'}:" in source
    assert "Movement.movement_type == 'انتداب'" in source
    assert "Employee.branch_id.in_(bs)" in source

def test_manager_sees_global_governorate_filter_choices_for_missions():
    source = MOVEMENTS.read_text(encoding="utf-8")
    assert "roles() & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'}" in source
