"""Source contracts for Phase 2 Excel integrity and large-list performance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTER = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
EXCEL_APPLY = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
EXCEL_TEMPLATE = (ROOT / "employee_movements/templates/excel_import.html").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/blueprints/employees.py").read_text(encoding="utf-8")
EMPLOYEE_TEMPLATE = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")
MISSION_QUERY = (ROOT / "employee_movements/services/mission_query.py").read_text(encoding="utf-8")
MISSION_TEMPLATE = (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")


def test_branch_import_code_is_authoritative_and_normalized_before_name_fallback():
    assert "branch_codes_by_gov" in IMPORTER
    assert "existing_codes = branch_codes_by_gov.get(governorate.id, {}).get(code_key, [])" in IMPORTER
    assert "The normalized branch code is authoritative" in IMPORTER
    assert "len(existing_codes) > 1" in IMPORTER
    assert "pending_branch_codes" in IMPORTER
    assert "pending_branch_names" in IMPORTER
    assert "seen_branch_targets" in IMPORTER


def test_new_excel_rows_are_explicitly_selectable_and_existing_updates_are_opt_in():
    assert 'name="change" value="{{a.type}}:{{a.row}}" checked' in EXCEL_TEMPLATE
    assert 'name="change" value="{{a.type}}:{{a.id}}:{{a.row}}:{{f}}">' in EXCEL_TEMPLATE
    assert "employee_match" in EXCEL_TEMPLATE and "branch_match" in EXCEL_TEMPLATE
    assert "build_excel_import_selection_plan(" in IMPORTER
    assert "selection_plan.is_selected_add(a)" in EXCEL_APPLY
    assert "selection_plan.selected_fields(a)" in EXCEL_APPLY


def test_excel_preview_uses_streamed_scalar_identity_rows_and_batch_collision_validation():
    assert "Employee.id, Employee.branch_id, Employee.full_name, Employee.job_code, Employee.email" in IMPORTER
    assert ").yield_per(2000)" in IMPORTER
    assert "employee_identity_by_id" in IMPORTER
    assert "TicketEmployeeCodeAlias.alias_text" in EXCEL_APPLY
    assert "TicketEmployeeCodeAlias.normalized_alias.in_(" not in EXCEL_APPLY
    assert "func.lower(func.trim(Employee.email)).in_(chunk)" in EXCEL_APPLY
    assert "Selected Excel rows contain duplicate or conflicting personnel codes" in EXCEL_APPLY


def test_employee_directory_uses_server_side_count_and_page_window():
    route = EMPLOYEES.split("def employees():", 1)[1].split("@bp.", 1)[0]
    assert "employee_server_paginated = not employee_filter" in route
    assert "query = query.filter(Employee.id == int(employee_filter))" in route
    assert "latest_current_assignment_id" in route
    assert "select(func.max(Movement.id))" in route
    assert "current_assignment_row.destination_branch_id == int(branch_filter)" in route
    assert "employee_is_effectively_in_branch(e, int(branch_filter))" not in route
    assert "employee_query_total = query.count()" in route
    assert ".limit(employee_page_size).offset(" in route
    assert "class=\"ui-pagination smart-directory-pagination\"" in EMPLOYEE_TEMPLATE
    assert "employee_next_page_url" in EMPLOYEE_TEMPLATE


def test_mission_report_paginates_in_sql_and_does_not_render_every_employee_option():
    assert "total_rows = q.order_by(None).count()" in MISSION_QUERY
    assert "rows_query = rows_query.limit(page_size).offset((page - 1) * page_size)" in MISSION_QUERY
    assert "selected_employee_object = employees_q.filter(Employee.id == int(employee)).first()" in MISSION_QUERY
    assert "missionEmployeeLookup" in MISSION_TEMPLATE
    assert "employee_search" not in MISSION_QUERY
    assert "MissionEditRequest.movement_id.in_(page_movement_ids)" in MISSION_QUERY


def test_indexes_are_idempotent_and_committed_schema_changes_precede_concurrent_creation():
    assert "ix_employee_branch_active_name" in BOOTSTRAP
    assert "ix_movement_employee_active_from" in BOOTSTRAP
    assert "CREATE INDEX CONCURRENTLY IF NOT EXISTS" in BOOTSTRAP
    position_commit = BOOTSTRAP.index("db.session.commit()", BOOTSTRAP.index("def ensure_schema():"))
    position_index = BOOTSTRAP.index("_ensure_performance_indexes()", BOOTSTRAP.index("def ensure_schema():"))
    assert position_commit < position_index


def test_mission_employee_autocomplete_requires_selection_and_uses_text_content():
    source = (ROOT / "employee_movements/static/js/mission_center.js").read_text(encoding="utf-8")
    assert "function initMissionEmployeeSearch()" in source
    assert "input.setCustomValidity('اختر موظفًا من قائمة نتائج البحث" in source
    assert "option.textContent =" in source
    assert "AbortController" in source


def test_mission_export_streams_query_and_uses_write_only_workbook():
    documents = (ROOT / "employee_movements/services/mission_documents.py").read_text(encoding="utf-8")
    assert "total_rows = q.order_by(None).count() if (paginate or include_total) else None" in MISSION_QUERY
    assert "rows = rows_query.yield_per(500)" in MISSION_QUERY
    assert "Workbook(write_only=True)" in documents
    assert "tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')" in documents
    assert "from openpyxl.cell import WriteOnlyCell" in documents
    assert "for mission in iterator:" in documents
    assert "list(islice(iterator, 200))" in documents
    assert documents.index("ws.column_dimensions[get_column_letter(index)].width = width") < documents.index("ws.append(header_cells)")
    assert "Workbook(write_only=True)" in documents
