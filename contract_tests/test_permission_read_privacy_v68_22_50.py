from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMPLOYEES = (ROOT / "employee_movements" / "blueprints" / "employees.py").read_text(encoding="utf-8")
EMPLOYEE_TEMPLATE = (ROOT / "employee_movements" / "templates" / "employee.html").read_text(encoding="utf-8")
EMPLOYEE_LIST_TEMPLATE = (ROOT / "employee_movements" / "templates" / "employees.html").read_text(encoding="utf-8")
AGENT = (ROOT / "employee_movements" / "assistant" / "agent.py").read_text(encoding="utf-8")
VISIBILITY = (ROOT / "employee_movements" / "assistant" / "visibility.py").read_text(encoding="utf-8")
RENDER = (ROOT / "employee_movements" / "assistant" / "render.py").read_text(encoding="utf-8")
REPORTS = (ROOT / "employee_movements" / "blueprints" / "reports.py").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
NOTIFICATIONS = (ROOT / "employee_movements" / "blueprints" / "notifications.py").read_text(encoding="utf-8")


def _block(source, start_marker, end_marker):
    start = source.index(start_marker)
    end = source.index(end_marker, start + len(start_marker))
    return source[start:end]


def test_global_home_search_requires_directory_or_report_permission():
    block = _block(EMPLOYEES, "def employee_search():", "@bp.route('/employees'")
    assert "if not (can('manage_employees') or can('view_reports'))" in block
    # Live home suggestions return identity fields only; movement records are
    # intentionally not fetched merely to populate a search result.
    assert "search_contains(Employee.full_name, q)" in block
    assert "search_contains(Employee.job_code, q)" in block
    assert "Movement.query" not in block
    assert "'last_assignment'" not in block


def test_employee_card_requires_permission_and_does_not_load_history_without_reports():
    block = EMPLOYEES[EMPLOYEES.index("def employee_card(i):"): ]
    assert "if not (can('manage_employees') or can_read_movement_details)" in block
    assert "Movement.query.filter_by(employee_id=i, is_active=True)" in block
    assert "if can_read_movement_details else None" in block
    assert "ms = []" in block
    assert "can_view_movement(mv)" in block


def test_employee_card_template_hides_operational_history_without_report_permission():
    assert "{% if can('view_reports') %}" in EMPLOYEE_TEMPLATE
    assert "{% if can('manage_employees') %}" in EMPLOYEE_TEMPLATE
    assert "{% if can('manage_movements') and can_manage_movement(m) %}" in EMPLOYEE_TEMPLATE


def test_assistant_read_tools_require_capability_and_scope():
    assert "if not (can(\"manage_employees\") or can(\"view_reports\"))" in AGENT
    assert "if not can(\"view_reports\")" in AGENT
    assert "if not visible_movement(m)" in AGENT
    assert "return bool(branch_ok(employee.branch_id))" in VISIBILITY


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
    assert "if field in ('status', 'last_leave', 'last_assignment', 'last_permission', 'movements') and not can_read_movement_details" in RENDER
    assert "ms = [m for m in candidate_movements if visible_movement(m)]" in RENDER


def test_employee_excel_template_includes_optional_branch_code_and_safe_name_fallback():
    importer = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "'كود الفرع'," in importer
    assert "'255'," not in importer
    assert "'أحمد محمد'," not in importer
    assert "'مثال: سوهاج'" not in importer
    assert "name_matches = branches_by_name.get(name_key, []) if name_key else []" in importer
    assert "return name_matches[0], 'unique_name_without_governorate'" in importer
    assert "return None, 'ambiguous_name'" in importer
    assert "# A known governorate is part of the user's intended target" in importer


def test_employees_directory_is_capability_gated_and_respects_operational_scope():
    block = _block(EMPLOYEES, "def employees():", "@bp.get('/employees/edit-data')")
    assert "if not (can('manage_employees') or can('view_reports'))" in block
    assert "search_branch_ids = set(bs or [])" in block
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
    branch_search = _block(AGENT, 'if name == "search_branches":', 'if name == "search_governorates":')
    gov_search = _block(AGENT, 'if name == "search_governorates":', 'if name == "search_movements":')
    movement_search = _block(AGENT, 'if name == "search_movements":', 'if name == "navigate_to":')
    assert "'Manager Application Support' in roles()" in branch_search
    assert "'Manager Application Support'}):" in gov_search
    assert "current_roles & {'مشرف محافظة', 'Manager Application Support'}" in movement_search


