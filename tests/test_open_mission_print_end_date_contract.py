from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSIONS = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text()
SERVICE = (ROOT / "employee_movements" / "services" / "mission_documents.py").read_text()
FORM = (ROOT / "employee_movements" / "templates" / "mission_print_date.html").read_text()

def test_open_mission_requires_print_only_end_date_before_pdf():
    assert "return redirect(url_for('missions.mission_print_date', movement_id=m.id))" in MISSIONS
    assert 'name="print_to_date"' in FORM and "required" in FORM
    assert "if not print_to_date:" in MISSIONS
    assert "print_to_date < m.from_date" in MISSIONS
    assert "print_to_date=print_to_date" in MISSIONS

def test_print_only_end_date_fills_existing_pdf_slot_without_saving_mission():
    assert "effective_to_date = print_to_date or mission.to_date" in SERVICE
    assert "effective_to_date.strftime('%Y/%m/%d') if effective_to_date else ''" in SERVICE
    # The print-date handler passes a local override to the PDF service; it does not assign m.to_date.
    handler = MISSIONS.split("def mission_print_date_save(movement_id):", 1)[1].split("@bp.get('/reports/assignments/mission-pdf/", 1)[0]
    assert "m.to_date =" not in handler

def test_creator_or_closer_remains_the_only_top_right_name():
    assert "display_user = closer if is_closed else creator" in SERVICE
    assert "أُغلقت بمعرفة" not in SERVICE
