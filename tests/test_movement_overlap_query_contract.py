from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_movement_overlap_does_not_load_all_active_movements():
    source = (ROOT / 'employee_movements' / 'validation.py').read_text()
    start = source.index('def movement_overlaps(')
    end = source.index('\n\ndef validate_movement_fields', start)
    body = source[start:end]

    assert '.all()' not in body
    assert 'Movement.employee_id == employee_id' in body
    assert 'Movement.is_active == True' in body
    assert 'Movement.id != exclude_id' in body
    assert "Movement.permission_date == day" in body
    assert "Movement.movement_type == 'انتداب'" in body


def test_movement_overlap_preserves_validation_messages():
    source = (ROOT / 'employee_movements' / 'validation.py').read_text()
    start = source.index('def movement_overlaps(')
    end = source.index('\n\ndef validate_movement_fields', start)
    body = source[start:end]

    for message in (
        'يوجد إذن آخر للموظف في نفس التاريخ.',
        'تاريخ الإذن يتعارض مع حركة أخرى للموظف.',
        'يوجد انتداب مفتوح للموظف؛ أغلقه أو عدّل مدته قبل تسجيل حركة متعارضة.',
        'فترة الحركة تتعارض مع حركة أخرى للموظف.',
        'فترة الحركة تتعارض مع إذن للموظف.',
    ):
        assert message in body
