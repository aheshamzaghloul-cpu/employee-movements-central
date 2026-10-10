from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "employee_movements" / "blueprints" / "dashboard.py"
HOME = ROOT / "employee_movements" / "templates" / "home.html"

def test_home_assignment_destinations_include_all_active_governorates():
    dashboard = DASHBOARD.read_text(encoding="utf-8")
    assert "home_assignment_governorates=(" in dashboard
    assert "Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()" in dashboard

def test_home_assignment_picker_filters_branches_without_scoping_to_work_governorate():
    home = HOME.read_text(encoding="utf-8")
    assert 'id="homeAssignmentGovernorate"' in home
    assert 'id="homeAssignmentBranch"' in home
    assert 'data-governorate="{{b.governorate_id}}"' in home
    assert "syncAssignmentBranches" in home
    assert "يمكنك اختيار فرع في محافظة مختلفة عن محافظة الموظف" in home

def test_selected_employee_card_shows_origin_governorate():
    home = HOME.read_text(encoding="utf-8")
    assert "movement_employee.branch.governorate.name" in home
