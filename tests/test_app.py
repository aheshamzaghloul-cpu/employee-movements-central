"""Integration tests: in-memory SQLite, real Flask app."""

from employee_movements import __version__
from employee_movements.bootstrap import init_database
from employee_movements.extensions import db
from employee_movements.models import Movement, UserRole

from .conftest import ADMIN_PASSWORD, csrf_from


def test_healthz(client):
    resp = client.get('/healthz')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    assert payload['version'] == __version__
    assert payload['app_env'] == 'testing'
    assert payload['database_backend'] == 'sqlite'
    assert payload['database_url_configured'] is True


def test_login_page_has_csrf_field_and_security_headers(client):
    resp = client.get('/login')
    assert resp.status_code == 200
    assert b'name="_csrf"' in resp.data
    assert 'Content-Security-Policy' in resp.headers
    assert resp.headers['X-Content-Type-Options'] == 'nosniff'
    assert resp.headers['X-Frame-Options'] == 'DENY'


def test_post_without_csrf_is_rejected(client):
    resp = client.post('/login', data={'username': 'admin', 'password': ADMIN_PASSWORD})
    assert resp.status_code == 400


def test_protected_pages_redirect_to_login(client):
    resp = client.get('/')
    assert resp.status_code == 302
    assert '/login' in resp.headers['Location']


def test_wrong_password_then_rate_limited(client):
    token = csrf_from(client)
    for _ in range(3):
        resp = client.post('/login', data={'username': 'admin', 'password': 'bad', '_csrf': token})
        assert resp.status_code == 200
    resp = client.post('/login', data={'username': 'admin', 'password': ADMIN_PASSWORD, '_csrf': token})
    assert resp.status_code == 429


def test_successful_login(login):
    assert login().get('/healthz').status_code == 200


def test_switch_role_rejects_external_redirect(login):
    client = login()
    with client.session_transaction() as sess:
        token = sess['csrf']
    resp = client.post(
        '/switch-role',
        data={'active_role': 'مشرف محافظة', 'next': '//evil.example', '_csrf': token},
    )
    assert resp.status_code == 302
    assert 'evil.example' not in resp.headers['Location']



def test_switch_role_resets_operational_and_assistant_context(login):
    client = login()
    with client.session_transaction() as sess:
        token = sess['csrf']
        sess['active_role'] = 'مسؤول التطبيق'
        sess['operational_governorate_id'] = 99
        sess['operational_scope_uid'] = 1
        sess['operational_scope_role'] = 'مسؤول التطبيق'
        sess['assistant_pending'] = {'employee_id': 1, 'movement_type': 'إجازة'}
        sess['assistant_manager_pending'] = {'action': 'x'}
        sess['assistant_context_employee_id'] = 1
        sess['assistant_workspace_context'] = 'old role context'
    with client.session_transaction() as sess:
        token = sess['csrf']
    resp = client.post('/switch-role', data={'active_role': 'مشرف محافظة', 'next': '/structure', '_csrf': token})
    assert resp.status_code == 302
    assert resp.headers['Location'].endswith('/')
    with client.session_transaction() as sess:
        assert sess.get('active_role') == 'مشرف محافظة'
        assert 'operational_governorate_id' not in sess
        assert 'operational_scope_uid' not in sess
        assert 'operational_scope_role' not in sess
        assert 'assistant_pending' not in sess
        assert 'assistant_manager_pending' not in sess
        assert 'assistant_context_employee_id' not in sess
        assert 'assistant_workspace_context' not in sess


def test_switch_to_admin_lands_in_administration(login):
    client = login()
    with client.session_transaction() as sess:
        sess['active_role'] = 'مشرف محافظة'
        token = sess['csrf']
    resp = client.post('/switch-role', data={'active_role': 'مسؤول التطبيق', 'next': '/', '_csrf': token})
    assert resp.status_code == 302
    assert '/structure' in resp.headers['Location']

def test_unknown_page_renders_friendly_arabic_404(client):
    resp = client.get('/no-such-page')
    assert resp.status_code == 404
    assert 'الصفحة غير موجودة'.encode() in resp.data


