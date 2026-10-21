from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMPLOYEES = (ROOT / "employee_movements" / "blueprints" / "employees.py").read_text(encoding="utf-8")
EMPLOYEE_TEMPLATE = (ROOT / "employee_movements" / "templates" / "employee.html").read_text(encoding="utf-8")
EMPLOYEE_LIST_TEMPLATE = (ROOT / "employee_movements" / "templates" / "employees.html").read_text(encoding="utf-8")
AGENT = (ROOT / "employee_movements" / "assistant" / "agent.py").read_text(encoding="utf-8")
READ_TOOLS = (ROOT / "employee_movements" / "assistant" / "tool_read_handlers.py").read_text(encoding="utf-8")
VISIBILITY = (ROOT / "employee_movements" / "assistant" / "visibility.py").read_text(encoding="utf-8")
RENDER = (ROOT / "employee_movements" / "assistant" / "render_read.py").read_text(encoding="utf-8")
READ_DIRECTORY = (ROOT / "employee_movements" / "assistant" / "read_directory_handlers.py").read_text(encoding="utf-8")
READ_MOVEMENTS = (ROOT / "employee_movements" / "assistant" / "read_movement_handlers.py").read_text(encoding="utf-8")
REPORTS = (ROOT / "employee_movements" / "blueprints" / "reports.py").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
NOTIFICATIONS = (ROOT / "employee_movements" / "blueprints" / "notifications.py").read_text(encoding="utf-8")


def _block(source, start_marker, end_marker):
    start = source.index(start_marker)
    end = source.index(end_marker, start + len(start_marker))
    return source[start:end]


def test_global_home_search_is_shared_and_includes_a_compact_latest_assignment_summary():
    block = _block(EMPLOYEES, "def employee_search():", "@bp.route('/employees'")
    assert "if not (can('manage_employees') or can('view_reports'))" not in block
    assert "employee_search_filter(q, include_contacts=True, include_branch=True)" in block
    assert "rank_scoped_employee_suggestions(q, pool, limit=8)" in block
    assert "'company_phone'" in block and "'personal_phone'" in block and "'email'" in block
    assert "Movement.query" not in block
    assert "latest_assignment_summaries({e.id for e in rows})" in block
    assert "'last_assignment': latest_by_employee.get(e.id, {}).get('text', '')" in block


def test_employee_card_shares_employee_data_but_does_not_load_history_without_reports():
    block = EMPLOYEES[EMPLOYEES.index("def employee_card(i):"): ]
    assert "if not (can('manage_employees') or can_read_movement_details)" not in block
    assert "Movement.query.filter_by(employee_id=i, is_active=True)" in block
    assert "if can_read_movement_details else None" in block
    assert "ms = []" in block
    assert "can_view_movement(mv)" in block


def test_employee_card_template_hides_operational_history_without_report_permission():
    assert "{% if can('view_reports') %}" in EMPLOYEE_TEMPLATE
    assert "can_manage_employee(e) and can('manage_employees')" in EMPLOYEE_TEMPLATE
    assert "{% if can('manage_movements') and can_manage_movement(m) %}" in EMPLOYEE_TEMPLATE


def test_assistant_read_tools_require_capability_and_allow_global_read_scope():
    assert "if not (can(\"manage_employees\") or can(\"view_reports\"))" in READ_TOOLS
    assert "if not can(\"view_reports\")" in READ_TOOLS
    assert "if not visible_movement(m)" in READ_TOOLS
    assert "branch = getattr(employee, 'branch', None)" in VISIBILITY
    assert "governorate.is_active" in VISIBILITY
    assert "work governorate limits mutations" in VISIBILITY
    assert "return bool(branch and branch.is_active and governorate and governorate.is_active)" in VISIBILITY


def test_live_tool_results_are_not_round_tripped_to_gemini():
    run = AGENT[AGENT.index("def run_agent("): ]
    assert "response = _call_gemini(contents, context)" in run
    assert run.count("_call_gemini(") == 1
    assert "contents.append(" not in run
    assert "functionResponse" not in run
    assert "formatted into the user-visible reply locally" in run


def test_external_model_context_redacts_selected_record_ids():
    call = _block(AGENT, "def _call_gemini(", "def _tool_result_response(")
    assert '"selected": {' in call
    assert "key: True for key, value in (context.get(\"selected\", {}) or {}).items()" in call
    assert "json.dumps(model_context, ensure_ascii=False)" in call
    assert "json.dumps(context, ensure_ascii=False)" not in call


def test_render_read_gates_histories_and_filters_each_movement():
    assert "if intent in report_intents and not can('view_reports')" in RENDER
    assert "if field in ('status', 'last_leave', 'last_assignment', 'last_permission', 'movements') and not can_read_movement_details" in READ_DIRECTORY
    assert "ms = [m for m in candidate_movements if visible_movement(m)][:20]" in READ_DIRECTORY
    assert "ms = [m for m in candidates if visible_movement(m)][:30]" in READ_MOVEMENTS


