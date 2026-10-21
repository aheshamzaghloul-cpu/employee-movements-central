"""Source-only guard for consuming ticket OCR drafts once per mission create."""
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_mission_create_locks_draft_before_use_and_deletes_it_after_attach():
    source = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
    create = source.split("def mission_from_screenshot_create():", 1)[1].split("def _render_mission_edit_form", 1)[0]
    query = create.split("ticket_image_draft = (", 1)[1].split("if ticket_image_draft and", 1)[0]
    assert ".with_for_update()" in query
    assert "uploaded_by=me().id" in query
    assert "db.session.delete(ticket_image_draft)" in create
    assert "db.session.commit()" in create
