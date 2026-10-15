from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
JOURNEY = (ROOT / "employee_movements/static/css/pages/home-journey.css").read_text(encoding="utf-8")


def test_home_has_four_role_gated_quick_actions_and_real_destinations():
    assert 'aria-label="اختصارات العمل الرئيسية"' in HOME
    assert 'href="{% if movement_employee %}#movement-register{% else %}/movements#movement-create{% endif %}"' in HOME
    assert 'href="/missions/from-screenshot"' in HOME
    assert 'href="#employee-search"' in HOME
    assert 'href="/reports/assignments/print-missions"' in HOME
    assert 'id="home-mission-from-attachment"' in HOME
    assert 'id="home-mission-print"' in HOME
    assert "راجع كل البيانات قبل التسجيل" in HOME
    assert "can('manage_movements') and can_manage_movement()" in HOME
    assert "{% if can('view_reports') %}" in HOME


def test_workbench_keeps_existing_register_and_global_search_forms_separate():
    assert 'aria-label="مساحة التنفيذ والبحث"' in HOME
    assert 'id="movement-register"' in HOME
    assert 'id="homeMovementForm"' in HOME
    assert 'action="/movements/create"' in HOME
    assert 'id="homeEmployeeSearchForm"' in HOME_SEARCH
    assert 'id="employee-search"' in HOME_SEARCH
    assert 'name="movement_governorate_id"' in HOME_SEARCH
    assert 'name="movement_branch_id"' in HOME_SEARCH


def test_home_composition_styles_load_after_shared_design_system_only_on_home():
    assert "request.path == '/'" in BASE
    assert "css/pages/home-journey.css" in BASE
    assert BASE.index("css/design-system-cyan.css") < BASE.index("css/pages/home-journey.css")
    assert "?v=68.49.0" in BASE
    assert ".ds-home-page .ds-home-quick-actions {" in JOURNEY
    assert ".ds-home-page .ds-home-workbench-grid {" in JOURNEY
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in JOURNEY


def test_home_composition_is_responsive_keyboard_accessible_and_reduced_motion_safe():
    assert "@media (max-width: 1279px)" in JOURNEY
    assert "@media (max-width: 940px)" in JOURNEY
    assert "@media (max-width: 720px)" in JOURNEY
    assert "@media (max-width: 360px)" in JOURNEY
    assert ":focus-visible" in JOURNEY
    assert "@media (prefers-reduced-motion: reduce)" in JOURNEY
    assert re.search(r"\.ds-home-page \.ds-home-quick-action:focus-visible\s*\{[^}]*outline:", JOURNEY)


def test_home_work_scope_selector_remains_only_in_the_topbar():
    topbar = BASE[BASE.index('<header class="ui-topbar premium-topbar">'):BASE.index("</header>", BASE.index('<header class="ui-topbar premium-topbar">'))]
    assert "premium-scope-form" in topbar
    assert "smart-scope-form" not in HOME
    assert 'name="governorate_id"' not in HOME