def test_employee_excel_template_includes_optional_branch_code_and_safe_name_fallback():
    importer = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "'كود الفرع'," in importer
    assert "'255'," not in importer
    assert "'أحمد محمد'," not in importer
    assert "'مثال: سوهاج'" not in importer
    matcher = (ROOT / "employee_movements" / "services" / "excel_import_matching.py").read_text(encoding="utf-8")
    assert "name_matches = branches_by_name.get(name_key, []) if name_key else []" in matcher
    assert "return name_matches[0], 'unique_name_without_governorate'" in matcher
    assert "return None, 'ambiguous_name'" in matcher
    assert "# A known governorate is part of the user's intended target" in matcher


def test_employees_directory_reads_globally_but_mutations_respect_operational_scope():
    block = _block(EMPLOYEES, "def employees():", "@bp.get('/employees/edit-data')")
    assert "if not (can('manage_employees') or can('view_reports'))" in block
    assert "search_branch_ids = {" in block
    assert "Branch.is_active == True, Governorate.is_active == True" in block
    assert "Employee.branch_id.in_(selected_branch_ids)" in block
    assert "supervisor_search_all" not in block
    assert "scope_governorates = scope_governorates_for_user()" in block
    assert "scope_governorates=scope_governorates" in block


def test_employee_directory_status_is_not_loaded_without_report_permission():
    block = _block(EMPLOYEES, "# حالة الحركة لكل موظف", "# عرض الموظفين يكون مجمعًا")
    assert "if rows and can('view_reports')" in block
    assert "movement_candidates" in block
    assert "if can_view_movement(m)" in block
    assert "{% if can('view_reports') %}" in EMPLOYEE_TEMPLATE
    assert "الحالة غير متاحة دون صلاحية التقارير" in EMPLOYEE_LIST_TEMPLATE


def test_assistant_manager_can_discover_global_governorates_and_assignment_branches():
    branch_search = _block(READ_TOOLS, 'if name == "search_branches":', 'if name == "search_governorates":')
    gov_search = _block(READ_TOOLS, 'if name == "search_governorates":', 'if name == "search_movements":')
    movement_search = _block(READ_TOOLS, 'if name == "search_movements":', '    return None')
    assert "Governorate.is_active == True" in branch_search
    assert "Branch.is_active == True" in branch_search
    assert "Governorate.query.filter(Governorate.is_active == True)" in gov_search
    assert "Read-only movement search is global across active governorates." in movement_search
    assert "allowed_branches = bids()" not in movement_search


def test_assistant_employee_contact_search_is_available_in_shared_read_scope():
    block = _block(READ_TOOLS, 'if name == "search_employees":', 'if name == "get_employee_profile":')
    assert 'if not (can("manage_employees") or can("view_reports")):' in block
    assert 'include_contacts=can("view_reports")' in block
    # Employee contacts are part of the shared employee directory read policy.
    assert 'employee_search_filter(' in block
    assert 'include_contacts=can("view_reports")' in block
    assert 'Employee.company_phone.ilike(pattern)' not in block
    assert 'Employee.personal_phone.ilike(pattern)' not in block


def test_current_employee_status_edit_link_is_permission_gated():
    assert "current_status.movement and can('manage_movements') and can_manage_movement(current_status.movement)" in EMPLOYEE_TEMPLATE


def test_assistant_movement_search_is_global_read_before_limiting_results():
    block = _block(READ_TOOLS, 'if name == "search_movements":', '    return None')
    assert "target_date = date.fromisoformat(date_filter)" in block
    assert "Movement.from_date == target_date" in block
    assert "Read-only movement search is global across active governorates." in block
    assert "Branch.is_active == True" in block
    assert "Governorate.is_active == True" in block
    assert "Movement.query.join(Employee).join(Branch, Employee.branch_id == Branch.id)" in block
    assert "allowed_branches = bids()" not in block
    assert "limit(result_limit).all()" in block
    assert "limit(60).all()" not in block


def test_read_only_reports_are_global_while_mutations_remain_work_governorate_scoped():
    scope = _block(REPORTS, "def _report_branch_scope():", "@bp.get('/manager')")
    assert "All signed-in operational roles can read reports across active governorates." in scope
    assert "Governorate.is_active == True" in scope
    assert "if raw_gid:" in scope
    assert "Branch.governorate_id == governorate.id" in scope
    assert "manager_global_report=selected_governorate is None" in REPORTS
    access = (ROOT / "employee_movements" / "access.py").read_text(encoding="utf-8")
    assert "selected = scope_governorate_id()" in access
    assert "branch.governorate_id != int(selected)" in access
    assert "not branch_ok(branch.id)" in access


def test_employee_type_report_reversed_date_range_fails_closed_without_rewriting_input():
    block = _block(REPORTS, "def _apply_employee_type_report_filters(", "def _report_branch_scope(")
    assert "date_range_error = bool(date_from_obj and date_to_obj and date_from_obj > date_to_obj)" in block
    assert "if date_range_error:" in block
    assert "query = query.filter(False)" in block
    assert "filter_error = True" in block
    assert "date_from_obj, date_to_obj = date_to_obj, date_from_obj" not in block
    assert "date_from, date_to = date_to, date_from" not in block


