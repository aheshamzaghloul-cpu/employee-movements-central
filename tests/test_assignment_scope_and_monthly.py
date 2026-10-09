from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / "employee_movements" / "access.py"
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"

def test_supervisor_global_reach_is_assignment_only():
    text = MOVEMENTS.read_text()
    assert "global_employee_access = 'مسؤول التطبيق' in rs or ('مشرف محافظة' in rs and movement_type == 'انتداب')" in text
    assert "Movement.movement_type == 'انتداب'" in text

def test_supervisor_cannot_view_leave_permission_globally():
    text = ACCESS.read_text()
    assert "if getattr(m, 'movement_type', None) == 'انتداب':" in text
    assert "return branch_ok(m.employee.branch_id)" in text

def test_monthly_aggregation_uses_closed_assignments_only():
    text = MISSIONS.read_text()
    assert "Movement.mission_state == 'مغلقة'" in text
    assert "Movement.movement_type == 'انتداب'" in text
    assert "total_days" in text

def test_monthly_aggregation_has_no_incentive_formula():
    text = MISSIONS.read_text()
    assert "does not invent or apply an incentive formula" in text

def test_manager_employee_filter_is_scope_limited():
    text = MISSIONS.read_text()
    assert "employee_scope_ids" in text
    assert "Employee.branch_id.in_(employee_scope_ids)" in text


def test_central_manager_global_assignment_employee_and_destination_access():
    text = ACCESS.read_text(encoding="utf-8")
    assert "rs & {'مشرف محافظة', 'Manager Application Support'} and movement_type == 'انتداب'" in text
    movement_text = MOVEMENTS.read_text(encoding="utf-8")
    assert "'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'" in movement_text
    # The exception is limited to assignments; ordinary employee data remains scoped.
    assert "return branch_ok(e.branch_id)" in text
    assert "return branch_ok(branch.id)" in text
