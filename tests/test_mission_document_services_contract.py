from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
SERVICE = ROOT / "employee_movements" / "services" / "mission_documents.py"


def test_mission_documents_are_extracted_from_blueprint():
    mission_text = MISSIONS.read_text()
    service_text = SERVICE.read_text()
    assert "from ..services.mission_documents import" in mission_text
    assert "def mission_template_pdf(" in service_text
    assert "def mission_export_xlsx(" in service_text
    assert "def mission_template_pdf(" not in mission_text


def test_mission_routes_still_delegate_document_generation():
    text = MISSIONS.read_text()
    assert "mission_template_pdf(" in text
    assert "mission_export_xlsx as build_mission_export_xlsx" in text
    assert "out = build_mission_export_xlsx(context['rows'])" in text
    assert "mission-{m.id}.pdf" in text
    assert "المأموريات.xlsx" in text


def test_mission_document_service_preserves_template_assets():
    text = SERVICE.read_text()
    assert "mission_template.pdf" in text
    assert "mission-original.ttf" in text
    assert "insert_htmlbox" in text
    assert "freeze_panes = 'A2'" in text
    assert "auto_filter.ref = ws.dimensions" in text
