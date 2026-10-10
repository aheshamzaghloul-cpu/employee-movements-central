from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = ROOT / 'employee_movements' / 'blueprints' / 'movements.py'
VALIDATION = ROOT / 'employee_movements' / 'validation.py'


def test_assignment_validation_can_skip_duplicate_branch_scope_only_after_route_authorization():
    source = VALIDATION.read_text(encoding='utf-8')
    assert 'destination_scope_checked=False' in source
    assert 'not destination_scope_checked and not branch_ok(dest)' in source


def test_create_and_preflight_authorize_assignment_destination_before_scope_override():
    source = MOVEMENTS.read_text(encoding='utf-8')
    start = source.index('def movement_preflight_api():')
    preflight = source[start:source.index('\n@bp.', start)]
    create = source[source.index('def movement_create():'):source.index("@bp.get('/movements')")]
    assert 'can_manage_movement_destination(destination, movement_type)' in preflight
    assert 'destination_scope_checked=(movement_type == \'انتداب\' and destination_id is not None)' in preflight
    assert 'can_manage_movement_destination(destination, movement_type)' in create
    assert 'destination_scope_checked=(movement_type == \'انتداب\' and destination is not None)' in create


def test_edit_route_validates_destination_scope_before_assignment_save():
    source = MOVEMENTS.read_text(encoding='utf-8')
    start = source.index('def movement_edit(i):')
    edit = source[start:source.index('\n@bp.', start)]
    assert 'can_manage_movement_destination(destination, mt)' in edit
    assert 'destination_scope_checked=(mt == \'انتداب\' and dest is not None)' in edit
