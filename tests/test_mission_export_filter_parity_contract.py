from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "employee_movements" / "services" / "mission_query.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
TEMPLATE = ROOT / "employee_movements" / "templates" / "mission_reports.html"

def test_start_date_filter_keeps_open_missions():
    source = QUERY.read_text(encoding="utf-8")
    assert "Movement.to_date.is_(None), Movement.to_date >= df" in source

def test_excel_export_reuses_authorized_report_query_and_all_filters():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_export_xlsx():")
    end = source.index("@bp.get('/reports/assignments/monthly')", start)
    block = source[start:end]
    assert "build_mission_report_context(" in block
    assert "args=request.args" in block
    assert "context['rows']" in block

def test_export_link_preserves_current_report_filters():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "url_for('missions.mission_export_xlsx', **request.args.to_dict())" in template
