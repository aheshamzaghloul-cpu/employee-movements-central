from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "employee_movements" / "blueprints" / "reports.py"
BASE = ROOT / "employee_movements" / "templates" / "base.html"
HUB = ROOT / "employee_movements" / "templates" / "manager_hub.html"
CONSTANTS = ROOT / "employee_movements" / "constants.py"


def test_manager_workspace_is_role_gated_and_scope_aware():
    reports = REPORTS.read_text(encoding="utf-8")
    constants = CONSTANTS.read_text(encoding="utf-8")
    assert "@bp.get('/manager')" in reports
    assert "'مسؤول التطبيق', 'Manager Application Support'" in reports
    assert "Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)" in reports
    assert "Branch.is_active == True, Governorate.is_active == True" in reports
    assert "governorates = Governorate.query.filter_by(is_active=True)" in reports
    assert "Employee.branch_id.in_(allowed_branch_ids)" in reports
    assert "reports.manager_hub" not in constants
    assert "Manager and Admin both have global oversight" in reports


def test_manager_workspace_is_linked_and_covers_requested_tasks():
    base = BASE.read_text(encoding="utf-8")
    hub = HUB.read_text(encoding="utf-8")
    assert 'href="/manager"' in base
    assert '>المدير</span>' in base
    for expected in (
        'طلبات تعديل المأموريات',
        'تقارير المحافظات',
        'التقرير الشهري',
        '/reports/assignments/edit-requests',
        '/reports/assignments/monthly',
    ):
        assert expected in hub


def test_manager_monthly_report_is_global_but_edit_queue_requires_selected_work_scope():
    missions = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
    assert "scoped_branch_ids = set(bids())" in missions
    assert "if not scope_governorate_id():" in missions
    assert "not branch_ok(r.movement.employee.branch_id)" in missions
    assert "if {'مسؤول التطبيق', 'Manager Application Support'} & rs:" in missions
    assert "cross-governorate aggregation." in missions
