from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = (ROOT / 'employee_movements' / 'assistant' / 'manager.py').read_text(encoding='utf-8')
RESOLVER = (ROOT / 'employee_movements' / 'assistant' / 'manager_resolvers.py').read_text(encoding='utf-8')


def test_supervisor_name_resolution_is_centralized():
    assert 'resolve_active_supervisor_by_name' in MANAGER
    assert "User.query.filter(User.is_active == True, User.full_name.ilike" not in MANAGER
    assert 'User.query.filter_by(is_active=True).all()' not in MANAGER


def test_supervisor_resolver_filters_role_in_database():
    assert 'join(UserRole, UserRole.user_id == User.id)' in RESOLVER
    assert 'UserRole.role == SUPERVISOR_ROLE' in RESOLVER
    assert '.distinct()' in RESOLVER
    assert '.limit(limit)' in RESOLVER


def test_manager_has_separate_plan_and_execute_entry_points():
    assert 'def plan(a):' in MANAGER
    assert 'def execute(plan):' in MANAGER
    assert "if not is_app_manager():" in MANAGER
    assert "return False, 'لم تعد تملك صلاحية مسؤول التطبيق.'" in MANAGER
