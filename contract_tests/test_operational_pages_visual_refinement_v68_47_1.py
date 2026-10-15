from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
OPS = (ROOT / "employee_movements/static/css/pages/operational-pages.css").read_text(encoding="utf-8")


def test_operational_stylesheet_is_loaded_only_for_operational_workflows():
    assert "filename='css/pages/operational-pages.css')+'?v=68.49.0'" in BASE
    for path_fragment in ("request.path == '/employees'", "request.path.startswith('/employees/')", "request.path.startswith('/employee/')", "request.path.startswith('/branches')", "request.path.startswith('/movements')", "request.path.startswith('/missions/')", "request.path.startswith('/reports/assignments/mission-edit')", "request.path.startswith('/reports/assignments/edit-requests')"):
        assert path_fragment in BASE
    assert BASE.count("v=68.49.0") == 21


def test_operational_styles_are_scoped_by_page_and_do_not_change_workflows():
    for selector in ('body[data-page=\"employees\"]', 'body[data-page=\"branches\"]', 'body[data-page=\"movements\"]', 'body[data-page=\"mission-import\"]', 'body[data-page=\"reports\"]'):
        assert selector in OPS
    assert 'name=' not in OPS and 'action=' not in OPS
    employees = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")
    movements = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
    mission = (ROOT / "employee_movements/templates/mission_from_screenshot.html").read_text(encoding="utf-8")
    assert 'name="job_code"' in employees
    assert 'action="/movements/create"' in movements
    assert 'name="_csrf"' in movements and 'name="screenshot"' in mission


def test_status_colors_and_responsive_rules_are_present():
    assert '.ui-status-chip.leave' in OPS
    assert '.ui-status-chip.assignment' in OPS
    assert '.ui-status-chip.permission' in OPS
    assert '#movementGovernorateStep .movement-step-number' in OPS
    assert '#movementBranchStep .movement-step-number' in OPS
    assert '#movementEmployeeStep .movement-step-number' in OPS
    assert '#movementDetailsStep .movement-step-number' in OPS
    assert '@media (max-width: 760px)' in OPS
    assert '@media (prefers-reduced-motion: reduce)' in OPS


def test_employee_profile_uses_scoped_operational_visual_refinement():
    assert "request.path.startswith('/employee/')" in BASE
    for selector in ('.smart-employee-hero', '.smart-employee-avatar', '.smart-employee-status', '.smart-employee-card', '.smart-last-movement.leave', '.smart-history-type.assign', '.smart-primary-action'):
        assert selector in OPS
    profile = (ROOT / "employee_movements/templates/employee.html").read_text(encoding="utf-8")
    assert 'class="smart-employee-hero"' in profile
    assert 'class="smart-employee-status {{current_status.key}}"' in profile
    assert 'id="movement-history"' in profile
    assert 'href="/movements?employee_id={{e.id}}"' in profile
