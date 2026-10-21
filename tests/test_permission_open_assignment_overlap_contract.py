from pathlib import Path


def test_permission_validation_checks_open_assignment_from_start_date():
    source = (Path(__file__).parents[1] / 'employee_movements' / 'validation.py').read_text(encoding='utf-8')
    permission_branch = source.split("if mt == 'إذن':", 1)[1].split("if not start:", 1)[0]

    assert "Movement.movement_type == 'انتداب'" in permission_branch
    assert "assignment_open_filter(Movement)" in source
    assert "assignment_state != 'مغلق'" not in permission_branch
    assert "Movement.from_date <= day" in permission_branch
    assert "Movement.to_date.is_(None)" in permission_branch
    assert 'OVERLAP_CONFLICT_MESSAGE' in source
    assert 'return OVERLAP_CONFLICT_MESSAGE' in permission_branch
