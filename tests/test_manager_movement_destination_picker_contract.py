from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"

def test_manager_open_movement_edit_uses_the_same_active_destination_catalog_as_supervisor():
    source = MOVEMENTS.read_text(encoding="utf-8")
    start = source.index("@bp.route('/movements/<int:i>/edit'")
    end = source.index("@bp.post('/movements/<int:i>/submit')", start)
    route = source[start:end]
    assert "can_manage_movement_destination(destination, mt)" in route
    assert "destination.id not in set(bids())" not in route
    assert "destination_branches=(" in route
    assert "Governorate.is_active == True" in route

def test_manager_open_mission_edit_allows_active_cross_governorate_destination():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_edit_save(")
    end = source.index("@bp.post('/reports/assignments/mission-close/<int:movement_id>')", start)
    route = source[start:end]
    assert "can_manage_movement_destination(destination, 'انتداب')" in route
    assert "destination.id not in set(bids())" not in route
    assert "destination.governorate.is_active" in route