def test_movement_list_and_filter_api_require_read_or_movement_management_access():
    listing = _block(MOVEMENTS, "def movements():", "@bp.route('/movements/<int:i>/edit'")
    filters_api = _block(MOVEMENTS, "def movements_page_filters_api():", "@bp.post('/movements/create')")
    assert "if not (can('view_reports') or can('manage_movements'))" in listing
    assert "if not (can('view_reports') or can('manage_movements'))" in filters_api

def test_preflight_and_employee_picker_do_not_expose_unreadable_movement_details():
    preflight = _block(MOVEMENTS, "def movement_preflight_api():", "@bp.get('/api/movements-page-filters')")
    filters_api = _block(MOVEMENTS, "def movements_page_filters_api():", "@bp.post('/movements/create')")
    assert "current_readable" in preflight
    assert "if current and current_readable" in preflight
    assert "if current and current_readable else None" in preflight
    assert "can_view_movement(current)" in filters_api
    assert "can_manage_movement(current)" in filters_api

def test_notifications_page_and_json_apis_are_permission_gated():
    for marker in ["def notifications():", "def notifications_items():", "def notifications_summary():"]:
        assert "if not (can('view_reports') or can('manage_movements'))" in NOTIFICATIONS[NOTIFICATIONS.index(marker):]


def test_transactional_employee_picker_requires_movement_write_permission_but_home_search_stays_global():
    block = _block(MOVEMENTS, "def movement_employees_api():", "@bp.get('/api/movement-preflight')")
    assert "if movement_type and (not can('manage_movements') or not can_manage_movement())" in block
    assert "global_home_search = bool(q) and not movement_type" in block
    assert "Employee.personal_phone" not in block
    assert "Employee.company_phone" not in block


def test_overlap_conflict_messages_do_not_disclose_hidden_movement_type_or_state():
    validation = (ROOT / "employee_movements" / "validation.py").read_text(encoding="utf-8")
    assert "OVERLAP_CONFLICT_MESSAGE = 'تتعارض بيانات الحركة مع حركة نشطة مسجلة للموظف؛ لا يمكن الحفظ.'" in validation
    assert "يوجد انتداب مفتوح للموظف" not in validation
    assert "يتعارض مع إذن" not in validation
    assert "يوجد إذن آخر للموظف" not in validation


def test_movements_worklist_is_global_read_with_selected_scope_for_write_controls():
    from pathlib import Path
    constants = (ROOT / "employee_movements" / "constants.py").read_text(encoding="utf-8")
    block = _block(MOVEMENTS, "def movements():", "@bp.route('/movements/<int:i>/edit'")
    assert "bs = bids()" in block
    assert "if bs else []" in block
    assert "def movement_log_query():" in block
    assert ".join(Branch, Branch.id == Employee.branch_id)" in block
    assert "total_records = log_query.order_by(None).count()" in block
    assert ".limit(movement_page_size)" in block
    assert "Governorate.is_active == True" in block
    assert "Employee.branch_id.in_(bs)" not in block
    assert "'movements.movements'" in constants


def test_notification_json_endpoints_inherit_operational_scope():
    constants = (ROOT / "employee_movements" / "constants.py").read_text(encoding="utf-8")
    assert "'notifications.notifications_items'" in constants
    assert "'notifications.notifications_summary'" in constants
    assert "'notifications.notifications'" in constants


def test_home_live_status_board_requires_report_permission_and_filters_each_movement():
    dashboard = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    home_template = (ROOT / "employee_movements" / "templates" / "home.html").read_text(encoding="utf-8")
    block = _block(dashboard, "if read_branch_ids and can('view_reports'):", "# قوائم الصفحة الرئيسية لا تعرض إلا المحافظات")
    assert "if read_branch_ids and can('view_reports'):" in block
    assert "current_employee_status_rows(read_branch_ids, today)" in block
    assert "can_view_movement(r['movement'])" in block
    assert "if branch_employee_ids and can('view_reports'):" in dashboard
    assert "if can('view_reports')" in home_template
    assert "تحتاج إلى صلاحية التقارير لعرض الحالة الحالية للموظفين." in home_template


def test_home_does_not_load_unused_selected_employee_history():
    dashboard = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    block = _block(dashboard, "def home():", "# Employee/movement reading is global for every official login role.")
    assert "Movement.query.filter_by(employee_id=movement_employee.id" not in block
    assert "Only a compact latest-assignment summary is loaded into search results." in dashboard


def test_movement_filter_api_uses_global_scope_only_for_assignment_workflow():
    block = _block(MOVEMENTS, "def movements_page_filters_api():", "@bp.post('/movements/create')")
    assert "global_read_filter = not movement_type" in block
    assert "if global_read_filter" in block
    assert "else set(gids())" in block
    assert "else set(bids())" in block
