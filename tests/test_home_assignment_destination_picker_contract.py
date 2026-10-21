from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "employee_movements" / "templates" / "home.html"
HOME_SEARCH = ROOT / "employee_movements" / "templates" / "home_global_search.html"
MOVEMENTS = ROOT / "employee_movements" / "templates" / "movements.html"

def test_home_mission_workflow_orders_global_search_ticket_upload_then_manual_entry():
    home = HOME.read_text(encoding="utf-8")
    search = HOME_SEARCH.read_text(encoding="utf-8")
    assert "{% include 'home_global_search.html' %}" in home
    assert 'id="homeTicketUploadForm"' in home
    assert 'id="homeTicketScreenshot"' in home
    assert "/movements?movement_type=انتداب" in home
    assert home.index("{% include 'home_global_search.html' %}") < home.index('id="homeTicketUploadForm"') < home.index("/movements?movement_type=انتداب")
    assert 'id="homeEmployeeSearchForm"' in search
    assert 'name="movement_governorate_id"' in search and 'name="movement_branch_id"' in search

def test_manual_mission_form_has_separate_source_and_destination_governorate_pickers():
    movements = MOVEMENTS.read_text(encoding="utf-8")
    assert 'id="movementCreateGovernorate"' in movements
    assert 'id="movementDestinationGovernorate"' in movements
    assert 'id="movementDestinationBranch"' in movements
    assert "syncDestinationBranches" in movements

def test_selected_employee_card_shows_origin_governorate_and_entry_contact():
    home = HOME_SEARCH.read_text(encoding="utf-8")
    assert "movement_employee.branch.governorate.name" in home
    assert "مسؤول الإدخال الأول عن هذا الفرع" in home
