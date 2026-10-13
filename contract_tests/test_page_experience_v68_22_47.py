from pathlib import Path

ROOT = Path(__file__).parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
LOGIN = (ROOT / "employee_movements/templates/login.html").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")


def test_mobile_menu_toggle_is_outside_the_breadcrumb_that_hides_on_mobile():
    topbar = BASE[BASE.index('<header class="ui-topbar premium-topbar">'):BASE.index("</header>", BASE.index('<header class="ui-topbar premium-topbar">'))]
    toggle_pos = topbar.index('class="ui-mobile-menu premium-mobile-menu"')
    breadcrumb_pos = topbar.index('<div class="premium-breadcrumb">')
    assert toggle_pos < breadcrumb_pos
    assert "id=\"sidebarToggle\"" in topbar
    assert ".premium-breadcrumb { display: none !important; }" in CSS
    assert ".premium-mobile-menu { display: inline-grid !important;" in CSS


def test_anonymous_auth_content_uses_full_page_container_not_legacy_430px_card():
    assert '{% if not me %}<div class="auth-content">{% endif %}' in BASE
    assert '.auth-content {' in CSS
    auth = CSS[CSS.index('.auth-content {'):CSS.index('}', CSS.index('.auth-content {'))]
    assert 'width: min(1120px, 100%);' in auth
    assert '{% if not me %}<div class="login">{% endif %}' not in BASE


def test_login_password_toggle_preserves_password_field_and_accessible_control_relationship():
    assert 'id="loginPassword" type="password" name="password"' in LOGIN
    assert 'data-password-toggle="loginPassword"' in LOGIN
    assert 'aria-controls="loginPassword" aria-pressed="false"' in LOGIN
    # The interactive button must not be nested inside a label.
    password_group = LOGIN[LOGIN.index('<div class="auth-field">'):LOGIN.index('</div>', LOGIN.index('<div class="auth-field">')) + 6]
    assert '<label for="loginPassword">' in password_group
    assert '<button class="auth-password-toggle"' in password_group
    assert 'aria-pressed' in APP_JS and "input.type=reveal?'text':'password'" in APP_JS


def test_login_mobile_keeps_branding_and_form_instead_of_hiding_the_hero():
    # The original mobile behavior remains in the responsive auth rules after the shared design authority was consolidated.
    assert '.login-hero { display: flex !important;' in CSS
    assert '.login-shell { grid-template-columns: minmax(0,1fr) !important;' in CSS


def test_primary_actions_and_active_tabs_use_shared_brand_tokens():
    # Shared styles may be reorganized without relying on a version-specific marker comment.
    assert '--ui-brand-strong: #066773' in CSS
    assert 'background: linear-gradient(120deg, var(--ui-brand-strong)' in CSS
    assert '.ui-filter-pill.active, .section-tab.active' in CSS


def test_login_toggle_does_not_add_inline_javascript_or_change_submit_name():
    assert '<script' not in LOGIN
    assert 'name="password"' in LOGIN
    assert 'autocomplete="current-password"' in LOGIN
