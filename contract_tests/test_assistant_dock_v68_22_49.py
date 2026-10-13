"""Regression contracts for the assistant dock no longer obstructing mobile content."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
DOCK = (ROOT / "employee_movements/templates/assistant_dock.html").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
JS = (ROOT / "employee_movements/static/js/assistant_dock.js").read_text(encoding="utf-8")


def test_assistant_launcher_is_inside_the_app_topbar_not_after_page_content():
    topbar = BASE[BASE.index('<header class="ui-topbar premium-topbar">'):BASE.index("</header>", BASE.index('<header class="ui-topbar premium-topbar">'))]
    assert "{% include 'assistant_dock.html' %}" in topbar
    assert BASE.index("{% include 'assistant_dock.html' %}") < BASE.index("</header>")
    assert BASE.count("{% include 'assistant_dock.html' %}") == 1


def test_assistant_panel_is_anchored_below_topbar_with_viewport_limits():
    assert "position: static;" in CSS[CSS.rfind("/* v68.22.49 — place Basyouni"):]
    block = CSS[CSS.rfind("/* v68.22.49 — place Basyouni"):]
    assert ".assistant-dock-panel {" in block
    assert "top: calc(100% + 8px);" in block
    assert "height: min(600px, calc(100dvh - var(--ui-topbar) - 16px));" in block
    assert "@media (max-width: 700px)" in block


def test_assistant_has_explicit_close_button_and_restores_focus():
    assert 'id="assistantDockClose"' in DOCK
    assert 'aria-label="إغلاق المساعد"' in DOCK
    assert "closeButton?.addEventListener('click',()=>setOpen(false));" in JS
    assert "else toggle?.focus({preventScroll:true});" in JS


def test_assistant_context_and_submission_controls_are_preserved():
    for token in ["assistantDockContext", "assistantDockThread", "assistantDockForm", "assistantDockInput", "assistantWorkspaceContext"]:
        assert token in DOCK
    assert "fetch('/assistant?panel=1'" in JS
    assert "credentials:'same-origin'" in JS


def test_optional_excel_branch_code_can_be_left_unmapped_in_the_actual_template():
    excel = (ROOT / "employee_movements/templates/excel_import.html").read_text(encoding="utf-8")
    condition = "{% if not (kind=='employees' and field in ['email','company_phone','personal_phone','branch_code']) %}required{% endif %}"
    assert condition in excel
    assert "optional_employee_fields = {'email', 'company_phone', 'personal_phone', 'branch_code'}" in (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")


def test_employee_type_report_smart_tables_have_responsive_overflow_containers():
    report = (ROOT / "employee_movements/templates/employee_type_report.html").read_text(encoding="utf-8")
    assert '<div class="ui-table-wrap"><table class="ui-table report-movement-table">' in report
    assert 'data-report-search-root' in report and 'data-report-search maxlength="120"' in report
    assert 'data-employee-search=' in report
    assert '<table data-smart-table>' not in report
    assert ".ui-table-wrap{overflow-x:auto}" in CSS
    assert ".ui-table-wrap>table[data-smart-table]{min-width:720px}" in CSS
    assert ".ui-table-wrap>table.report-movement-table{min-width:720px}" in CSS


def test_employee_type_report_table_separates_header_from_searchable_body_rows():
    report = (ROOT / "employee_movements/templates/employee_type_report.html").read_text(encoding="utf-8")
    assert '<table class="ui-table report-movement-table"><thead><tr><th>النوع</th>' in report
    assert '</tr></thead><tbody>' in report
    assert '</tbody></table></div></div>{% endfor %}' in report


def test_assignment_type_report_has_a_print_cell_matching_its_mission_header():
    report = (ROOT / "employee_movements/templates/employee_type_report.html").read_text(encoding="utf-8")
    assert "<th class=\"no-print\">المأمورية</th>" in report
    assert "href=\"/reports/assignments/mission-pdf/{{m.id}}\"" in report
    assert "{% if report_type=='assignments' %}<td class=\"no-print\" data-search-ignore>" in report
    assert "target=\"_blank\" rel=\"noopener\"" in report


def test_legacy_fixed_overlay_position_rules_are_removed():
    assert '.assistant-dock{position:fixed' not in CSS
    assert '.assistant-dock{inset-inline-end:12px;bottom:12px}' not in CSS
    assert 'bottom:58px' not in CSS
    assert 'bottom:54px' not in CSS


def test_error_states_use_generic_arabic_messages_without_exposing_exception_details():
    errors = (ROOT / 'employee_movements/errors.py').read_text(encoding='utf-8')
    template = (ROOT / 'employee_movements/templates/error.html').read_text(encoding='utf-8')
    for code in ['400', '403', '404', '405', '413', '500']:
        assert f'    {code}:' in errors
    assert "500: ('حدث خطأ غير متوقع', 'تم تسجيل المشكلة. حاول مرة أخرى بعد قليل.')" in errors
    assert '{{ message }}' in template
    assert 'traceback' not in template.lower()
    assert 'exception' not in template.lower()


def test_global_csrf_guard_is_enabled_without_exempted_endpoints():
    hooks = (ROOT / 'employee_movements/hooks.py').read_text(encoding='utf-8')
    assert 'CSRF_EXEMPT_ENDPOINTS = frozenset()' in hooks
    assert "if request.method != 'POST' or request.endpoint in CSRF_EXEMPT_ENDPOINTS:" in hooks
    assert 'hmac.compare_digest(token, expected)' in hooks


def test_release_metadata_uses_one_package_version():
    import re
    init = (ROOT / 'employee_movements/__init__.py').read_text(encoding='utf-8')
    pyproject = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    version = (ROOT / 'VERSION.md').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r"\d+\.\d+\.\d+", version)
    assert f"__version__ = '{version}'" in init
    assert f'version = "{version}"' in pyproject
    assert f'?v={version}' in BASE
    assert f'v{version}' in CSS.splitlines()[1]
