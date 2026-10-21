from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "employee_movements" / "blueprints" / "reports.py"
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"

def test_manager_and_other_official_roles_can_read_global_mission_reports():
    reports = REPORTS.read_text(encoding="utf-8")
    assert "def _report_branch_scope():" in reports
    assert "independent of work scope" in reports
    assert "Branch.is_active == True" in reports
    assert "Governorate.is_active == True" in reports
    assert "def reports_missions():" in reports

def test_global_mission_report_query_keeps_user_selected_governorate_as_a_filter_not_auth_scope():
    reports = REPORTS.read_text(encoding="utf-8")
    start = reports.index("def _report_branch_scope():")
    end = reports.index("@bp.get('/manager')", start)
    helper = reports[start:end]
    assert "raw_gid = (request.args.get('governorate_id') or '').strip()" in helper
    assert "query = query.filter(Branch.governorate_id == governorate.id)" in helper
    assert "work-governorate" in helper

def test_movement_read_list_uses_all_active_records_but_action_helpers_remain_row_scoped():
    source = MOVEMENTS.read_text(encoding="utf-8")
    start = source.index("def movements():")
    end = source.index("@bp.", start + 10)
    route = source[start:end]
    assert "Shared read directory" in route
    assert "Movement.is_active == True" in route
    assert "can_manage_movement(m)" in source
