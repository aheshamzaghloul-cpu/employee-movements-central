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


def test_mission_report_branch_filters_exclude_inactive_governorates():
    """Branch filter options must not expose active branches under inactive governorates."""
    text = (ROOT / "employee_movements" / "services" / "mission_query.py").read_text(encoding="utf-8")
    assert "active_branch_query = (" in text
    assert "Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)" in text
    assert "Branch.is_active == True, Governorate.is_active == True" in text
    assert "active_branch_query.filter(Branch.id.in_(allowed_bids))" in text


def test_global_mission_report_filters_are_independent_of_work_governorate():
    """Global mission browsing must keep cross-governorate filters for authorized roles."""
    text = (ROOT / "employee_movements" / "services" / "mission_query.py").read_text(encoding="utf-8")
    assert "global_actor = bool({'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'} & set(roles))" in text
    assert "Movement.movement_type == 'انتداب'" in text
    assert "destination_governorate_id" in text
    assert "destination_branch_id" in text


def test_manager_assignment_picker_is_global_but_not_for_leave_permission():
    """Manager Support needs the same cross-governorate assignment picker."""
    text = MOVEMENTS.read_text(encoding="utf-8")
    assert "bool(rs & {'مشرف محافظة', 'Manager Application Support'}) and movement_type == 'انتداب'" in text
    assert "Branch.is_active == True, Governorate.is_active == True" in text

