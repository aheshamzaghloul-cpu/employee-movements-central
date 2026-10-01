"""Integration tests: in-memory SQLite, real Flask app."""

from employee_movements.bootstrap import init_database
from employee_movements.extensions import db
from employee_movements.models import Movement, UserRole

from .conftest import ADMIN_PASSWORD, csrf_from


def test_healthz(client):
    resp = client.get('/healthz')
    assert resp.status_code == 200
    assert resp.get_json() == {'status': 'ok'}


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
