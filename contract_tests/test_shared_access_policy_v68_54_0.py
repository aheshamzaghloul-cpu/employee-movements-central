from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = (ROOT / "employee_movements" / "constants.py").read_text(encoding="utf-8")
ACCESS = (ROOT / "employee_movements" / "access.py").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements" / "templates" / "base.html").read_text(encoding="utf-8")
STRUCTURE = (ROOT / "employee_movements" / "blueprints" / "structure.py").read_text(encoding="utf-8")
USERS = (ROOT / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
REPORTS = (ROOT / "employee_movements" / "blueprints" / "reports.py").read_text(encoding="utf-8")
EMPLOYEE_TYPE_TEMPLATE = (ROOT / "employee_movements" / "templates" / "employee_type_report.html").read_text(encoding="utf-8")
MISSIONS = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")


def _block(text, begin, end):
    start = text.index(begin)
    stop = text.index(end, start + len(begin))
    return text[start:stop]


def test_only_three_official_login_roles_and_no_first_entry_role():
    assert "ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']" in CONSTANTS
    assert "LOGIN_ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']" in CONSTANTS
    assert "'المدخل الأول':" not in CONSTANTS
    assert "'مدخل أول':" not in CONSTANTS


def test_supervisor_and_manager_share_operational_permissions_but_not_admin_permissions():
    assert "'مشرف محافظة':" in CONSTANTS
    assert "'Manager Application Support':" in CONSTANTS
    assert "'manage_employees'" in CONSTANTS and "'manage_movements'" in CONSTANTS and "'view_reports'" in CONSTANTS
    # These roles must never inherit the account/catalog capabilities from the admin role.
    for role in ("مشرف محافظة", "Manager Application Support"):
        body = CONSTANTS.split(f"'{role}':", 1)[1].split("},", 1)[0]
        assert "'manage_users'" not in body
        assert "'manage_structure'" not in body
        assert "'view_audit'" not in body


def test_admin_area_and_user_account_management_remain_admin_only():
    assert "{% if 'مسؤول التطبيق' in roles %}" in BASE
    assert 'href="/structure"' in BASE
    structure_route = _block(STRUCTURE, "def structure():", "@bp.")
    assert "if 'مسؤول التطبيق' not in roles(current):" in structure_route and "abort(403)" in structure_route
    users_route = _block(USERS, "def users():", "@bp.")
    assert "if 'مسؤول التطبيق' not in roles() or not can('manage_users'):" in users_route


def test_report_filters_are_global_and_employee_type_report_does_not_block_without_work_scope():
    scope = _block(REPORTS, "def _report_branch_scope():", "@bp.get('/manager')")
    assert "Governorate.is_active == True" in scope
    assert "gids()" not in scope
    helper = _block(REPORTS, "def _apply_employee_type_report_filters(", "def _report_branch_scope():")
    assert "Governorate.query.filter_by(is_active=True).all()" in helper
    assert "set(gids())" not in helper
    assert "scope-empty-state" not in EMPLOYEE_TYPE_TEMPLATE


def test_read_only_movement_history_is_global_but_does_not_grant_mutation_scope():
    view = _block(ACCESS, "def can_view_movement(m=None):", "def can_print_mission")
    assert "if not can('view_reports')" in view
    assert "return bool(getattr(m, 'is_active', False))" in view
    mutation = ACCESS[ACCESS.index("def can_manage_movement(m=None):"): ]
    assert "selected = scope_governorate_id()" in mutation
    assert "branch.governorate_id != int(selected)" in mutation
    assert "not branch_ok(branch.id)" in mutation


def test_work_governorate_stays_mandatory_for_admin_and_manager_operations():
    resolver = _block(ACCESS, "def scope_governorate_id():", "def scope_governorates_for_user")
    assert "Admin and Manager always make an explicit work-scope choice" in resolver
    assert "current_scope_role == 'مشرف محافظة' and len(allowed_ids) == 1" in resolver
    assert "OPERATIONAL_SCOPE_ENDPOINTS" in CONSTANTS
    assert "'dashboard.home'" in CONSTANTS and "'movements.movement_create'" in CONSTANTS


def test_first_entry_assignment_is_operational_and_work_governorate_scoped():
    assert "المدخل الأول هنا بند تنظيمي فقط: لا يحتاج حساب دخول." in (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    assert "'مسؤول التطبيق' in effective or 'مشرف محافظة' in effective or is_manager_support" in (ROOT / "employee_movements" / "blueprints" / "dashboard.py").read_text(encoding="utf-8")
    assert "return bool(selected and allowed and current and current.issubset(allowed))" in STRUCTURE


def test_closed_mission_change_requests_are_created_by_supervisor_or_admin_and_reviewed_only_by_manager():
    create = _block(MISSIONS, "def mission_edit_request_create(", "@bp.get('/reports/assignments/edit-requests')")
    queue = _block(MISSIONS, "def mission_edit_requests():", "@bp.get('/reports/assignments/edit-requests/<int:request_id>')")
    review = _block(MISSIONS, "def mission_edit_request_review(", "@bp.post('/reports/assignments/edit-requests/<int:request_id>')")
    save = _block(MISSIONS, "def mission_edit_request_save(", "@bp.get('/reports/assignments/export.xlsx')")
    assert "'مشرف محافظة' in rs or 'مسؤول التطبيق' in rs" in create
    assert "'Manager Application Support' not in rs" in create
    for block in (queue, review, save):
        assert "if 'Manager Application Support' not in rs or not can('manage_movements'):" in block


def test_closed_missions_cannot_be_reopened_or_deleted_directly():
    mission_reopen = _block(MISSIONS, "def mission_reopen(", "@bp.get('/reports/assignments/mission-print-date")
    movement_reopen = _block(MOVEMENTS, "def reopen_assignment(", "@bp.get('/movements/<int:i>/assignment-form')")
    delete = _block(MOVEMENTS, "def movement_delete(", "@bp.get('/movements/<int:i>/history')")
    edit_save = _block(MISSIONS, "def mission_edit_save(", "@bp.post('/reports/assignments/mission-close")
    assert "لا يمكن إعادة فتح المأمورية مباشرة" in mission_reopen
    assert "إعادة الفتح المباشر غير متاحة" in movement_reopen
    assert "movement_is_closed(m)" in delete
    assert "لا يمكن حذف مأمورية مغلقة مباشرة" in delete
    submit = _block(MOVEMENTS, "def movement_submit(", "@bp.post('/movements/<int:i>/close-assignment')")
    assert "movement_is_closed(m)" in submit
    assert "لا يمكن تثبيت أو تغيير حالة مأمورية مغلقة مباشرة" in submit
    assert "if mission_state_label(m) == 'مغلقة':" in edit_save
