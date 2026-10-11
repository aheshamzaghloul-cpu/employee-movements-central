from pathlib import Path


def test_reopen_assignment_checks_open_ended_overlap_before_mutation():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    body = source.split("def reopen_assignment(i):", 1)[1].split("@bp.get('/movements/<int:i>/assignment-form')", 1)[0]
    assert "movement_overlaps(" in body
    assert "m.from_date.isoformat() if m.from_date else None" in body
    assert "None,\n        m.id," in body
    assert body.index("if overlap:") < body.index("m.assignment_state = 'ساري'")
    assert "لم يتم" not in body  # no mutation is performed in the rejection branch
