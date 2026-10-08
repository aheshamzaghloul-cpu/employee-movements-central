from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MISSIONS = ROOT / 'employee_movements' / 'blueprints' / 'missions.py'
SERVICE = ROOT / 'employee_movements' / 'services' / 'mission_query.py'


def test_mission_print_list_delegates_query_work_to_service():
    text = MISSIONS.read_text(encoding='utf-8')
    assert 'build_mission_report_context' in text
    assert "return render_template('mission_reports.html', **context)" in text

    body = text[text.index("def mission_print_list"):text.index("@bp.post('/reports/assignments/mission-edit-request")]
    assert 'Movement.query' not in body
    assert 'MissionEditRequest.query' not in body
    assert 'parse_optional_iso_date' not in body


def test_mission_query_service_owns_report_filters_and_scope_query():
    text = SERVICE.read_text(encoding='utf-8')
    for marker in (
        'Employee.branch_id.in_(allowed_bids)',
        'Movement.destination.has(',
        'Movement.destination_branch_id == selected_destination_branch.id',
        'Movement.mission_state == mission_state',
        'Movement.to_date.is_(None)',
        'Movement.to_date.isnot(None)',
        'parse_optional_iso_date',
        'MissionEditRequest.query',
    ):
        assert marker in text, f'Mission query service lost required behavior: {marker}'
