from pathlib import Path


def test_manager_movement_edit_destination_choices_use_current_scope():
    source = Path('employee_movements/blueprints/movements.py').read_text(encoding='utf-8')
    start = source.index("@bp.route('/movements/<int:i>/edit'")
    end = source.index("@bp.post('/movements/<int:i>/submit')", start)
    route = source[start:end]
    assert "'Manager Application Support' in roles()" in route
    assert "Branch.id.in_(bids())" in route
    assert "Governorate.id.in_(gids())" in route


def test_manager_movement_edit_post_rejects_destination_outside_scope():
    source = Path('employee_movements/blueprints/movements.py').read_text(encoding='utf-8')
    start = source.index("@bp.route('/movements/<int:i>/edit'")
    end = source.index("@bp.post('/movements/<int:i>/submit')", start)
    route = source[start:end]
    assert "destination.id not in set(bids())" in route
    assert "not can_manage_movement_destination(destination, mt)" in route
