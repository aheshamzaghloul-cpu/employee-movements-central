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
