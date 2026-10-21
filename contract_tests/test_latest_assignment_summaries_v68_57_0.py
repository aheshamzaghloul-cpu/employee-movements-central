"""Regression contracts for fast, global latest-assignment summaries in employee search."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = (ROOT / "employee_movements" / "assignments.py").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements" / "blueprints" / "employees.py").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements" / "templates" / "home_global_search.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements" / "static" / "js" / "app.js").read_text(encoding="utf-8")


def test_latest_assignment_summary_uses_one_window_ranked_record_per_employee():
    assert "def latest_assignment_summaries(employee_ids):" in ASSIGNMENTS
    assert "func.row_number().over(" in ASSIGNMENTS
    assert "partition_by=Movement.employee_id" in ASSIGNMENTS
    assert "Movement.movement_type == 'انتداب'" in ASSIGNMENTS
    assert "ranked_assignments.c.row_rank == 1" in ASSIGNMENTS
    assert "joinedload(Movement.destination).joinedload(Branch.governorate)" in ASSIGNMENTS
    assert "'governorate': governorate_name" in ASSIGNMENTS
    assert "'state': state_text" in ASSIGNMENTS


def test_search_endpoint_returns_assignment_summary_without_loading_all_history_directly():
    block = EMPLOYEES[EMPLOYEES.index("def employee_search():"):EMPLOYEES.index("@bp.route('/employees'")]
    assert "latest_assignment_summaries({e.id for e in rows})" in block
    assert "'last_assignment': latest_by_employee.get(e.id, {}).get('text', '')" in block
    assert "'last_assignment_governorate': latest_by_employee.get(e.id, {}).get('governorate', '')" in block
    assert "Movement.query" not in block


def test_home_live_and_server_search_display_the_same_latest_assignment_summary():
    assert "latest_assignment_summaries({employee.id for employee in visible_search_employees})" in DASHBOARD
    assert "movement_employee_last.get(emp.id, {}).get('text', 'لا يوجد انتداب مسجل')" in HOME
    assert "movement_employee_last.get(movement_employee.id, {}).get('text', 'لا يوجد انتداب مسجل')" in HOME
    assert "e.last_assignment||'لا يوجد انتداب مسجل'" in APP_JS
    assert "آخر انتداب" in HOME
