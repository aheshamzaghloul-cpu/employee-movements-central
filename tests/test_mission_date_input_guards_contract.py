from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_assignment_close_handles_invalid_date():
    source = (ROOT / "employee_movements/blueprints/movements.py").read_text()
    section = source.split("def close_assignment(i):", 1)[1].split("@bp.post('/movements/<int:i>/reopen-assignment')", 1)[0]
    assert "except ValueError:" in section
    assert "تاريخ الإغلاق غير صحيح" in section

def test_mission_edit_handles_invalid_dates_before_mutation():
    source = (ROOT / "employee_movements/blueprints/missions.py").read_text()
    section = source.split("def mission_edit_save(movement_id):", 1)[1].split("@bp.post('/reports/assignments/mission-close/", 1)[0]
    assert "except ValueError:" in section
    assert "تاريخ المأمورية غير صحيح" in section
    assert section.index("except ValueError:") < section.index("apply_mission_edit(")

def test_mission_print_date_handles_invalid_date():
    source = (ROOT / "employee_movements/blueprints/missions.py").read_text()
    section = source.split("def mission_print_date_save(movement_id):", 1)[1].split("@bp.get('/reports/assignments/mission-pdf/", 1)[0]
    assert "except ValueError:" in section
    assert "تاريخ «إلى» غير صحيح" in section
