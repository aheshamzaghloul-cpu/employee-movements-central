from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = (ROOT / "employee_movements/assignments.py").read_text(encoding="utf-8")
EMPLOYEE_ROUTES = (ROOT / "employee_movements/blueprints/employees.py").read_text(encoding="utf-8")
DASHBOARD_ROUTES = (ROOT / "employee_movements/blueprints/dashboard.py").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
EMPLOYEES_TEMPLATE = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")


def test_responsible_contact_is_resolved_by_branch_assignment_not_employee_id():
    assert "def entry_responsible_names_by_branch(branch_ids):" in ASSIGNMENTS
    assert "EntryAssignmentBranch.branch_id.in_(ids)" in ASSIGNMENTS
    assert "EntryAssignment.is_active == True" in ASSIGNMENTS
    assert "Employee.is_active == True" in ASSIGNMENTS
    assert "db.session.query(EntryAssignmentBranch.branch_id, Employee.id, Employee.full_name)" in ASSIGNMENTS
    assert "seen_employee_ids" in ASSIGNMENTS


def test_live_search_endpoint_returns_entry_contact_without_movement_history():
    endpoint = EMPLOYEE_ROUTES[EMPLOYEE_ROUTES.index("def employee_search():"):EMPLOYEE_ROUTES.index("@bp.route('/employees'", EMPLOYEE_ROUTES.index("def employee_search():"))]
    assert "entry_responsible_names_by_branch" in endpoint
    assert "'entry_responsible': entry_responsible_label" in endpoint
    assert "'entry_responsible_names'" in endpoint
    assert "Movement.query" not in endpoint


def test_homepage_server_results_and_selected_employee_show_entry_contact():
    assert "movement_entry_responsible_map=movement_entry_responsible_map" in DASHBOARD_ROUTES
    assert "movement_entry_responsible_status_map=movement_entry_responsible_status_map" in DASHBOARD_ROUTES
    assert "movement_entry_responsible_map.get(emp.id, 'غير محدد')" in HOME_SEARCH
    assert "movement_entry_responsible_map.get(movement_employee.id, 'غير محدد')" in HOME_SEARCH
    assert "مسؤول إدخال الفرع" in HOME_SEARCH
    assert "is-conflict" in HOME_SEARCH


def test_homepage_live_search_renders_the_same_contact_field():
    assert "e.entry_responsible||'غير محدد'" in APP_JS
    assert "smart-entry-contact-inline" in APP_JS
    assert "entry_responsible_status==='conflict'" in APP_JS


def test_employee_directory_uses_branch_responsibility_and_exposes_ambiguity():
    assert "names_by_branch = entry_responsible_names_by_branch" in EMPLOYEE_ROUTES
    assert "entry_responsible_label(names_by_branch.get(employee.branch_id, []))" in EMPLOYEE_ROUTES
    assert "تعارض تكليفات:" in ASSIGNMENTS
    assert "entry_map.get(e.id) or 'غير مسند'" in EMPLOYEES_TEMPLATE
