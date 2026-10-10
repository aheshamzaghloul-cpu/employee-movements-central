from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "employee_movements" / "blueprints" / "employees.py"

def test_global_employee_search_assignment_summary_includes_destination_governorate():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def employee_search():")
    end = source.index("@bp.route('/employees'", start)
    block = source[start:end]
    assert "mv.destination.governorate.name" in block
    assert "'last_assignment': fmt(latest.get('انتداب'))" in block
