from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = ROOT / "employee_movements" / "constants.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
ACCESS = ROOT / "employee_movements" / "access.py"

def test_global_mission_search_and_print_do_not_require_work_governorate():
    constants = CONSTANTS.read_text(encoding="utf-8")
    start = constants.index("OPERATIONAL_SCOPE_ENDPOINTS")
    scope_block = constants[start:constants.index("\n)", start)]
    for endpoint in (
        "missions.mission_print_list",
        "missions.mission_print_date",
        "missions.mission_print_date_save",
        "missions.mission_pdf",
        "missions.mission_print",
    ):
        assert endpoint not in scope_block, f"Global print endpoint is still gated: {endpoint}"

def test_global_mission_print_still_uses_central_permission_guard():
    access = ACCESS.read_text(encoding="utf-8")
    missions = MISSIONS.read_text(encoding="utf-8")
    assert "def can_print_mission(m=None):" in access
    assert "if not can_print_mission(m):" in missions
    assert "def mission_print_list():" in missions


def test_global_mission_report_does_not_gate_on_selected_work_governorate():
    template = (ROOT / "employee_movements" / "templates" / "mission_reports.html").read_text(encoding="utf-8")
    assert "scope_required and not scope_selected" not in template
    assert "اختر المحافظة أولًا" not in template
    assert 'name="branch_id" onchange="this.form.employee_id.value=\'\';this.form.submit()" disabled' not in template
    assert 'name="destination_branch_id" onchange="this.form.submit()" disabled' not in template

def test_global_mission_branch_filters_disambiguate_same_named_branches():
    template = (ROOT / "employee_movements" / "templates" / "mission_reports.html").read_text(encoding="utf-8")
    assert "{{b.name}} · {{b.governorate.name if b.governorate else '—'}}" in template
