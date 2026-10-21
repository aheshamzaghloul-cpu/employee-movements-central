from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
ROUTES = (ROOT / 'employee_movements/blueprints/employees.py').read_text(encoding='utf-8')
HOME = (ROOT / 'employee_movements/templates/home_global_search.html').read_text(encoding='utf-8')
PROFILE = (ROOT / 'employee_movements/templates/employee.html').read_text(encoding='utf-8')
JS = (ROOT / 'employee_movements/static/js/app.js').read_text(encoding='utf-8')
CSS = (ROOT / 'employee_movements/static/css/pages/home.css').read_text(encoding='utf-8')
BASE = (ROOT / 'employee_movements/templates/base.html').read_text(encoding='utf-8')


def _search_endpoint():
    start = ROUTES.index('def employee_search():')
    end = ROUTES.index("@bp.route('/employees'", start)
    return ROUTES[start:end]


def test_global_employee_search_exposes_all_employee_data_to_authenticated_users():
    endpoint = _search_endpoint()
    assert "if not (can('manage_employees') or can('view_reports'))" not in endpoint
    for field in (
        "'code': e.employee_code or e.job_code or ''",
        "'hire_date'", "'rehire_date'", "'resignation_date'", "'employment_status'",
        "'company_phone'", "'personal_phone'", "'email'",
    ):
        assert field in endpoint


def test_selected_employee_card_shows_one_code_and_all_employee_details():
    for expected in (
        'بيانات الموظف الأساسية', 'كود شئون العاملين', 'تاريخ التعيين',
        'تاريخ العودة للخدمة', 'تاريخ الاستقالة', 'الحالة الوظيفية',
        'مسؤول إدخال هذا الفرع', 'بيانات التواصل',
    ):
        assert expected in HOME
    assert 'movement_employee.employee_code or movement_employee.job_code' in HOME
    assert 'رقم سجل الموظف' not in HOME
    assert "movement_employee.personal_phone or 'غير مسجل'" in HOME
    assert "movement_employee.email or 'غير مسجل'" in HOME
    assert "emp.company_phone or 'غير مسجل'" in HOME
    assert "emp.personal_phone or 'غير مسجل'" in HOME
    assert "emp.resignation_date.strftime('%d/%m/%Y')" in HOME
    assert 'الملف الكامل متاح عند العمل ضمن نطاق هذه المحافظة' not in HOME


def test_employee_profile_public_data_does_not_require_report_permission():
    block = ROUTES[ROUTES.index('def employee_card(i):'):]
    assert "if not (can('manage_employees') or can_read_movement_details)" not in block
    assert 'if can_read_movement_details else None' in block
    contact_block = PROFILE[PROFILE.index('smart-contact-card'):PROFILE.index('smart-context-card')]
    assert "{% if can('manage_employees') %}" not in contact_block
    assert "e.employee_code or e.job_code or '—'" in PROFILE


def test_live_search_shows_single_code_and_shared_employee_data():
    assert "e.code||'—'" in JS
    assert "e.employee_code||'غير مسجل'" not in JS
    for field in ('e.hire_date', 'e.rehire_date', 'e.resignation_date', 'e.company_phone', 'e.personal_phone', 'e.email', 'e.employment_status'):
        assert field in JS
    assert "e.branch_code?' · '+esc(e.branch_code)" in JS


def test_home_details_are_responsive_and_assets_bumped_to_current_version():
    assert 'smart-employee-facts-detailed' in CSS
    assert '@media(max-width:640px)' in CSS
    assert 'data-app-version="{{app_version}}"' in BASE
    assert '68.53.2' not in BASE
