"""Regression contracts for fail-closed date and month filter handling."""
from pathlib import Path
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "employee_movements/services/mission_query.py").read_text(encoding="utf-8")
MISSIONS = (ROOT / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
MONTH_TEMPLATE = (ROOT / "employee_movements/templates/mission_monthly.html").read_text(encoding="utf-8")


def test_inverted_mission_report_dates_fail_closed_instead_of_being_silently_swapped():
    date_block = SERVICE.split("df = parse_optional_iso_date(date_from)", 1)[1].split("# Include open missions", 1)[0]
    assert "date_range_error = bool(df and dt and df > dt)" in date_block
    assert "if date_range_error:" in date_block
    assert "filter_error = True" in date_block
    assert "q = q.filter(False)" in date_block
    assert "df, dt = dt, df" not in date_block


def test_invalid_month_filter_does_not_silently_show_current_month_data():
    route = MISSIONS.split("def mission_monthly_aggregation():", 1)[1].split("@bp.get('/reports/assignments/print-mission", 1)[0]
    assert 'month_filter_error = False' in route
    assert 're.fullmatch(r"\\d{4}-(0[1-9]|1[0-2])", month_raw)' in route
    assert 'if month_filter_error:' in route
    assert 'q = q.filter(False)' in route
    assert 'month_filter_error=month_filter_error' in route
    assert 'قيمة الشهر غير صالحة' in MONTH_TEMPLATE


def test_month_filter_warning_template_remains_valid_jinja():
    Environment().parse(MONTH_TEMPLATE)
