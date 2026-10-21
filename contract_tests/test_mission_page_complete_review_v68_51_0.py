from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "employee_movements" / "templates"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"
QUERY = ROOT / "employee_movements" / "services" / "mission_query.py"
CENTER = TEMPLATES / "mission_reports.html"
CENTER_JS = ROOT / "employee_movements" / "static" / "js" / "mission_center.js"
REPORTS_MISSIONS = TEMPLATES / "reports_missions.html"
MANAGER_HUB = TEMPLATES / "manager_hub.html"


def test_mission_page_printing_is_one_pdf_flow_across_legacy_routes():
    missions = MISSIONS.read_text(encoding="utf-8")
    movements = MOVEMENTS.read_text(encoding="utf-8")
    center = CENTER.read_text(encoding="utf-8")
    assert "url_for('missions.mission_pdf', movement_id=m.id)" in movements.split(
        "def assignment_form(", 1
    )[1].split("@bp.post('/movements/<int:i>/delete')", 1)[0]
    assert "url_for('missions.mission_pdf', movement_id=m.id)" in missions.split(
        "def mission_print(movement_id):", 1
    )[1]
    assert "url_for('missions.mission_pdf', movement_id=m.id, return_to=request.full_path.rstrip('?'))" in center
    assert not (TEMPLATES / "assignment_form.html").exists()
    assert not (TEMPLATES / "mission_print.html").exists()


def test_due_soon_dashboard_link_opens_the_correct_filtered_center():
    query = QUERY.read_text(encoding="utf-8")
    report_page = REPORTS_MISSIONS.read_text(encoding="utf-8")
    assert "follow_up = args.get('follow_up', '').strip()" in query
    assert "if follow_up == '7':" in query
    assert "Movement.to_date <= today + timedelta(days=7)" in query
    assert "?follow_up=7" in report_page
    assert "?duration=open" in report_page
    assert "governorate_id={{ selected_governorate.id }}" in report_page


def test_hidden_or_collapsed_mission_selection_is_cleared_before_actions():
    js = CENTER_JS.read_text(encoding="utf-8")
    assert "new MutationObserver" in js
    assert "attributeFilter: ['hidden']" in js
    assert "if (selected && selected.hidden) clearSelection();" in js
    assert "tableSearch?.addEventListener('input', clearSelection)" not in js


def test_pending_edit_request_is_shown_and_cannot_be_submitted_twice_from_center():
    query = QUERY.read_text(encoding="utf-8")
    center = CENTER.read_text(encoding="utf-8")
    js = CENTER_JS.read_text(encoding="utf-8")
    assert "pending_edit_request_movement_ids" in query
    assert "m.id not in pending_edit_request_movement_ids" in center
    assert "طلب تعديل قيد المراجعة" in center
    assert "hasPendingEditRequest" in js
    assert "لن يُسمح بإنشاء طلب مكرر" in js


def test_mission_edit_returns_to_existing_filter_set_after_save_or_validation_error():
    route = MISSIONS.read_text(encoding="utf-8")
    center = CENTER.read_text(encoding="utf-8")
    edit = (TEMPLATES / "mission_edit.html").read_text(encoding="utf-8")
    assert "return_to=_mission_center_return_url()" in route
    assert "return_to=_mission_center_return_url(request.form.get('return_to'))" in route
    assert "return_to=request.full_path.rstrip('?')" in center
    assert 'name="return_to" value="{{return_to}}"' in edit
    assert 'href="{{return_to}}"' in edit


def test_filter_date_values_are_normalized_and_related_objects_eager_loaded():
    query = QUERY.read_text(encoding="utf-8")
    assert "date_from, date_to = df.isoformat(), dt.isoformat()" in query
    assert "if date_from and df is None:" in query
    assert "if date_to and dt is None:" in query
    assert "joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate)" in query
    assert "joinedload(Movement.destination).joinedload(Branch.governorate)" in query


def test_manager_hub_does_not_repeat_the_same_header_shortcuts_above_the_cards():
    hub = MANAGER_HUB.read_text(encoding="utf-8")
    header = hub.split("</section>", 1)[0]
    assert 'href="/reports/assignments/edit-requests"' not in header
    assert 'href="/reports/assignments/monthly"' not in header
    assert 'href="/reports/assignments/edit-requests"' in hub
    assert 'href="/reports/assignments/monthly"' in hub


def test_due_soon_filter_excludes_closed_missions_using_current_and_legacy_states():
    query = QUERY.read_text(encoding="utf-8")
    assert "assignment_open_filter(Movement)" in query
    assert "from ..movement_state import assignment_closed_filter, assignment_open_filter" in query


def test_open_mission_print_date_preserves_center_filters():
    route = MISSIONS.read_text(encoding="utf-8")
    print_date = (TEMPLATES / "mission_print_date.html").read_text(encoding="utf-8")
    assert "return_to=_mission_center_return_url()" in route
    assert 'href="{{return_to}}"' in print_date
    assert 'name="return_to" value="{{return_to}}"' in print_date
    assert "mission_pdf', movement_id=m.id, return_to=request.full_path.rstrip('?')" in (TEMPLATES / "mission_reports.html").read_text(encoding="utf-8")
    assert "return_to=_mission_center_return_url(request.form.get('return_to'))" in route


def test_mission_center_has_no_hidden_single_value_status_filter():
    query = QUERY.read_text(encoding="utf-8")
    center = CENTER.read_text(encoding="utf-8")
    assert "args.get('status'" not in query
    assert "Movement.status == status" not in query
    assert "'status': status" not in query
    assert 'name="mission_state"' in center