def test_assistant_employee_phone_search_requires_employee_management_permission():
    block = _block(AGENT, 'if name == "search_employees":', 'if name == "get_employee_profile":')
    assert 'if can("manage_employees"):' in block
    assert 'Employee.company_phone.ilike(pattern)' in block
    assert 'Employee.personal_phone.ilike(pattern)' in block
    assert 'db.or_(*search_fields)' in block


def test_current_employee_status_edit_link_is_permission_gated():
    assert "current_status.movement and can('manage_movements') and can_manage_movement(current_status.movement)" in EMPLOYEE_TEMPLATE


def test_assistant_movement_search_filters_work_scope_before_limiting_results():
    block = _block(AGENT, 'if name == "search_movements":', 'if name == "navigate_to":')
    assert "target_date = date.fromisoformat(date_filter)" in block
    assert "Movement.from_date == target_date" in block
    assert "Movement.movement_type == 'انتداب'" in block
    assert "Employee.branch_id.in_(allowed_branches)" in block
    assert "limit(result_limit).all()" in block
    assert "limit(60).all()" not in block


def test_operational_reports_use_selected_governorate_for_admin_and_manager():
    scope = _block(REPORTS, "def _report_branch_scope():", "@bp.get('/manager')")
    assert "allowed_gov_ids = set(gids())" in scope
    assert "if not allowed_gov_ids:" in scope
    assert "Branch.governorate_id.in_(allowed_gov_ids)" in scope
    assert "Manager/Admin reports default to all active governorates" not in scope
    assert "manager_global_report=is_central_manager and selected_governorate is None" in REPORTS
    assert "allowed_gov_ids = set(gids())" in REPORTS


def test_employee_type_report_swaps_reversed_date_range_once():
    block = _block(REPORTS, "def _apply_employee_type_report_filters(", "def _report_branch_scope(")
    assert "date_from_obj, date_to_obj = date_to_obj, date_from_obj" in block
    assert "date_from, date_to = date_to, date_from" in block
    assert block.count("date_from_obj, date_to_obj = date_to_obj, date_from_obj") == 1


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


def test_movements_worklist_is_limited_to_selected_work_governorate_for_all_roles():
    from pathlib import Path
    constants = (ROOT / "employee_movements" / "constants.py").read_text(encoding="utf-8")
    block = _block(MOVEMENTS, "def movements():", "@bp.route('/movements/<int:i>/edit'")
    assert "bs = bids()" in block
    assert "Employee.branch_id.in_(bs)" in block
    assert "if bs else []" in block
    assert "Movement.movement_type == 'انتداب',\n                    Employee.branch_id.in_(bs)" not in block
    assert "'movements.movements'" in constants


def test_notification_json_endpoints_inherit_operational_scope():
    constants = (ROOT / "employee_movements" / "constants.py").read_text(encoding="utf-8")
    assert "'notifications.notifications_items'" in constants
    assert "'notifications.notifications_summary'" in constants
    assert "'notifications.notifications'" in constants


def test_home_live_status_board_requires_report_permission_and_filters_each_movement():
    dashboard = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    home_template = (ROOT / "employee_movements" / "templates" / "home.html").read_text(encoding="utf-8")
    block = _block(dashboard, "if bs and can('view_reports'):", "# قوائم الصفحة الرئيسية لا تعرض إلا المحافظات")
    assert "if bs and can('view_reports'):" in block
    assert "can_view_movement(r['movement'])" in block
    assert "if branch_employee_ids and can('view_reports'):" in dashboard
    assert "if can('view_reports')" in home_template
    assert "تحتاج إلى صلاحية التقارير لعرض الحالة الحالية للموظفين." in home_template


def test_home_does_not_load_unused_selected_employee_history():
    dashboard = (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    block = _block(dashboard, "def home():", "# Governorates visible to the current effective role.")
    assert "Movement.query.filter_by(employee_id=movement_employee.id" not in block
    assert "not render the selected employee's history" in dashboard


def test_movement_filter_api_uses_global_scope_only_for_assignment_workflow():
    block = _block(MOVEMENTS, "def movements_page_filters_api():", "@bp.post('/movements/create')")
    assert "movement_type == 'انتداب'" in block
    assert "bool(rs & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'})" in block
    assert "else set(gids())" in block
