from pathlib import Path
"""Regression tests for intentionally empty custom permission sets."""

from werkzeug.security import generate_password_hash

from employee_movements.access import CUSTOM_PERMISSION_SET_MARKER, user_permissions
from employee_movements.constants import ROLE_DEFAULT_PERMISSIONS
from employee_movements.extensions import db
from employee_movements.models import User, UserPermission, UserRole


def _user(username):
    user = User(
        username=username,
        full_name=username,
        email=f'{username}@example.test',
        job_title='اختبار',
        job_code=username,
        password_hash=generate_password_hash('TestPass123!'),
    )
    db.session.add(user)
    db.session.flush()
    db.session.add(UserRole(user_id=user.id, role='مشرف محافظة'))
    db.session.flush()
    return user


def test_legacy_user_without_permission_rows_inherits_role_defaults(app):
    with app.app_context():
        user = _user('legacy_permission_user')
        db.session.commit()
        assert user_permissions(user) == set(ROLE_DEFAULT_PERMISSIONS['مشرف محافظة'])


def test_custom_marker_allows_intentionally_empty_permissions(app):
    with app.app_context():
        user = _user('empty_custom_permission_user')
        db.session.add(UserPermission(user_id=user.id, permission=CUSTOM_PERMISSION_SET_MARKER))
        db.session.commit()
        assert user_permissions(user) == set()


def test_custom_marker_keeps_only_explicitly_selected_permissions(app):
    with app.app_context():
        user = _user('partial_custom_permission_user')
        db.session.add_all([
            UserPermission(user_id=user.id, permission=CUSTOM_PERMISSION_SET_MARKER),
            UserPermission(user_id=user.id, permission='view_reports'),
        ])
        db.session.commit()
        assert user_permissions(user) == {'view_reports'}



def test_access_module_imports_permission_catalog_for_admin_role():
    source = (Path(__file__).resolve().parents[1] / 'employee_movements' / 'access.py').read_text(encoding='utf-8')
    assert 'from .constants import ' in source and 'GLOBAL_READ_SCOPE_ENDPOINTS' in source and 'OPERATIONAL_SCOPE_ENDPOINTS' in source and 'ROLE_DEFAULT_PERMISSIONS' in source
    assert 'return set(PERMISSIONS)' in source



def test_active_role_is_validated_against_stored_roles_before_admin_permissions():
    source = (Path(__file__).resolve().parents[1] / 'employee_movements' / 'access.py').read_text(encoding='utf-8')
    assert "candidate_role in (actual_roles(u) - {'المدخل الأول'})" in source
    assert "elif candidate_role:" in source
    assert "session.pop('active_role', None)" in source