def test_dashboard_due_soon_counter_uses_the_same_closed_state_rules_as_center():
    reports = (ROOT / "employee_movements" / "blueprints" / "reports.py").read_text(encoding="utf-8")
    assert "follow_up_condition = and_(" in reports
    assert "follow_up_count'" in reports
    assert "One conditional aggregate replaces eight independent COUNT round-trips." in reports
    assert "assignment_open_filter(Movement)" in reports
    assert "from ..movement_state import assignment_closed_filter, assignment_open_filter" in reports


def test_action_confirm_does_not_block_submission_after_global_busy_handler_disables_button():
    js = CENTER_JS.read_text(encoding="utf-8")
    assert "if (!window.confirm('هل تريد إغلاق المأمورية المختارة?" not in js
    assert "if (!window.confirm('هل تريد إغلاق المأمورية المختارة؟ لن يتم تنفيذ الإغلاق" in js
    assert "if (!window.confirm('هل تريد إعادة فتح المأمورية المختارة؟')) event.preventDefault();" in js
    assert "closeButton?.disabled ||" not in js
    assert "reopenButton?.disabled ||" not in js


def test_closed_state_display_filters_and_monthly_report_share_legacy_closure_rule():
    documents = (ROOT / "employee_movements" / "services" / "mission_documents.py").read_text(encoding="utf-8")
    query = QUERY.read_text(encoding="utf-8")
    route = MISSIONS.read_text(encoding="utf-8")
    assert "if movement_is_closed(mission):" in documents
    assert "assignment_closed_filter(Movement)" in query
    assert "from ..movement_state import assignment_closed_filter, assignment_open_filter" in query
    assert "assignment_closed_filter(Movement)" in route
    assert "from ..movement_state import assignment_open_filter, assignment_closed_filter" in route or "from ..movement_state import assignment_closed_filter" in route


def test_reopening_legacy_closed_mission_clears_legacy_closed_flag():
    lifecycle = (ROOT / "employee_movements" / "services" / "mission_lifecycle.py").read_text(encoding="utf-8")
    assert "if getattr(movement, 'assignment_state', None) == 'مغلق':" in lifecycle
    assert "movement.assignment_state = 'ساري'" in lifecycle
    assert "final_state == 'تحت التحرير' and getattr(movement, 'assignment_state', None) == 'مغلق'" in lifecycle


def test_edit_request_uniqueness_is_limited_to_pending_missions_and_migrates_old_constraint():
    model = (ROOT / "employee_movements" / "models.py").read_text(encoding="utf-8")
    bootstrap = (ROOT / "employee_movements" / "bootstrap.py").read_text(encoding="utf-8")
    assert "uq_mission_edit_request_pending" in model
    assert "sqlite_where=text(\"status = 'قيد المراجعة'\")" in model
    assert "postgresql_where=text(\"status = 'قيد المراجعة'\")" in model
    assert "UniqueConstraint('movement_id', 'status', name='uq_mission_edit_request_status')" not in model
    assert "def _ensure_pending_mission_edit_request_index():" in bootstrap
    assert "ALTER TABLE mission_edit_request DROP CONSTRAINT IF EXISTS" in bootstrap
    assert "ALTER TABLE {table_name} RENAME TO {backup_table}" in bootstrap
    assert "_ensure_pending_mission_edit_request_index()" in bootstrap


def test_closed_mission_lifecycle_is_enforced_across_movement_actions_without_duplicate_edit_links():
    movements = MOVEMENTS.read_text(encoding="utf-8")
    reports = (ROOT / "employee_movements" / "blueprints" / "reports.py").read_text(encoding="utf-8")
    actions = (TEMPLATES / "partials" / "movement_actions.html").read_text(encoding="utf-8")
    assert "from ..access import" in movements and "movement_is_closed" in movements
    assert "if m.movement_type == 'انتداب' and movement_is_closed(m)" in movements
    assert "if movement_is_closed(m):" in movements
    reopen_body = movements.split("def reopen_assignment(", 1)[1].split("@bp.get('/movements/<int:i>/assignment-form')", 1)[0]
    assert "إعادة الفتح المباشر غير متاحة" in reopen_body
    assert "mission_is_closed = m.assignment_state == 'مغلق' or m.mission_state == 'مغلقة'" in actions
    assert "تعديل / تمديد الانتداب" in actions
    assert "تعديل الحركة{% endif %}</a>" in actions
    assert "assignment_closed_filter(Movement)" in reports
    assert "Movement.to_date.is_(None)," in reports
    assert "assignment_open_filter(Movement)" in reports


def test_legacy_closed_mission_state_is_used_in_excel_export_and_edit_header():
    routes = MISSIONS.read_text(encoding="utf-8")
    documents = (ROOT / "employee_movements" / "services" / "mission_documents.py").read_text(encoding="utf-8")
    edit_template = (TEMPLATES / "mission_edit.html").read_text(encoding="utf-8")
    assert "mission_state_label(mission)," in documents
    assert "mission_display_state=mission_state_label(m)" in routes
    assert "الحالة الحالية: <strong>{{mission_display_state}}</strong>" in edit_template
    assert "المأمورية مغلقة — البيانات للعرض فقط" in edit_template
    assert "يتولى الـManager إرفاق الصورة أو استبدالها" in edit_template
