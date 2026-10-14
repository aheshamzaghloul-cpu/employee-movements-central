from pathlib import Path

ROOT = Path(__file__).parents[1]
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_SEARCH = (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "employee_movements/static/css/pages/home.css").read_text(encoding="utf-8")
DESIGN_CSS = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
HOME_JOURNEY_CSS = (ROOT / "employee_movements/static/css/pages/home-journey.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")


def test_home_offers_ticket_attachment_mission_entrypoint_for_movement_managers():
    assert 'id="home-mission-from-attachment"' in HOME
    assert 'href="/missions/from-screenshot"' in HOME
    assert "مأمورية من المرفق" in HOME
    assert "راجع كل البيانات قبل التسجيل" in HOME


def test_home_movement_cta_opens_the_dedicated_movement_wizard_not_global_search():
    assert 'href="/movements#movement-create"' in HOME
    assert 'id="homeStartMovementAction"' in HOME
    assert "homeChooseEmployeeAction" not in HOME
    assert "employeeSearchSection?.scrollIntoView" not in HOME
    assert 'id="movement-create"' in (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
    # Global search remains a separate, independent home card.
    assert 'id="employee-search"' in HOME_SEARCH


def test_operational_governorate_selector_is_single_source_in_topbar():
    topbar = BASE[BASE.index('<header class="ui-topbar premium-topbar">'):BASE.index("</header>", BASE.index('<header class="ui-topbar premium-topbar">'))]
    assert "premium-scope-form" in topbar
    assert "smart-scope-form" not in HOME
    assert "اختر محافظة العمل من الشريط العلوي" in HOME
    assert 'name="governorate_id"' not in HOME


def test_home_action_cards_have_explicit_order_and_responsive_spacing():
    # Shared final card ordering lives in the design layer, loaded after home.css.
    combined = HOME_CSS + "\n" + DESIGN_CSS
    for selector in (".ds-home-register", ".ds-home-ticket-mission", ".ds-home-search", ".ds-home-mission"):
        assert selector in combined
    assert ".ds-home-page .ds-home-quick-actions {" in HOME_JOURNEY_CSS
    assert "grid-template-columns: repeat(4, minmax(0, 1fr))" in HOME_JOURNEY_CSS
    assert ".ds-home-page .ds-home-workbench-grid {" in HOME_JOURNEY_CSS
    assert ".ds-home-page .ds-home-actions > .ds-home-quick-actions { grid-column: 1 / -1;" in HOME_JOURNEY_CSS
    assert "@media (max-width: 820px)" in HOME_CSS
    assert "@media (prefers-reduced-motion: reduce)" in HOME_CSS


def test_shared_visual_polish_covers_shell_login_forms_tables_and_focus():
    for selector in (".premium-sidebar", ".premium-topbar", ".premium-main.with-shell", ".login-hero", ".login-card", ".ui-table-wrap", ":focus-visible"):
        assert selector in APP_CSS
    assert "v68.37.0" in APP_CSS


def test_sky_blue_cyan_design_system_is_loaded_after_page_styles_and_cache_busted():
    assert "design-system-cyan.css" in BASE
    assert "v=68.45.0" in BASE
    assert "v68.45.0" in (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
    assert "--ui-brand: #147cad" in APP_CSS
    assert "--ui-brand-soft: #e8f5ff" in APP_CSS
