"""Regression contracts for mission report filters, export shape and response privacy."""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "employee_movements" / "services" / "mission_query.py"
DOCS = ROOT / "employee_movements" / "services" / "mission_documents.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
PRINT_TEMPLATE = ROOT / "employee_movements" / "templates" / "mission_reports_print.html"
HOOKS = ROOT / "employee_movements" / "hooks.py"
SMOKE = ROOT / "scripts" / "check_mission_center_runtime.py"


def _xlsx_headers():
    source = DOCS.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "mission_export_xlsx":
            for child in ast.walk(node):
                if isinstance(child, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "headers" for target in child.targets
                ):
                    return ast.literal_eval(child.value)
    raise AssertionError("mission_export_xlsx headers list was not found")


def test_open_duration_filter_excludes_closed_legacy_rows_without_end_dates():
    source = QUERY.read_text(encoding="utf-8")
    start = source.index("if duration == 'open':")
    end = source.index("elif duration == 'dated':", start)
    block = source[start:end]
    assert "Movement.to_date.is_(None)" in block
    assert "assignment_open_filter(Movement)" in block


def test_mission_report_print_receives_database_count_without_materializing_query():
    query = QUERY.read_text(encoding="utf-8")
    routes = MISSIONS.read_text(encoding="utf-8")
    template = PRINT_TEMPLATE.read_text(encoding="utf-8")
    assert "total_rows = q.order_by(None).count() if (paginate or include_total) else None" in query
    start = routes.index("def mission_print_all():")
    end = routes.index("@bp.post('/reports/assignments/mission-edit-request/<int:movement_id>')", start)
    assert "include_total=True" in routes[start:end]
    assert "إجمالي السجلات المطابقة: {{ total_rows if total_rows is not none else 0 }}" in template


def test_xlsx_export_contains_only_distinct_source_and_destination_columns():
    headers = _xlsx_headers()
    assert len(headers) == 16
    assert len(set(headers)) == len(headers)
    assert headers[3:7] == [
        "محافظة الموظف", "فرع الموظف", "محافظة جهة المأمورية", "فرع جهة المأمورية"
    ]
    assert "منشئ المأمورية" in headers
    assert "من محافظة" not in headers and "من فرع" not in headers


def test_sensitive_report_and_export_endpoints_are_marked_no_store():
    source = HOOKS.read_text(encoding="utf-8")
    assert "PRIVATE_REPORT_ENDPOINTS = frozenset({" in source
    for endpoint in (
        "missions.mission_print_list",
        "missions.mission_print_all",
        "missions.mission_export_xlsx",
        "missions.mission_pdf",
        "reports.reports",
        "reports.employee_type_report_xlsx",
    ):
        assert f"'{endpoint}'" in source
    assert "resp.headers['Cache-Control'] = 'private, no-store, max-age=0'" in source
    assert "resp.headers['Pragma'] = 'no-cache'" in source
    assert "resp.headers['Expires'] = '0'" in source


def test_http_smoke_checks_pagination_against_all_results_print_and_xlsx():
    source = SMOKE.read_text(encoding="utf-8")
    assert "MISSION_SMOKE_RESULT_COUNT = 55" in source
    assert "len(page_ids) != 50" in source
    assert "set(print_ids) != set(mission_ids)" in source
    assert "set(exported_ids) != set(mission_ids)" in source
    assert "len(rows) != MISSION_SMOKE_RESULT_COUNT" in source
    assert "assert_private_no_store(response, label: str)" in source
    assert "assert_private_no_store(export_response, \"Mission XLSX export\")" in source
    assert "matching[0][13] != creator_name" in source
