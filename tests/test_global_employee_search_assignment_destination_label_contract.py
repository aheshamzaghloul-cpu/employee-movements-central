from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "employee_movements" / "blueprints" / "employees.py"


def test_global_employee_search_includes_last_assignment_and_destination_governorate():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def employee_search():")
    end = source.index("@bp.route('/employees'", start)
    block = source[start:end]
    assert "latest_assignment_summaries({e.id for e in rows})" in block
    assert "'last_assignment': latest_by_employee.get(e.id, {}).get('text', '')" in block
    assert "'last_assignment_governorate': latest_by_employee.get(e.id, {}).get('governorate', '')" in block


def test_latest_assignment_summary_is_visible_in_home_search_results():
    template = (ROOT / "employee_movements" / "templates" / "home_global_search.html").read_text(encoding="utf-8")
    script = (ROOT / "employee_movements" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "آخر انتداب" in template
    assert "e.last_assignment||'لا يوجد انتداب مسجل'" in script
