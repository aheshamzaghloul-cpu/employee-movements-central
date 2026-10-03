"""All tests in one module so the repo stays under GitHub's 100-file web upload limit."""

from pathlib import Path
import ast
import pytest

from employee_movements import create_app
from employee_movements.extensions import db

ADMIN_PASSWORD = 'Admin12345'


@pytest.fixture()
def app():
    app = create_app(
        {
            'APP_ENV': 'testing',
            'SECRET_KEY': 'k' * 48,
            'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'ADMIN_USERNAME': 'admin',
            'ADMIN_PASSWORD': ADMIN_PASSWORD,
            'LOGIN_RATE_LIMIT': 3,
        }
    )
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def csrf_from(client, path='/login'):
    """Fetch a page and return the session CSRF token."""
    client.get(path)
    with client.session_transaction() as sess:
        return sess.setdefault('csrf', 'test-csrf-token')


@pytest.fixture()
def login(app, client):
    """Return a callable that signs the admin in and clears the forced password change."""

    def _login():
        from employee_movements.models import User

        with app.app_context():
            user = User.query.filter_by(username='admin').first()
            user.must_change_password = False
            db.session.commit()
        token = csrf_from(client)
        resp = client.post('/login', data={'username': 'admin', 'password': ADMIN_PASSWORD, '_csrf': token})
        assert resp.status_code == 302
        return client

    return _login


# --- app / integration ---

from employee_movements.bootstrap import init_database
from employee_movements.extensions import db
from employee_movements.models import Movement, UserRole


def test_healthz(client):
    resp = client.get('/healthz')
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload['status'] == 'ok'
    assert payload['version'] == '61.0.1'
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


def test_live_status_board_includes_normal_present_employee(app, login):
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
        assert len(rows) == 1
        assert rows[0]['state'] == 'متواجد في الفرع'
        assert rows[0]['movement'] is None


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


# --- text ---

from employee_movements.assistant.text import extract_date, normalize_digits, normalize_for_search


def test_hamza_and_taa_marbuta_are_unified():
    assert normalize_for_search('إجازة') == normalize_for_search('اجازه')


def test_alef_maqsura_and_yaa_are_unified():
    assert normalize_for_search('منى') == normalize_for_search('مني')


def test_diacritics_and_tatweel_removed():
    assert normalize_for_search('مُحَمَّد') == normalize_for_search('محمد')
    assert normalize_for_search('مـحـمد') == 'محمد'


def test_arabic_indic_digits():
    assert normalize_digits('٢٠٢٥') == '2025'


def test_extract_date_pads_parts():
    assert extract_date('من 2025/3/7 إلى') == '2025-03-07'
    assert extract_date('بدون تاريخ') is None


# --- ratelimit ---

from employee_movements.ratelimit import RateLimiter


def test_blocks_after_limit_and_resets():
    limiter = RateLimiter(limit=2, window_seconds=60)
    assert limiter.allow('k') and limiter.allow('k')
    assert not limiter.allow('k')
    assert limiter.is_blocked('k')
    limiter.reset('k')
    assert limiter.allow('k')


def test_keys_are_independent():
    limiter = RateLimiter(limit=1, window_seconds=60)
    assert limiter.allow('a')
    assert limiter.allow('b')


def test_window_expires(monkeypatch):
    import employee_movements.ratelimit as mod

    now = [1000.0]
    monkeypatch.setattr(mod.time, 'monotonic', lambda: now[0])
    limiter = RateLimiter(limit=1, window_seconds=10)
    assert limiter.allow('k')
    assert not limiter.allow('k')
    now[0] += 11
    assert limiter.allow('k')


# --- config ---

from employee_movements.config import ConfigError, database_backend, load_config, normalize_database_url


@pytest.mark.parametrize(
    'url',
    [
        'postgres://u:p@h:5432/db',
        'postgresql://u:p@h:5432/db',
        'postgresql+psycopg://u:p@h:5432/db',
    ],
)
def test_postgres_urls_use_installed_driver(url):
    assert normalize_database_url(url) == 'postgresql+psycopg2://u:p@h:5432/db'


def test_sqlite_url_untouched():
    assert normalize_database_url('sqlite:///x.db') == 'sqlite:///x.db'


def test_production_rejects_missing_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_production_rejects_placeholder_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'change-me-' + 'x' * 40)
    with pytest.raises(ConfigError):
        load_config()


def test_production_requires_persistent_database(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'a' * 48)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(ConfigError):
        load_config()


def test_production_accepts_strong_secret_and_postgres(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'production')
    monkeypatch.setenv('SECRET_KEY', 'a' * 48)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@h:5432/db')
    assert load_config()['SECRET_KEY'] == 'a' * 48
    assert load_config()['SQLALCHEMY_DATABASE_URI'].startswith('postgresql+psycopg2://')


def test_development_generates_ephemeral_secret(monkeypatch):
    monkeypatch.setenv('APP_ENV', 'development')
    monkeypatch.delenv('SECRET_KEY', raising=False)
    assert len(load_config()['SECRET_KEY']) >= 32


def test_database_backend_labels_are_safe():
    assert database_backend('postgresql+psycopg2://u:p@host/db') == 'postgresql'
    assert database_backend('sqlite:///local.db') == 'sqlite'
    assert database_backend('https://example.invalid') == 'other'


# --- assistant contract ---

from pathlib import Path
import ast


def test_agent_declares_application_tools():
    source = Path("employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    required = {
        "get_workspace_context", "search_employees", "get_employee_profile",
        "search_branches", "search_governorates", "search_movements",
        "prepare_action", "navigate_to",
    }
    assert required.issubset(names)


def test_old_theme_layers_are_not_loaded_by_base():
    base = Path("employee_movements/templates/base.html").read_text(encoding="utf-8")
    for legacy in ("professional-v55.css", "professional-v56.css", "professional-v57.css"):
        assert legacy not in base


# --- UI integrity (was scripts/check_ui_integrity.py) ---
def test_ui_integrity_no_legacy_layers():
    root = Path(__file__).resolve().parents[1]
    templates = root / 'employee_movements' / 'templates'
    css_dir = root / 'employee_movements' / 'static' / 'css'
    js_dir = root / 'employee_movements' / 'static' / 'js'
    import re
    legacy = re.compile(r'(?:\bds-[\w-]+|\bv5[0-9]-[\w-]+|[\w-]+-v5[0-9])')
    forbidden = (
        'directActionModal', 'directActionOpen', 'directActionClose',
        'directActionSearch', 'ui-direct-modal', 'ui-direct-panel',
    )
    texts = []
    for p in list(templates.rglob('*.html')) + list(css_dir.glob('*.css')) + list(js_dir.glob('*.js')):
        texts.append((p, p.read_text(encoding='utf-8')))
    errors = []
    for p, s in texts:
        if legacy.search(s):
            errors.append(f'legacy token: {p}')
        for token in forbidden:
            if token in s:
                errors.append(f'forbidden component {token}: {p}')
    css_files = list(css_dir.glob('*.css'))
    if css_files != [css_dir / 'app.css']:
        errors.append(f'expected one CSS entrypoint, found: {[p.name for p in css_files]}')
    js_files = sorted(p.name for p in js_dir.glob('*.js'))
    if js_files != ['app.js']:
        errors.append(f'expected one JS entrypoint, found: {js_files}')
    css = (css_dir / 'app.css').read_text(encoding='utf-8')
    if css.count('{') != css.count('}'):
        errors.append('CSS braces are unbalanced')
    if css.count('(') != css.count(')'):
        errors.append('CSS parentheses are unbalanced')
    assert not errors, '\n'.join(errors)
