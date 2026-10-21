"""Guard the CI runtime check for the actual mission table and its documents."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI = ROOT / ".github" / "workflows" / "ci.yml"
SMOKE = ROOT / "scripts" / "check_mission_center_runtime.py"


def test_docker_ci_runs_authenticated_mission_center_smoke_against_postgres():
    workflow = CI.read_text(encoding="utf-8")
    assert "emc-smoke-db" in workflow
    assert "CI_MISSION_CENTER_SMOKE=1" in workflow
    assert "scripts/check_mission_center_runtime.py" in workflow
    assert workflow.index("scripts/check_mission_center_runtime.py") < workflow.index("scripts/check_ticket_ocr_runtime.py")


def test_mission_center_smoke_fails_closed_outside_ephemeral_ci_database():
    script = SMOKE.read_text(encoding="utf-8")
    assert 'os.environ.get("CI_MISSION_CENTER_SMOKE") != "1"' in script
    assert 'parsed.host != "emc-smoke-db" or parsed.database != "movements_smoke"' in script


def test_mission_center_smoke_verifies_live_table_xlsx_and_pdf():
    script = SMOKE.read_text(encoding="utf-8")
    assert 'report_url = f"/reports/assignments/print-missions?{report_filters}"' in script
    assert 'export_response = get(f"/reports/assignments/export.xlsx?{report_filters}")' in script
    assert '"/reports/assignments/mission-pdf/' in script
    assert "f'data-mission-id=\"{mission_id}\"'" in script
    assert "load_workbook(BytesIO(exported_bytes)" in script
    assert "MISSION_SMOKE_RESULT_COUNT = 55" in script
    assert "len(page_ids) != 50" in script
    assert "set(print_ids) != set(mission_ids)" in script
    assert "set(exported_ids) != set(mission_ids)" in script
    assert 'pdf_bytes.startswith(b"%PDF")' in script
