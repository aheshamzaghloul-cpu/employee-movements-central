from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "employee_movements" / "services" / "mission_lifecycle.py"
DOCUMENTS = ROOT / "employee_movements" / "services" / "mission_documents.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
MODELS = ROOT / "employee_movements" / "models.py"

def test_closing_user_and_timestamp_are_saved_and_reset_on_reopen():
    text = LIFECYCLE.read_text(encoding="utf-8")
    close = text[text.index("def close_mission"):text.index("def reopen_mission")]
    reopen = text[text.index("def reopen_mission"):text.index("def apply_mission_edit")]
    assert "movement.closed_by = actor.id if actor else None" in close
    assert "movement.closed_at = now" in close
    assert "movement.closed_by = None" in reopen
    assert "movement.closed_at = None" in reopen

def test_pdf_swaps_creator_for_closer_in_the_existing_top_right_name_slot_only():
    docs = DOCUMENTS.read_text(encoding="utf-8")
    routes = MISSIONS.read_text(encoding="utf-8")
    models = MODELS.read_text(encoding="utf-8")
    assert "closed_by_user = db.relationship('User', foreign_keys=[closed_by])" in models
    assert "display_user = closer if is_closed else creator" in docs
    assert "display_name = display_user.full_name if display_user else ''" in docs
    assert "fitz.Rect(462.5, 90.2, 552.8, 98.2)" in docs
    assert "أُغلقت بمعرفة:" not in docs
    assert "closer_name" not in docs
    assert "creator_name = creator.full_name if creator else ''" not in docs
    assert routes.count("closer=m.closed_by_user") == 2

def test_manager_closing_via_edit_request_records_closer():
    text = LIFECYCLE.read_text(encoding="utf-8")
    body = text[text.index("def execute_edit_request"): ]
    assert "if final_state == 'مغلقة':" in body
    assert "movement.closed_by = actor.id if actor else None" in body
    assert "movement.closed_at = now" in body
