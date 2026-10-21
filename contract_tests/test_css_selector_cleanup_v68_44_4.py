from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
CSS = ROOT / "employee_movements/static/css"
HOME = (CSS / "pages/home.css").read_text(encoding="utf-8")
DIRECTORY = (CSS / "pages/employee-directory.css").read_text(encoding="utf-8")
MOVEMENTS = (CSS / "pages/movement-forms.css").read_text(encoding="utf-8")
THEME = (CSS / "design-system-cyan.css").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")


def test_login_security_icon_is_a_blue_line_icon_not_a_black_filled_shape():
    rule = next(line for line in THEME.splitlines() if line.startswith(".login-trust-note svg"))
    assert "fill: none" in rule
    assert "stroke: currentColor" in rule
    assert "stroke-width:" in rule


def test_home_mission_and_register_cards_have_single_final_rules():
    assert len(__import__("re").findall(r"(?m)^\.ds-home-page \.ds-home-mission \{", HOME)) == 1
    assert len(__import__("re").findall(r"(?m)^\.ds-home-page \.ds-home-mission p \{", HOME)) == 1
    assert len(__import__("re").findall(r"(?m)^\.ds-home-page \.ds-home-mission > \.ui-btn \{", HOME)) == 1
    assert ".ds-home-page .ds-home-register .smart-register-empty { width:" not in HOME
    assert "#f1fafa" not in HOME.lower()
    assert "#eaf9fa" not in HOME.lower()


def test_scope_gate_uses_one_base_rule_with_responsive_only_overrides():
    assert ".ds-home-scope { grid-template-columns: 48px minmax(0,1fr); margin-bottom: 0; padding: 14px 18px; border-radius: 16px; background: linear-gradient(115deg,#f0fbfc,#fff); }" not in HOME
    assert ".ds-home-scope p { max-width: 900px; font-size: 11.5px; line-height: 1.7; }" not in HOME
    assert ".ds-home-scope .smart-scope-icon { width: 42px; height: 42px; border-radius: 13px; }" not in HOME


def test_directory_hero_background_is_owned_by_the_later_shared_design_layer():
    # The page-level background is intentionally removed when the globally loaded
    # design layer provides the final rule after it.
    assert ".ds-directory-page .ds-directory-hero {" in THEME
    hero = THEME[THEME.index(".ds-directory-page .ds-directory-hero {"):THEME.index("}", THEME.index(".ds-directory-page .ds-directory-hero {"))]
    assert "background: linear-gradient" in hero
    assert "#f0f8ff 100%) !important;" in hero
    assert "background:" not in DIRECTORY[DIRECTORY.index(".ds-directory-page .ds-directory-hero {"):DIRECTORY.index("}", DIRECTORY.index(".ds-directory-page .ds-directory-hero {"))]


def test_mission_textarea_is_not_overridden_by_the_fixed_height_input_rule():
    assert ".movement-edit-page .mission-edit-form input:not([type=checkbox]),.movement-edit-page .mission-edit-form select,.movement-edit-page .mission-edit-form textarea" not in MOVEMENTS
    assert ".movement-edit-page .mission-edit-form textarea{height:auto;min-height:100px;padding:10px 12px;border-radius:10px}" in MOVEMENTS


def test_stylesheet_cache_busters_are_synchronized_for_the_release():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    assert version == CURRENT_VERSION
    assert BASE.count("v=app_version") == 24
    assert 'data-app-version="{{app_version}}"' in BASE


def test_mobile_overflow_fallback_is_preserved_before_clip():
    app = (CSS / "app.css").read_text(encoding="utf-8")
    assert "html { overflow-x: hidden; overflow-x: clip; }" in app


def test_password_visibility_toggle_remains_secondary_and_reduced_motion_safe():
    app = (CSS / "app.css").read_text(encoding="utf-8")
    assert ".login-card form .auth-password-toggle {" in THEME
    assert "background: #fff !important" in THEME
    assert ".auth-password-toggle,.login-card form button { transition: none !important; transform: none !important; }" not in app
    assert '.login-card form button[type="submit"] { transform: none !important; }' in app


def test_assistant_launcher_has_one_base_rule():
    assistant = (CSS / "pages/assistant-dock.css").read_text(encoding="utf-8")
    assert len(__import__("re").findall(r"(?m)^\.assistant-dock-trigger \{", assistant)) == 1


def test_ticket_screenshot_route_loads_the_icon_dimension_stylesheet():
    assert "request.path.startswith('/missions/from-screenshot')" in BASE
    movement_forms = (CSS / "pages/movement-forms.css").read_text(encoding="utf-8")
    assert ".ticket-image-import .ticket-image-privacy-icon" in movement_forms
