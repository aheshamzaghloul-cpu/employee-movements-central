from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
DOCK = (ROOT / "employee_movements/templates/assistant_dock.html").read_text(encoding="utf-8")
ASSISTANT_CSS = (ROOT / "employee_movements/static/css/pages/assistant-dock.css").read_text(encoding="utf-8")
SHARED_CSS = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
NAV_CSS = (ROOT / "employee_movements/static/css/navigation-color-system.css").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "employee_movements/static/css/pages/home-journey.css").read_text(encoding="utf-8")


def test_sidebar_uses_a_stronger_deep_blue_canvas_with_a_bright_active_state():
    assert "--ui-sidebar-bg-start: #164b76;" in NAV_CSS.lower()
    assert "--ui-sidebar-bg-mid: #10395f;" in NAV_CSS.lower()
    assert "--ui-sidebar-bg-end: #092b4b;" in NAV_CSS.lower()
    assert ".premium-sidebar .premium-nav a.active" in NAV_CSS
    assert "#b9eaff" in NAV_CSS.lower()
    assert '.premium-sidebar .premium-nav a[href="/employees"] svg' in NAV_CSS
    assert '.premium-sidebar .premium-nav a[href="/movements"] svg' in NAV_CSS
    assert 'navigation-color-system.css' in BASE
    assert BASE.index("css/navigation-color-system.css") > BASE.index("css/pages/assistant-dock.css")


def test_home_welcome_panel_is_more_compact():
    assert "min-height: 92px" in HOME_CSS
    assert "padding: clamp(11px, .9vw, 15px) !important" in HOME_CSS
    assert "font-size: 21px; line-height: 1.22" in HOME_CSS
    assert ".ds-home-page .ds-home-hero h1" in HOME_CSS


def test_home_action_icons_have_distinct_semantic_colors():
    for selector in (".ds-home-quick-register .ds-home-quick-icon", ".ds-home-ticket-mission .ds-home-quick-icon", ".ds-home-quick-search .ds-home-quick-icon", ".ds-home-quick-print .ds-home-quick-icon"):
        assert selector in HOME_CSS
    for color in ("#087fc0", "#0b9288", "#7056c7", "#315da8"):
        assert color in HOME_CSS.lower()


def test_assistant_name_is_visible_and_accessible():
    assert 'class="assistant-dock-label">المساعد الذكي</span>' in DOCK
    assert 'aria-label="فتح المساعد الذكي بسيوني"' in DOCK
    assert ".assistant-dock-label" in ASSISTANT_CSS
    assert "min-width: 132px !important" in ASSISTANT_CSS


def test_static_asset_cache_version_is_bumped_consistently():
    assert "68.49.0" in BASE
    assert "68.45.0" not in BASE


def test_sidebar_icons_use_distinct_high_contrast_semantic_colors():
    for color in ("#006fbd", "#007e6b", "#6841c4", "#244db6", "#a85b08", "#b94227", "#ae2f71"):
        assert color in NAV_CSS.lower()
    for selector in (".ds-home-quick-register .ds-home-quick-icon", ".ds-home-ticket-mission .ds-home-quick-icon", ".ds-home-quick-search .ds-home-quick-icon", ".ds-home-quick-print .ds-home-quick-icon"):
        assert selector in NAV_CSS
