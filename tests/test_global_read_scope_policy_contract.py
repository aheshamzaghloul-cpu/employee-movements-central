from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = ROOT / 'employee_movements' / 'constants.py'
ACCESS = ROOT / 'employee_movements' / 'access.py'
EMPLOYEES = ROOT / 'employee_movements' / 'blueprints' / 'employees.py'


def _set_block(source, name):
    start = source.index(name)
    end = source.index('\n)', start)
    return source[start:end]


def test_read_only_directories_and_reports_are_not_operational_scope_pages():
    source = CONSTANTS.read_text(encoding='utf-8')
    block = _set_block(source, 'OPERATIONAL_SCOPE_ENDPOINTS')
    for endpoint in (
        'missions.mission_print_list',
        'employees.employee_card',
        'employees.resigned_employees',
        'movements.movements',
        'movements.movement_history',
        'reports.reports',
        'reports.reports_missions',
        'reports.employee_type_report',
        'reports.employee_type_report_xlsx',
        'reports.employee_type_report_csv',
        'reports.report_csv',
        'notifications.notifications',
    ):
        assert f"'{endpoint}'" not in block, f'{endpoint} should be globally readable.'


def test_global_read_safe_method_allowlist_is_explicit_and_mixed_endpoint_keeps_write_scope():
    constants = CONSTANTS.read_text(encoding='utf-8')
    global_block = _set_block(constants, 'GLOBAL_READ_SCOPE_ENDPOINTS')
    assert 'employees.employees' in global_block
    access = ACCESS.read_text(encoding='utf-8')
    start = access.index('def is_scope_required_endpoint():')
    end = access.index('\n\ndef scope_governorate_id', start)
    policy = access[start:end]
    assert "request.method in {'GET', 'HEAD', 'OPTIONS'}" in policy
    assert 'return endpoint in OPERATIONAL_SCOPE_ENDPOINTS' in policy


def test_employee_directory_get_is_global_but_post_still_checks_branch_scope():
    routes = EMPLOYEES.read_text(encoding='utf-8')
    start = routes.index("@bp.route('/employees', methods=['GET', 'POST'])")
    end = routes.index("@bp.", start + 10)
    route = routes[start:end]
    assert "if request.method == 'POST':" in route
    assert 'if not branch_ok(bid):' in route
    assert 'search_branch_ids = {' in route
    assert 'Branch.is_active == True, Governorate.is_active == True' in route


def test_global_mission_directory_relies_on_read_permission_and_keeps_mutations_separate():
    constants = CONSTANTS.read_text(encoding='utf-8')
    op = _set_block(constants, 'OPERATIONAL_SCOPE_ENDPOINTS')
    assert 'missions.mission_print_list' not in op
    missions = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
    start = missions.index("@bp.get('/reports/assignments/print-missions')")
    end = missions.index("@bp.post('/reports/assignments/mission-edit-request/", start)
    route = missions[start:end]
    assert "if not can('view_reports'):" in route
    assert 'build_mission_report_context(' in route


def test_row_mutations_from_global_views_remain_guarded_by_selected_work_governorate():
    access = ACCESS.read_text(encoding='utf-8')
    start = access.index('def can_manage_employee(e):')
    end = access.index('\n\ndef can_manage_movement_employee', start)
    guard = access[start:end]
    assert 'selected = scope_governorate_id()' in guard
    assert 'governorate.id == int(selected)' in guard
    start = access.index('def can_manage_movement(m=None):')
    guard = access[start:]
    assert 'selected = scope_governorate_id()' in guard
    assert 'if not selected:' in guard
