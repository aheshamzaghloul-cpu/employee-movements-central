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
        'assignment_closed_filter(Movement)',
        'assignment_open_filter(Movement)',
        'Movement.to_date.is_(None)',
        'Movement.to_date.isnot(None)',
        'parse_optional_iso_date',
        'MissionEditRequest.query',
    ):
        assert marker in text, f'Mission query service lost required behavior: {marker}'


def test_mission_filter_options_reuse_active_reference_data_and_id_maps():
    text = SERVICE.read_text(encoding='utf-8')
    assert "destination_governorates = govs" in text
    assert "governorates_by_id = {governorate.id: governorate for governorate in govs}" in text
    assert "active_branches = active_branch_query.order_by(" in text
    assert "destination_branches = list(active_branches)" in text
    assert "destination_branches_by_id = {b.id: b for b in destination_branches}" in text
    assert "branches_by_id = {b.id: b for b in branches}" in text


def test_mission_report_search_explains_server_page_scope():
    app_js = (ROOT / 'employee_movements' / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
    template = (ROOT / 'employee_movements' / 'templates' / 'mission_reports.html').read_text(encoding='utf-8')
    assert 'data-smart-server-page="true"' in template
    assert 'الصفحة الحالية فقط' in template
    assert "table.dataset.smartServerPage === 'true'" in app_js
    assert 'في الصفحة الحالية' in app_js
