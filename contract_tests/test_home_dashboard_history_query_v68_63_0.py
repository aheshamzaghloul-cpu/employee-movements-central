"""Guard homepage live-status queries against unbounded history hydration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_current_status_uses_database_ranking_for_one_row_per_employee():
    source = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    start = source.index("def current_employee_status_rows(")
    end = source.index("\n\n@bp.get('/')", start)
    section = source[start:end]

    assert "func.row_number().over(" in section
    assert "partition_by=Movement.employee_id" in section
    assert "Movement.employee_id.in_(employee_ids)" in section
    assert "ranked_movements.c.current_rank == 1" in section
    assert "Movement.query.filter(Movement.employee_id.in_(employee_ids), Movement.is_active == True)" not in section
    assert "by_employee.setdefault(movement.employee_id, []).append(movement)" not in section


def test_homepage_does_not_serialize_an_unused_full_employee_directory():
    source = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    assert "movement_search_employees=" not in source
    assert "Employee.query.filter_by(is_active=True)\n            .order_by(Employee.full_name.asc())\n            .all()" not in source


def test_effective_branch_employee_fetch_eager_loads_branch_relationships():
    source = (ROOT / "employee_movements" / "assignments.py").read_text(encoding="utf-8")
    start = source.index("def employees_effectively_in_branches(")
    end = source.index("\n\ndef supervisor_for_governorate", start)
    section = source[start:end]
    assert "joinedload(Employee.branch).joinedload(Branch.governorate)" in section
    assert "Movement.employee_id.in_(employee_ids)" not in section


def test_homepage_entry_assignment_loader_uses_two_batched_reads_not_a_query_per_assignment():
    source = (ROOT / "employee_movements" / "assignments.py").read_text(encoding="utf-8")
    start = source.index("def organizational_entries_for_supervisor(")
    end = source.index("\n\ndef organizational_entry_for_employee", start)
    section = source[start:end]
    assert "joinedload(EntryAssignment.employee)" in section
    assert "EntryAssignmentBranch.entry_assignment_id.in_(assignment_ids)" in section
    assert "EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).all()" not in section
    assert "Branch.query.filter(Branch.id.in_(branch_ids)" not in section
