from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / 'employee_movements' / 'blueprints' / 'reports.py'
HUB = ROOT / 'employee_movements' / 'templates' / 'manager_hub.html'


def test_manager_mission_reports_aggregate_globally_or_by_requested_governorate():
    source = REPORTS.read_text(encoding='utf-8')
    assert "central = bool({'مسؤول التطبيق', 'Manager Application Support'} & rs)" in source
    assert "branch_query = Branch.query.filter_by(is_active=True)" in source
    assert "branch_query = branch_query.filter(Branch.governorate_id == governorate.id)" in source
    assert "manager_global_report=is_central_manager and not requested_gid.isdigit()" in source


def test_governorate_report_link_is_supported_and_does_not_expand_supervisor_scope():
    source = REPORTS.read_text(encoding='utf-8')
    hub = HUB.read_text(encoding='utf-8')
    assert 'href="/reports-missions?governorate_id={{ row.governorate.id }}"' in hub
    assert 'Never let a query parameter expand permissions.' in source or 'without letting query parameters expand permissions.' in source
    assert 'allowed &= branch_ids' in source


def test_central_manager_is_global_in_mission_report_queries_and_exports():
    mission_query = (ROOT / 'employee_movements' / 'services' / 'mission_query.py').read_text(encoding='utf-8')
    missions = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
    access = (ROOT / 'employee_movements' / 'access.py').read_text(encoding='utf-8')
    assert "'Manager Application Support'" in mission_query
    export_body = missions[missions.index("def mission_export_xlsx"):missions.index("def mission_monthly_aggregation")]
    assert "build_mission_report_context(" in export_body
    assert "roles=roles()" in export_body
    assert "Manager Application Support" in access
    assert "Leave and permission records remain in the selected operational scope" in access
    assert "Central Manager may manage assignments across all governorates" in access
