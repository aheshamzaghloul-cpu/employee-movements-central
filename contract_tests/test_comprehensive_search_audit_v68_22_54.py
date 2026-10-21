from __future__ import annotations

import importlib.util
from pathlib import Path

from sqlalchemy.dialects import sqlite
from sqlalchemy.sql import column

ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _search_module():
    path = ROOT / "employee_movements" / "search.py"
    spec = importlib.util.spec_from_file_location("employee_movement_search_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_arabic_search_normalizes_alef_marks_tatweel_and_arabic_persian_digits():
    normalizer = _search_module().normalize_search_text
    assert normalizer("أَحْمَد") == normalizer("احمد")
    assert normalizer("آية") == normalizer("ايه") or normalizer("آية") == normalizer("اية")
    assert normalizer("مـحـمـد") == normalizer("محمد")
    assert normalizer("١٢۳٤") == "1234"
    assert normalizer("  محمد   أحمد ") == "محمد احمد"


def test_sql_search_escapes_like_wildcards_and_compiles_for_sqlite():
    search = _search_module().search_contains
    expression = search(column("full_name"), "١٠%_\\")
    sql = str(expression.compile(dialect=sqlite.dialect(), compile_kwargs={"literal_binds": True}))
    assert "ESCAPE" in sql
    assert "%10\\%\\_\\\\%" in sql


def test_home_search_api_is_global_identity_only_and_supports_branch_only_lookup():
    source = _read("employee_movements/blueprints/employees.py")
    start = source.index("def employee_search():")
    end = source.index("@bp.route('/employees'", start)
    block = source[start:end]
    assert "if not (can('manage_employees') or can('view_reports'))" not in block
    assert "len(normalized_q) < 2 and not branch_raw" in block
    assert "employee_search_filter(q, include_contacts=True, include_branch=True)" in block
    assert "rank_scoped_employee_suggestions(q, pool, limit=8)" in block
    assert "Movement.query" not in block
    assert "'company_phone':" in block and "'personal_phone':" in block and "'email':" in block
    assert "'governorate':" in block and "'branch':" in block


def test_main_search_branch_cascade_and_live_results_are_wired_to_real_template_ids():
    js = _read("employee_movements/static/js/app.js")
    home = _read("employee_movements/templates/home_global_search.html")
    assert 'id="homeEmployeeSearchForm"' in home
    assert 'id="homeSearchGovernorate"' in home
    assert 'id="homeSearchBranch"' in home
    assert 'id="homeEmployeeLiveResults"' in home
    assert "function syncHomeSearchBranches()" in js
    assert "option.dataset.governorate===gid" in js
    assert "fetch('/employee-search?'" in js
    assert "const homeSearchForm=qs('#homeEmployeeSearchForm')" in js
    # The obsolete pre-redesign selectors must not return.
    for stale in ("#home_employee_search", "#home_search_results", "#movement-employee-search-form"):
        assert stale not in js


def test_employee_directory_does_not_mistake_a_filtered_subset_for_the_full_directory():
    template = _read("employee_movements/templates/employees.html")
    assert "data-server-query=\"{{q|e}}\"" in template
    assert "initialServerQuery&&q!==initialServerQuery" in template
    assert "النتائج الحالية تخص البحث السابق" in template
    assert "اضغط Enter أو «بحث» لتطبيق البحث الجديد" in template
    source = _read("employee_movements/blueprints/employees.py")
    assert "invalid_q_filter = len(raw_q) > 120" in source
    assert "not (invalid_q_filter or invalid_gov_filter or invalid_branch_filter or invalid_employee_filter)" in source


def test_employee_edit_data_search_is_bounded_normalized_and_active_scope_only():
    source = _read("employee_movements/blueprints/employees.py")
    block = source[source.index("def employee_edit_data():"):source.index("@bp.route('/employees/<int:i>/edit'")]
    assert "Governorate.is_active == True" in block
    assert "employee_search_filter(q, include_contacts=True, include_branch=True)" in block
    assert "rank_scoped_employee_suggestions(q, pool, limit=8)" in block
    assert "invalid_q_filter = len(raw_q) > 120" in block
    assert "for e in rows" not in block
    template = _read("employee_movements/templates/employee_edit_data.html")
    assert 'maxlength="120"' in template
    assert "if filter_error" in template


def test_profile_history_and_delegation_searches_share_normalization_and_empty_states():
    app = _read("employee_movements/static/js/app.js")
    delegation = _read("employee_movements/templates/delegations.html")
    profile = _read("employee_movements/templates/employee.html")
    assert "norm(historySearch?.value)" in app
    assert "historyNo.hidden=shown!==0" in app
    assert 'id="employee_history_search" class="smart-history-search" type="search" maxlength="120"' in profile
    assert delegation.count("id=\"delegationSearch\"") == 1
    assert "const rows = [...document.querySelectorAll('[data-delegation-row]')]" in delegation
    assert "render();" in delegation
    assert "delegationSearchEmpty" in delegation
    title_block = delegation.split("{% block title %}", 1)[1].split("{% endblock %}", 1)[0]
    assert "<script>" not in title_block


def test_generated_smart_table_ids_are_unique_for_accessibility_relationships():
    app = _read("employee_movements/static/js/app.js")
    assert "let generatedSmartTableId=0" in app
    assert "smart-table-search-'+(++generatedSmartTableId)" in app
    assert "while(document.getElementById(candidate))" in app
    assert "input.setAttribute('aria-controls',table.id)" in app


def test_generic_table_search_excludes_action_buttons_and_header_rows():
    app = _read("employee_movements/static/js/app.js")
    lookups = _read("employee_movements/templates/lookups.html")
    assert "!row.querySelector('th')" in app
    assert "!r.querySelector('th')" in app
    utility = _read("employee_movements/static/js/search_utils.js")
    assert "data-search-ignore" in utility
    assert "getEmployeeSearchableRowText" in app
    assert "getEmployeeSearchableRowText" in utility
    assert "selectedOptions" in utility
    assert "fieldValues.push(field.value)" in utility
    assert "if (/اجراء|خيارات|اوامر/.test(lastHeader))" in utility
    assert '<table data-smart-table><tr><th>العنصر</th>' in lookups


def test_movement_list_count_is_unique_by_movement_and_uses_arabic_normalization():
    template = _read("employee_movements/templates/movements.html")
    assert template.count("data-movement-id=\"{{m.id}}\"") == 3
    assert "const totalIds=new Set(allRows.map(row=>row.dataset.movementId).filter(Boolean))" in template
    assert "const visibleIds=new Set(visibleRows.map(row=>row.dataset.movementId).filter(Boolean))" in template
    assert "window.employeeSearchMatches(q,row.dataset.search||((row.dataset.name||'')+' '+(row.dataset.code||'')))" in template
    assert "تعذر تحميل فلاتر الفروع" in template
    assert "لا توجد سجلات مطابقة للمرشحات الحالية." in template


def test_movement_and_home_employee_apis_fail_closed_for_malformed_filters():
    movement = _read("employee_movements/blueprints/movements.py")
    filters = movement[movement.index("def movements_page_filters_api():"):movement.index("@bp.post('/movements/create')")]
    assert "if (gid_raw and not gid_raw.isdigit()) or (bid_raw and not bid_raw.isdigit())" in filters
    assert "return {'branches': [], 'employees': []}" in filters
    picker = movement[movement.index("def movement_employees_api():"):movement.index("@bp.get('/api/movement-preflight')")]
    assert "Employee.branch_id.in_(branch_ids) if branch_ids else False" in picker or "Employee.branch_id.in_(branch_ids) if branch_ids else False" in picker


def test_report_html_and_both_exports_share_fail_closed_cascading_filters():
    source = _read("employee_movements/blueprints/reports.py")
    helper = source[source.index("def _apply_employee_type_report_filters("):source.index("def _report_branch_scope(")]
    assert "query = query.filter(False)" in helper
    assert "filter_error = True" in helper
    assert "selected_branch.governorate_id != selected_gov_id" in helper
    assert "Movement.to_date.is_(None)" in helper
    assert source.count("_apply_employee_type_report_filters(q, mt, bs, request.args)") == 3
    assert "filter_error=filter_error" in source
    assert "bs, _central_report = _report_branch_scope()" in source[source.index("def employee_type_report_xlsx("):]


def test_general_report_invalid_dropdown_values_are_not_ignored_in_html_or_csv():
    source = _read("employee_movements/blueprints/reports.py")
    block = source[source.index("def reports():"):source.index("@bp.get('/reports/<report_type>')")]
    csv_block = source[source.index("def report_csv():"):]
    assert "filter_error = False" in block
    assert "q = q.filter(False)" in block
    assert "filter_error=filter_error" in block
    assert "if status:" in csv_block and "else q.filter(False)" in csv_block
    assert "bs, _central_report = _report_branch_scope()" in csv_block
    template = _read("employee_movements/templates/reports.html")
    assert "if filter_error" in template


def test_all_search_surfaces_have_bounded_inputs_or_native_dropdown_filters():
    templates = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "employee_movements/templates").rglob("*.html"))
    assert 'id="delegationSearch" type="search" maxlength="120"' in templates
    assert 'id="employee_history_search" class="smart-history-search" type="search" maxlength="120"' in templates
    assert 'id="movementRecordsSearch" type="search" maxlength="120"' in templates
    assert 'name="movement_name" value="{{movement_name_query or \'\'}}" type="search" maxlength="120"' in templates
    assert 'name="q" id="employees_search_input" type="search" value="{{q}}" maxlength="120"' in templates


def test_shared_search_utility_loads_before_inline_page_scripts():
    base = _read("employee_movements/templates/base.html")
    assert base.index("js/search_utils.js") < base.index("</head>")
    assert base.index("js/search_utils.js") < base.index("js/app.js")
    assert base.count("js/search_utils.js") == 1


def test_employee_type_reports_use_one_search_over_employee_identity_and_movement_rows():
    template = _read("employee_movements/templates/employee_type_report.html")
    app = _read("employee_movements/static/js/app.js")
    assert 'data-report-search-root' in template
    assert 'data-report-search maxlength="120"' in template
    assert 'data-employee-search=' in template
    assert 'class="ui-table report-movement-table"' in template
    assert 'data-search-ignore' in template
    assert "document.querySelectorAll('[data-report-search-root]')" in app
    assert "window.employeeSearchMatches(q,identity)" in app
    assert "window.employeeSearchMatches(q,rowText)" in app
    assert "تصدير Excel يعتمد على المرشحات أعلاه" in template