def test_assistant_cancel_does_not_create_a_movement(app, login):
    client = login()
    with client.session_transaction() as sess:
        token = sess['csrf']
        sess['assistant_pending'] = {
            'employee_id': 1,
            'movement_type': 'إجازة',
            'leave_type': 'سنوية',
            'from_date': '2030-01-01',
            'to_date': '2030-01-02',
        }
    resp = client.post('/assistant/confirm', data={'cancel': '1', '_csrf': token})
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert 'assistant_pending' not in sess
    with app.app_context():
        assert Movement.query.count() == 0


def test_nl2br_escapes_html(app):
    rendered = app.jinja_env.filters['nl2br']('<script>alert(1)</script>\nسطر')
    assert '<script>' not in str(rendered)
    assert '<br>' in str(rendered)


def test_admin_keeps_parallel_supervisor_role(app):
    with app.app_context():
        roles = {r.role for r in UserRole.query.all()}
        assert {'مسؤول التطبيق', 'مشرف محافظة'} <= roles


def test_bootstrap_is_idempotent(app):
    with app.app_context():
        init_database(app)
        init_database(app)
        assert UserRole.query.filter_by(role='مشرف محافظة').count() == 1
        db.session.rollback()


def test_live_status_board_excludes_normal_present_employee(app, login):
    from datetime import date

    from employee_movements.blueprints.dashboard import current_employee_status_rows
    from employee_movements.models import Branch, Employee, Governorate

    with app.app_context():
        gov = Governorate(name='اختبار القاهرة')
        db.session.add(gov)
        db.session.flush()
        branch = Branch(governorate_id=gov.id, name='فرع الاختبار', code='T-01')
        employee = Employee(
            full_name='موظف حاضر للاختبار',
            employee_code='EMP-STATUS-01',
            branch=branch,
            job_title='موظف',
            is_active=True,
        )
        db.session.add_all([branch, employee])
        db.session.commit()

        rows = current_employee_status_rows({branch.id}, date.today())
        assert rows == []


def test_home_direct_movement_creation_records_leave(app, login):
    from employee_movements.models import Branch, Employee, Governorate

    client = login()
    with app.app_context():
        gov = Governorate(name='اختبار سوهاج')
        db.session.add(gov)
        db.session.flush()
        branch = Branch(governorate_id=gov.id, name='فرع الحركات', code='T-02')
        employee = Employee(
            full_name='موظف حركة للاختبار',
            employee_code='EMP-MOVE-01',
            branch=branch,
            job_title='موظف',
            is_active=True,
        )
        db.session.add_all([branch, employee])
        db.session.commit()
        employee_id = employee.id
        branch_id = branch.id
        gov_id = gov.id

    with client.session_transaction() as sess:
        sess['operational_governorate_id'] = gov_id
    token = csrf_from(client, '/')

    resp = client.post(
        '/movements/create',
        data={
            'employee_id': str(employee_id),
            'movement_type': 'إجازة',
            'leave_type': 'سنوية',
            'leave_from_date': '2030-01-10',
            'leave_to_date': '2030-01-12',
            'destination_branch_id': '',
            'assignment_from_date': '',
            'assignment_to_date': '',
            'permission_date': '',
            'open_assignment': '',
            '_csrf': token,
        },
    )
    assert resp.status_code == 302

    with app.app_context():
        movement = Movement.query.one()
        assert movement.employee_id == employee_id
        assert movement.movement_type == 'إجازة'
        assert str(movement.from_date) == '2030-01-10'
        assert str(movement.to_date) == '2030-01-12'


def test_home_and_palette_keep_employee_search_boundaries():
    from pathlib import Path

    home = Path('employee_movements/templates/home.html').read_text(encoding='utf-8')
    base = Path('employee_movements/templates/base.html').read_text(encoding='utf-8')
    smart_ui = Path('employee_movements/static/js/smart_ui.js').read_text(encoding='utf-8')
    assert 'home_global_search.html' in home
    assert '<b>الحركات</b>' not in home
    assert 'ابحث عن موظف' not in base
    assert '/employee-search?q=' not in smart_ui

