from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
QUERY = ROOT / "employee_movements" / "services" / "mission_query.py"
DOCUMENTS = ROOT / "employee_movements" / "services" / "mission_documents.py"
MODELS = ROOT / "employee_movements" / "models.py"
BASE = ROOT / "employee_movements" / "templates" / "base.html"
TEMPLATE = ROOT / "employee_movements" / "templates" / "mission_reports.html"
PRINT_TEMPLATE = ROOT / "employee_movements" / "templates" / "mission_reports_print.html"
PRINT_CSS = ROOT / "employee_movements" / "static" / "css" / "pages" / "mission-report-print.css"
SMOKE = ROOT / "scripts" / "check_mission_center_runtime.py"


def test_all_results_print_uses_same_authorized_filter_service_without_pagination():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_print_all():")
    end = source.index("@bp.post('/reports/assignments/mission-edit-request/<int:movement_id>')", start)
    body = source[start:end]
    assert "if not can('view_reports')" in body
    assert "build_mission_report_context(" in body
    assert "args=request.args" in body
    assert "paginate=False" in body
    assert "include_creator=True" in body
    assert "mission_reports_print.html" in body


def test_mission_center_has_filter_preserving_all_results_print_action():
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "url_for('missions.mission_print_all', **request.args.to_dict())" in template
    assert 'target="_blank"' in template
    assert "طباعة جميع النتائج" in template


def test_all_results_print_template_contains_all_report_rows_and_current_filters():
    template = PRINT_TEMPLATE.read_text(encoding="utf-8")
    assert "{% for m in rows %}" in template
    assert 'data-mission-id="{{ m.id }}"' in template
    assert "print_filters" in template
    assert "date_range_error" in template
    assert "mission_state_label(m)" in template
    assert "وليس الصفحة الحالية فقط" in template
    assert "لا توجد مأموريات تطابق الفلاتر الحالية" in template


def test_all_results_print_styles_are_route_scoped_and_print_ready():
    base = BASE.read_text(encoding="utf-8")
    css = PRINT_CSS.read_text(encoding="utf-8")
    assert "request.path == '/reports/assignments/print-missions/print'" in base
    assert "@page{size:A4 landscape" in css
    assert "thead{display:table-header-group}" in css
    assert "tr{break-inside:avoid" in css
    assert ".mission-report-print-table-wrap{overflow:visible" in css


def test_mission_xlsx_creator_column_uses_actual_creator_not_employee_name():
    model = MODELS.read_text(encoding="utf-8")
    query = QUERY.read_text(encoding="utf-8")
    docs = DOCUMENTS.read_text(encoding="utf-8")
    route = MISSIONS.read_text(encoding="utf-8")
    assert "creator_user = db.relationship('User', foreign_keys=[created_by])" in model
    assert "def build_mission_report_context(*, roles, allowed_bids, args, paginate=False, include_creator=False, include_total=False)" in query
    assert "joinedload(Movement.creator_user)" in query
    assert "mission.creator_user.full_name if getattr(mission, 'creator_user', None) else ''" in docs
    export_start = route.index("def mission_export_xlsx():")
    export_end = route.index("@bp.get('/reports/assignments/monthly')", export_start)
    assert "include_creator=True" in route[export_start:export_end]


def test_ci_http_smoke_covers_filtered_all_results_print_and_pdf_xlsx_remain_covered():
    smoke = SMOKE.read_text(encoding="utf-8")
    assert 'print_response = get(f"/reports/assignments/print-missions/print?{report_filters}")' in smoke
    assert 'export_response = get(f"/reports/assignments/export.xlsx?{report_filters}")' in smoke
    assert '"/reports/assignments/mission-pdf/' in smoke
    assert "matching[0][13] != creator_name" in smoke
    assert "MISSION_SMOKE_RESULT_COUNT = 55" in smoke
    assert "set(print_ids) != set(mission_ids)" in smoke
    assert "set(exported_ids) != set(mission_ids)" in smoke
