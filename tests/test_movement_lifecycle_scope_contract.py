from pathlib import Path


def _route(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


def test_mission_close_and_reopen_recheck_source_scope_and_manage_permission():
    source = Path("employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    close = _route(source, "def mission_close(", "@bp.post('/reports/assignments/mission-reopen/")
    reopen = _route(source, "def mission_reopen(", "@bp.get('/reports/assignments/mission-print-date/")
    for route in (close, reopen):
        assert "not can('manage_movements') or not can_manage_movement(m)" in route
        assert "not m.is_active" in route
    assert "if not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):" in reopen


def test_assignment_close_reopen_recheck_source_scope_and_reopen_role_boundary():
    source = Path("employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    close = _route(source, "def close_assignment(", "@bp.post('/movements/<int:i>/reopen-assignment')")
    reopen = _route(source, "def reopen_assignment(", "@bp.get('/movements/<int:i>/assignment-form')")
    for route in (close, reopen):
        assert "not can('manage_movements') or not can_manage_movement(m)" in route
        assert "not m.is_active" in route
    assert "if not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):" in reopen
    assert "movement_overlaps(" in reopen


def test_movement_delete_requires_delete_permission_and_scope():
    source = Path("employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    route = _route(source, "def movement_delete(", "@bp.get('/movements/<int:i>/history')")
    assert "not can('delete_movements')" in route
    assert "not can_manage_movement(m) and 'مسؤول التطبيق' not in roles()" in route
    assert "m.is_active = False" in route
    assert "record_movement_history" in route
