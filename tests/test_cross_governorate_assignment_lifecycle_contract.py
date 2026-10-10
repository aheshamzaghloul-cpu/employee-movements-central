from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
ACCESS = ROOT / "employee_movements" / "access.py"
MISSION_QUERY = ROOT / "employee_movements" / "services" / "mission_query.py"

def test_manager_and_supervisor_can_select_active_cross_governorate_assignment_branches():
    text = MOVEMENTS.read_text(encoding="utf-8")
    assert "bool(rs & {'مشرف محافظة', 'Manager Application Support'}) and movement_type == 'انتداب'" in text
    assert "Branch.is_active == True, Governorate.is_active == True, Branch.id.in_(allowed_bids)" in text

def test_assignment_save_validates_employee_destination_and_overlap_before_commit():
    text = MOVEMENTS.read_text(encoding="utf-8")
    create = text[text.index("def movement_create():"):text.index("@bp.get('/movements')")]
    assert "can_manage_movement_employee(employee, movement_type)" in create
    assert "can_manage_movement_destination(destination, movement_type)" in create
    assert "not destination.governorate.is_active" in create
    assert "movement_overlaps(employee.id, movement_type" in create
    assert "record_movement_history(movement" in create and "db.session.commit()" in create

def test_global_mission_query_and_print_remain_authorized_read_workflows():
    access = ACCESS.read_text(encoding="utf-8")
    missions = MISSIONS.read_text(encoding="utf-8")
    query = MISSION_QUERY.read_text(encoding="utf-8")
    assert "def can_print_mission(m=None):" in access
    assert "global_actor = bool({'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'} & set(roles))" in query
    assert "if not can_print_mission(m):" in missions
    assert "def mission_pdf(movement_id):" in missions
    assert "def mission_print_date_save(movement_id):" in missions
