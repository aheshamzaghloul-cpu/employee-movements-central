from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'employee_movements/blueprints/employees.py').read_text(encoding='utf-8')
HOME = (ROOT / 'employee_movements/templates/home_global_search.html').read_text(encoding='utf-8')
PROFILE = (ROOT / 'employee_movements/templates/employee.html').read_text(encoding='utf-8')


def test_global_search_requires_login_but_not_employee_management_or_report_roles():
    block = ROUTES[ROUTES.index('def employee_search():'):ROUTES.index("@bp.route('/employees'", ROUTES.index('def employee_search():'))]
    marker = "@bp.get('/employee-search')"
    decorator_block = ROUTES[ROUTES.rfind(marker, 0, ROUTES.index('def employee_search():')):ROUTES.index('def employee_search():')]
    assert '@req' in decorator_block
    assert "can('manage_employees') or can('view_reports')" not in block
    assert "'company_phone'" in block and "'personal_phone'" in block and "'email'" in block


def test_profile_details_are_shared_but_movement_history_remains_restricted():
    block = ROUTES[ROUTES.index('def employee_card(i):'):]
    assert "can_read_movement_details = can('view_reports')" in block
    assert 'if can_read_movement_details:' in block
    assert "if not (can('manage_employees') or can_read_movement_details)" not in block
    assert 'movement_employee_in_scope or has_role' not in HOME
    assert 'الملف الكامل متاح عند العمل ضمن نطاق هذه المحافظة' not in HOME
    assert 'smart-contact-card' in PROFILE


def test_personnel_code_is_presented_once_with_legacy_fallback():
    assert "movement_employee.employee_code or movement_employee.job_code or 'غير مسجل'" in HOME
    assert 'رقم سجل الموظف' not in HOME
    assert "e.employee_code or e.job_code or '—'" in PROFILE
    assert 'كود شئون العاملين' in PROFILE
