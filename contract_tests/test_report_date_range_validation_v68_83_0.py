"""Fail-closed date range contracts for HTML reports and mission exports."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _source(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_employee_type_report_date_range_is_not_silently_reversed():
    reports = _source("employee_movements/blueprints/reports.py")
    block = reports[reports.index("def _apply_employee_type_report_filters("):reports.index("def _report_branch_scope(")]
    assert "date_range_error = bool(date_from_obj and date_to_obj and date_from_obj > date_to_obj)" in block
    assert "query = query.filter(False)" in block
    assert "'date_range_error': date_range_error" in block
    assert "date_from, date_to = date_to, date_from" not in block

def test_html_and_xlsx_employee_reports_share_filter_helper():
    reports = _source("employee_movements/blueprints/reports.py")
    assert reports.count("_apply_employee_type_report_filters(q, mt, bs, request.args)") == 3
    assert "date_range_error=date_range_error" in reports

def test_mission_html_and_xlsx_share_fail_closed_date_range_logic():
    service = _source("employee_movements/services/mission_query.py")
    assert "date_range_error = bool(df and dt and df > dt)" in service
    assert "if date_range_error:" in service
    assert "q = q.filter(False)" in service
    assert "'date_range_error': date_range_error" in service
    missions = _source("employee_movements/blueprints/missions.py")
    assert "build_mission_report_context(" in missions
    assert "context['rows']" in missions

def test_reversed_range_message_is_explicit_and_accessible_in_both_report_forms():
    report_template = _source("employee_movements/templates/employee_type_report.html")
    mission_template = _source("employee_movements/templates/mission_reports.html")
    assert "تاريخ البداية يأتي بعد تاريخ النهاية" in report_template
    assert 'id="reportDateRangeError" role="alert"' in report_template
    assert 'aria-describedby="reportDateRangeError"' in report_template
    assert "تاريخ البداية يأتي بعد تاريخ النهاية" in mission_template
    assert 'id="missionDateRangeError" role="alert"' in mission_template
    assert 'aria-describedby="missionDateRangeError"' in mission_template
