from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = (ROOT / "employee_movements/access.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "employee_movements/constants.py").read_text(encoding="utf-8")
DASHBOARD = (ROOT / "employee_movements/blueprints/dashboard.py").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/blueprints/employees.py").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
REPORTS = (ROOT / "employee_movements/blueprints/reports.py").read_text(encoding="utf-8")
MISSIONS = (ROOT / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
USERS_TEMPLATE = (ROOT / "employee_movements/templates/users.html").read_text(encoding="utf-8")
USER_EDIT_TEMPLATE = (ROOT / "employee_movements/templates/user_edit.html").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")


def _block(text, start, end):
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b]


def test_readable_branch_ids_is_global_and_independent_of_selected_work_governorate():
    block = _block(ACCESS, "def readable_branch_ids():", "def governorate_ok(")
    assert "if not can('view_reports')" in block
    assert "Branch.is_active == True, Governorate.is_active == True" in block
    assert "bids()" not in block
    assert "scope_governorate_id()" not in block


def test_home_dashboard_read_only_status_uses_global_branches_before_scope_selection():
    block = _block(DASHBOARD, "def home():", "@bp.get('/api/entry-ids")
    assert "read_branch_ids = set(readable_branch_ids())" in block
    assert "current_employee_status_rows(read_branch_ids, today)" in block
    assert "if read_branch_ids and can('view_reports'):" in block
    # Work-scope branches are kept separately for assigning/editing only.
    assert "bs = set(bids())" in block


def test_employee_directory_read_query_is_global_but_post_remains_scope_checked():
    block = _block(EMPLOYEES, "def employees():", "@bp.get('/employees/edit-data')")
    assert "if not branch_ok(bid):" in block
    assert "search_branch_ids = {" in block
    assert "Branch.is_active == True, Governorate.is_active == True" in block
    assert "Employee.branch_id.in_(selected_branch_ids)" in block
    assert "allowed_search_branch_ids = {b.id for b in scope_branches}" in block


def test_movement_worklist_reads_global_records_and_mutation_helpers_keep_scope():
    block = _block(MOVEMENTS, "def movements():", "@bp.route('/movements/<int:i>/edit'")
    assert "def movement_log_query():" in block
    assert ".join(Branch, Branch.id == Employee.branch_id)" in block
    assert "total_records = log_query.order_by(None).count()" in block
    assert ".limit(movement_page_size)" in block
    assert "Employee.branch_id.in_(bs)" not in block
    assert "bs = bids()" in block
    mutation = _block(ACCESS, "def can_manage_movement(m=None):", "# No legacy first-entry login role")
    assert "selected = scope_governorate_id()" in mutation
    assert "branch.governorate_id != int(selected)" in mutation


def test_reports_and_mission_print_export_read_across_active_governorates_before_scope():
    scope = _block(REPORTS, "def _report_branch_scope():", "@bp.get('/manager')")
    assert "Branch.is_active == True" in scope and "Governorate.is_active == True" in scope
    assert "bids()" not in scope and "gids()" not in scope
    assert "allowed_bids=readable_branch_ids()" in MISSIONS


def test_first_entry_is_not_a_formal_login_role_and_legacy_accounts_are_migrated():
    assert "LOGIN_ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']" in CONSTANTS
    assert "المدخل الأول" not in USERS_TEMPLATE or "name=\"roles\" value=\"المدخل الأول\"" not in USERS_TEMPLATE
    assert "name=\"roles\" value=\"المدخل الأول\"" not in USER_EDIT_TEMPLATE
    assert "DELETE FROM user_role WHERE role = 'المدخل الأول'" in BOOTSTRAP
    assert "DELETE FROM role_account WHERE role = 'المدخل الأول'" in BOOTSTRAP
    assert "EntryAssignment/EntryAssignmentBranch rows are intentionally" in BOOTSTRAP


def test_branch_entry_assignment_is_not_created_as_login_role():
    catalog = (ROOT / "employee_movements/blueprints/catalog.py").read_text(encoding="utf-8")
    assignments = (ROOT / "employee_movements/assignments.py").read_text(encoding="utf-8")
    replacement_template = (ROOT / "employee_movements/templates/replacement.html").read_text(encoding="utf-8")
    # Adding a branch no longer accepts or attaches a legacy first-entry login user.
    assert "entry_user_id" not in _block(catalog, "def branches():", "@bp.post('/branches/<int:i>/aliases')")
    assert "EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first()" in assignments
    assert "تكليف مسؤول إدخال للفروع" in replacement_template
    assert 'name="roles" value="المدخل الأول"' not in USERS_TEMPLATE


def test_global_read_routes_do_not_require_selected_work_governorate_for_results():
    home_template = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
    notifications = (ROOT / "employee_movements/blueprints/notifications.py").read_text(encoding="utf-8")
    movement_list = _block(MOVEMENTS, "def movements():", "@bp.get('/movements/<int:i>/history')")
    # The no-scope Home message is informational; it does not wrap or replace the
    # global employee search and cross-governorate read-only status board.
    assert "بيانات الموظفين والحركات والتقارير متاحة الآن عبر جميع المحافظات" in home_template
    assert "read_branch_ids = set(readable_branch_ids())" in DASHBOARD
    assert "readable_branch_ids()" in notifications
    assert "def movement_log_query():" in movement_list
    assert ".join(Branch, Branch.id == Employee.branch_id)" in movement_list
    assert "total_records = log_query.order_by(None).count()" in movement_list
    assert ".limit(movement_page_size)" in movement_list
    assert "Employee.branch_id.in_(bs)" not in movement_list
