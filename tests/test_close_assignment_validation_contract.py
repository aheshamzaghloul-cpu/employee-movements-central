from pathlib import Path


def test_close_assignment_validates_date_and_overlaps_before_mutation():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    start = source.index("def close_assignment(i):")
    end = source.index("@bp.post('/movements/<int:i>/reopen-assignment')", start)
    body = source[start:end]
    assert "except ValueError:" in body
    assert "تاريخ الإغلاق غير صحيح" in body
    assert "movement_overlaps" in body
    assert body.index("movement_overlaps") < body.index("m.assignment_state = 'مغلق'")
    assert "m.id)" in body
