from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
JOURNEY = (ROOT / "employee_movements/static/css/pages/home-journey.css").read_text(encoding="utf-8")
VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()


def test_home_uses_one_ordered_mission_flow_instead_of_duplicate_quick_action_cards():
    for required in (
        'id="homeEmployeeSearchTitle"',
        'id="homeTicketTitle"',
        'id="homeManualMissionTitle"',
        'id="homeTicketUploadForm"',
        'id="homeTicketSubmit"',
    ):
        assert required in HOME
    assert HOME.index('id="homeEmployeeSearchTitle"') < HOME.index('id="homeTicketTitle"') < HOME.index('id="homeManualMissionTitle"')
    assert 'id="employee-search"' in HOME_SEARCH
    assert HOME.count('action="/missions/from-screenshot/scan"') == 1
    assert 'href="/reports/assignments/print-missions"' not in HOME


def test_selected_employee_is_shared_between_home_search_image_flow_and_manual_form():
    assert "movement_employee" in HOME
    assert 'name="expected_employee_id" value="{{movement_employee.id if movement_employee else \'\'}}"' in HOME
    assert "employee_id=movement_employee.id if movement_employee else None" in HOME
    assert "return_to=url_for('dashboard.home'" in HOME
    assert 'id="homeEmployeeSearchForm"' in HOME_SEARCH
    assert 'id="employee-search"' in HOME_SEARCH


def test_entry_assignment_is_centralized_and_not_a_formal_role_card_elsewhere():
    assert 'id="entry-directory"' in HOME
    assert 'action="/entry-role/add"' in HOME
    assert "لا ينشئ دور دخول أو حسابًا جديدًا" in HOME
    replacement = (ROOT / "employee_movements/templates/replacement.html").read_text(encoding="utf-8")
    assert "إدارة التكليفات والاستبدال تتم من مركز العمل في الرئيسية فقط" in replacement
    constants = (ROOT / "employee_movements/constants.py").read_text(encoding="utf-8")
    assert "ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']" in constants


def test_home_composition_styles_load_after_shared_design_system_and_match_release():
    assert "request.path == '/'" in BASE
    assert "css/pages/home-journey.css" in BASE
    assert BASE.index("css/design-system-cyan.css") < BASE.index("css/pages/home-journey.css")
    assert "v=app_version" in BASE
    assert ".ds-home-flow-grid" in JOURNEY
    assert re.search(r"@media\s*\(max-width:\s*820px\)", JOURNEY)
    assert "@media (prefers-reduced-motion: reduce)" in JOURNEY


def test_home_flow_has_keyboard_and_mobile_affordances():
    assert ":focus-visible" in JOURNEY
    assert "@media (max-width: 820px)" in JOURNEY
    assert "touch-action" in JOURNEY or "dropzone" in JOURNEY
    assert "aria-live" in HOME
