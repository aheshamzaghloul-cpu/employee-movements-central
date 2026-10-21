"""Optional integration smoke against a disposable, real PostgreSQL database.

Set POSTGRES_TEST_URL only for an empty, isolated test database. CI provisions a
fresh PostgreSQL service and sets this variable; local SQLite tests never touch
production or a developer database by accident.
"""
import os

import pytest

POSTGRES_TEST_URL = os.getenv('POSTGRES_TEST_URL', '').strip()
pytestmark = pytest.mark.skipif(not POSTGRES_TEST_URL, reason='POSTGRES_TEST_URL is not configured')


def test_postgres_bootstrap_health_and_performance_indexes():
    from sqlalchemy import inspect, text
    from employee_movements import create_app
    from employee_movements.extensions import db

    app = create_app({
        'APP_ENV': 'testing',
        'TESTING': True,
        'SECRET_KEY': 'postgres-integration-test-key-0123456789',
        'SQLALCHEMY_DATABASE_URI': POSTGRES_TEST_URL,
        'DATABASE_URL_CONFIGURED': True,
        'INIT_DATABASE': True,
        'DB_INIT_RETRIES': 1,
        'ADMIN_USERNAME': 'integration-admin',
        'ADMIN_PASSWORD': 'IntegrationPass12345',
        'ADMIN_EMAIL': 'integration-admin@example.invalid',
    })
    try:
        with app.app_context():
            assert db.engine.dialect.name == 'postgresql'
            assert db.session.execute(text('SELECT 1')).scalar_one() == 1
            inspector = inspect(db.engine)
            tables = set(inspector.get_table_names())
            assert {'governorate', 'branch', 'employee', 'movement', 'lookup'} <= tables
            indexes = {
                index.get('name')
                for table in ('branch', 'employee', 'movement')
                if table in tables
                for index in inspector.get_indexes(table)
            }
            assert {
                'ix_branch_governorate_active_code',
                'ix_employee_branch_active_name',
                'ix_employee_job_code',
                'ix_movement_employee_active_from',
                'ix_movement_active_created',
                'ix_movement_type_active_from',
            } <= indexes
        client = app.test_client()
        response = client.get('/healthz')
        assert response.status_code == 200
        payload = response.get_json()
        assert payload['status'] == 'ok'
        assert payload['database_backend'] == 'postgresql'
    finally:
        with app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()
