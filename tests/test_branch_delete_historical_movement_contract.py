from pathlib import Path


def test_branch_delete_blocks_both_source_and_destination_movement_references():
    source = Path('employee_movements/blueprints/catalog.py').read_text(encoding='utf-8')
    start = source.index("@bp.post('/branches/<int:i>/delete')")
    end = source.index("@bp.route('/lookups'", start)
    route = source[start:end]
    assert "Movement.query.filter_by(branch_id=i).count()" in route
    assert "Movement.query.filter_by(destination_branch_id=i).count()" in route
    assert "استخدم التعطيل" in route
