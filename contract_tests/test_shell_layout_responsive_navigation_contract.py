from pathlib import Path

ROOT = Path(__file__).parents[1]
CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
SHELL_JS = (ROOT / "employee_movements/static/js/shell.js").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")


def test_desktop_shell_width_and_sidebar_offset_share_one_token():
    assert ".ui-shell > .premium-main.with-shell" in CSS
    assert "width: calc(100% - var(--ui-sidebar));" in CSS
    assert "margin-right: var(--ui-sidebar);" in CSS


def test_mobile_main_uses_full_width_without_sidebar_reservation():
    assert "@media (max-width: 800px)" in CSS
    assert "width: 100%;" in CSS
    assert "body.ui-sidebar-collapsed .premium-main.with-shell" in CSS


def test_mobile_menu_has_visible_trigger_and_dismissible_backdrop():
    assert 'id="sidebarToggle"' in BASE
    assert 'id="sidebarBackdrop"' in BASE
    assert "ui-sidebar-backdrop:not([hidden])" in CSS
    assert "backdrop?.addEventListener('click'" in SHELL_JS


def test_escape_closes_mobile_navigation_and_aria_state_is_synced():
    assert "e.key==='Escape'&&sidebar.classList.contains('is-open')" in SHELL_JS
    assert "toggle.setAttribute('aria-expanded',String(shouldOpen))" in SHELL_JS


def test_saved_collapsed_preference_does_not_shrink_mobile_drawer():
    assert "!mobileQuery.matches&&desktopCollapsed" in SHELL_JS
    assert "body.ui-sidebar-collapsed .premium-sidebar" in CSS


def test_command_icon_has_clear_non_employee_search_purpose():
    assert 'title="التنقل السريع إلى الصفحات والإجراءات — Ctrl+K"' in BASE
    assert "فتح التنقل والأوامر السريعة" in BASE
    assert "employee search" not in BASE.lower()


def test_command_palette_is_a_real_responsive_dialog_not_an_inline_block():
    assert ".interactive-palette:not([hidden])" in CSS
    assert "position: fixed;" in CSS
    assert ".interactive-palette-dialog" in CSS
    assert "body.interactive-palette-open { overflow: hidden; }" in CSS


def test_notification_popover_is_anchored_to_stay_inside_desktop_viewport():
    start = CSS.index(".interactive-notification-popover {")
    block = CSS[start:CSS.index("}", start)]
    assert "inset-inline-end: 0;" in block
    assert "inset-inline-start: auto;" in block
    assert "width: min(410px, calc(100vw - 24px));" in block


def test_notification_escape_restores_focus_to_the_trigger():
    assert "if(restoreFocus) trigger.focus({preventScroll:true})" in (ROOT / "employee_movements/static/js/notifications.js").read_text(encoding="utf-8")


def test_navigation_updates_active_page_and_mobile_menu_icon_state():
    assert "a.setAttribute('aria-current','page')" in SHELL_JS
    assert "shouldOpen?'إغلاق القائمة':'فتح القائمة'" in SHELL_JS
    assert "m6 6 12 12M18 6 6 18" in SHELL_JS
