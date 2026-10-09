from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'employee_movements' / 'blueprints' / 'reports.py'
HUB = ROOT / 'employee_movements' / 'templates' / 'manager_hub.html'


def test_manager_mission_reports_aggregate_globally_or_by_requested_governorate():
    source = REPORTS.read_text(encoding='utf-8')
    assert "is_central_manager = bool({'مسؤول التطبيق', 'Manager Application Support'} & rs)" in source
    assert "active_branches = Branch.query.filter_by(is_active=True)" in source
    assert "active_branches = active_branches.filter(Branch.governorate_id == int(requested_gid))" in source
    assert "manager_global_report=is_central_manager and not requested_gid.isdigit()" in source


def test_governorate_report_link_is_supported_and_does_not_expand_supervisor_scope():
    source = REPORTS.read_text(encoding='utf-8')
    hub = HUB.read_text(encoding='utf-8')
    assert 'href="/reports-missions?governorate_id={{ row.governorate.id }}"' in hub
    assert 'Never let a query parameter expand a supervisor\'s permissions.' in source
    assert 'bs &= requested_branch_ids' in source


def test_central_manager_is_global_in_mission_report_queries_and_exports():
    mission_query = (ROOT / 'employee_movements' / 'services' / 'mission_query.py').read_text(encoding='utf-8')
    missions = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
    access = (ROOT / 'employee_movements' / 'access.py').read_text(encoding='utf-8')
    assert "'Manager Application Support'" in mission_query
    assert "'Manager Application Support'" in missions[missions.index("def mission_export_xlsx"):missions.index("def mission_monthly_aggregation")]
    assert "Central Manager may manage assignments across all governorates" in access
    assert "Leave and permission editing remains work-scope-bound" in access
    assert "central operational lead above all governorate supervisors" in access
