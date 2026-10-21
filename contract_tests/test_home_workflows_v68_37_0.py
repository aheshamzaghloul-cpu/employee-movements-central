from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "employee_movements/static/css/pages/home.css").read_text(encoding="utf-8")
DESIGN_CSS = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
HOME_JOURNEY_CSS = (ROOT / "employee_movements/static/css/pages/home-journey.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()


def test_home_primary_flow_is_search_then_ticket_image_then_manual_mission():
    positions = [HOME.index(token) for token in (
        'id="homeEmployeeSearchTitle"',
        'id="homeTicketTitle"',
        'id="homeManualMissionTitle"',
    )]
    assert positions == sorted(positions)
    assert 'id="homeTicketUploadForm"' in HOME
    assert 'action="/missions/from-screenshot/scan"' in HOME
    assert 'enctype="multipart/form-data"' in HOME
    assert 'name="screenshot" type="file"' in HOME
    assert 'accept="image/png,image/jpeg,image/webp"' in HOME
    assert 'name="expected_employee_id"' in HOME
    assert 'id="homeTicketSubmit"' in HOME
    assert "لا تُحفظ المأمورية تلقائيًا من الصورة" in HOME


def test_home_manual_mission_preserves_the_selected_employee_and_uses_standard_form():
    assert "url_for('movements.movements', movement_type='انتداب'" in HOME
    assert "return_to=url_for('dashboard.home'" in HOME
    assert "employee_id=movement_employee.id if movement_employee else None" in HOME
    movement_template = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
    movement_route = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    assert 'id="movement-create"' in movement_template
    assert "initial_movement_type=initial_movement_type" in movement_route
    assert "initial_employee=initial_employee" in movement_route
    assert "can_manage_movement_employee(candidate, initial_movement_type)" in movement_route
    assert "تم تحديد الموظف الذي اخترته في الرئيسية" in movement_template


def test_home_employee_search_is_global_and_selection_is_explicit():
    assert 'id="employee-search"' in HOME_SEARCH
    assert 'id="homeEmployeeSearchForm"' in HOME_SEARCH
    assert 'name="movement_name"' in HOME_SEARCH
    assert 'name="movement_governorate_id"' in HOME_SEARCH
    assert 'name="movement_branch_id"' in HOME_SEARCH
    assert "البحث شامل لكل المحافظات ولا يتأثر بمحافظة العمل" in HOME_SEARCH
    assert 'employee_id={{emp.id}}#employee-search' in HOME_SEARCH


def test_first_entry_is_an_operational_assignment_not_a_login_role():
    assert "تكليف مسؤول إدخال للفروع" in HOME
    assert 'action="/entry-role/add"' in HOME
    assert 'name="employee_id" id="inline-entry-employee"' in HOME
    assert 'name="supervisor_id"' in HOME
    assert 'name="branch_id"' in HOME
    assert "لا ينشئ دور دخول أو حسابًا جديدًا" in HOME
    constants = (ROOT / "employee_movements/constants.py").read_text(encoding="utf-8")
    access = (ROOT / "employee_movements/access.py").read_text(encoding="utf-8")
    assert "'المدخل الأول'" not in constants.split("ROLES =", 1)[1].split("\n", 1)[0]
    assert "'المدخل الأول'" not in constants.split("ROLE_DEFAULT_PERMISSIONS =", 1)[1].split("\n}", 1)[0]
    assert "role in LOGIN_ROLES" in access
    users_template = (ROOT / "employee_movements/templates/users.html").read_text(encoding="utf-8")
    assert "rejectattr('role','equalto','المدخل الأول')|list" in users_template
    bootstrap = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")
    assert "DELETE FROM user_role WHERE role = 'المدخل الأول'" in bootstrap
    assert "DELETE FROM role_account WHERE role = 'المدخل الأول'" in bootstrap
    structure = (ROOT / "employee_movements/blueprints/structure.py").read_text(encoding="utf-8")
    assert "supervisor_self" in structure
    assert "branch_ids.issubset(allowed_branch_ids)" in structure


def test_operational_governorate_selector_is_single_source_in_topbar():
    topbar_start = BASE.index('<header class="ui-topbar premium-topbar">')
    topbar = BASE[topbar_start:BASE.index("</header>", topbar_start)]
    assert "premium-scope-form" in topbar
    assert "smart-scope-form" not in HOME
    assert "اختر محافظة العمل من الشريط العلوي" in HOME
    assert 'name="governorate_id"' not in HOME


def test_home_styles_are_responsive_and_loaded_after_shared_design_system():
    assert "design-system-cyan.css" in BASE
    assert BASE.index("design-system-cyan.css") < BASE.index("home-journey.css")
    assert "v=app_version" in BASE
    for selector in (".ds-home-flow", ".ds-home-flow-search", ".ds-home-flow-ticket", ".ds-home-flow-manual"):
        assert selector in HOME_JOURNEY_CSS
    assert "@media (max-width: 820px)" in HOME_CSS
    assert "@media (prefers-reduced-motion: reduce)" in HOME_CSS
    for selector in (".premium-sidebar", ".premium-topbar", ".premium-main.with-shell", ".ui-table-wrap", ":focus-visible"):
        assert selector in APP_CSS
