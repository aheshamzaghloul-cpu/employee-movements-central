"""Contracts for the secondary workspace visual polish in v68.53.1."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements/static/css/pages/secondary-workspaces.css").read_text(encoding="utf-8")


def test_release_metadata_and_cache_busters_are_synchronized():
    assert (ROOT / "VERSION.md").read_text(encoding="utf-8").strip() == CURRENT_VERSION
    assert f'version = "{CURRENT_VERSION}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"__version__ = '{CURRENT_VERSION}'" in (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert 'data-app-version="{{app_version}}"' in BASE
    assert BASE.count("v=app_version") == 24


def test_secondary_stylesheet_loads_after_shared_and_operational_styles_only_on_relevant_routes():
    link = "css/pages/secondary-workspaces.css"
    assert link in BASE
    assert BASE.index("css/navigation-color-system.css") < BASE.index(link)
    assert BASE.index("css/pages/operational-pages.css") < BASE.index(link)
    for path in ("/change-password", "/notifications", "/audit", "/lookups", "/replacement"):
        assert f"request.path.startswith('{path}')" in BASE
    assert "request.path.startswith('/users/') and request.path != '/users'" in BASE


def test_secondary_pages_have_semantic_page_identifiers():
    for fragment in ("}audit", "}lookups", "}account", "}replacement", "}user-edit"):
        assert fragment in BASE
    assert "request.path == '/users'" in BASE
    assert "request.path.startswith('/users/')" in BASE


def test_password_account_styles_are_responsive_and_keep_existing_fields():
    template = (ROOT / "employee_movements/templates/change_password.html").read_text(encoding="utf-8")
    for field in ('name="old_password"', 'name="new_password"', 'name="confirm_password"', 'name="_csrf"'):
        assert field in template
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in CSS
    assert "@media (max-width: 760px)" in CSS


def test_notifications_keep_semantic_urgency_states():
    template = (ROOT / "employee_movements/templates/notifications.html").read_text(encoding="utf-8")
    for token in ('urgent', 'warning', 'info', 'data-progressive-search', 'data-progressive-container'):
        assert token in template
    for token in ('.interactive-notification-metric.urgent', '.interactive-notification-metric.warning', '.interactive-notification-metric.info'):
        assert token in CSS


def test_audit_and_lookup_tables_keep_overflow_inside_table_containers():
    audit = (ROOT / "employee_movements/templates/audit.html").read_text(encoding="utf-8")
    lookups = (ROOT / "employee_movements/templates/lookups.html").read_text(encoding="utf-8")
    assert 'class="ui-card ui-table-wrap audit-table-card"' in audit
    assert 'class="ui-table-wrap"' in lookups
    assert 'body[data-workspace-path^="/audit"] .audit-table-card table { min-width: 920px; }' in CSS
    assert 'body[data-workspace-path^="/lookups"] .ui-grid.wide > .ui-card table { min-width: 560px; }' in CSS


def test_replacement_and_user_edit_are_scoped_without_changing_post_fields():
    replacement = (ROOT / "employee_movements/templates/replacement.html").read_text(encoding="utf-8")
    user_edit = (ROOT / "employee_movements/templates/user_edit.html").read_text(encoding="utf-8")
    for field in ('name="mode" value="supervisor"', 'name="old_supervisor_id"', 'name="new_supervisor_id"', 'name="_csrf"'):
        assert field in replacement
    assert 'name="mode" value="entry"' not in replacement
    assert 'href="/#entry-directory"' in replacement
    assert "إدارة التكليفات والاستبدال تتم من مركز العمل في الرئيسية فقط" in replacement
    for field in ('name="full_name"', 'name="roles"', 'name="governorate_id"', 'name="permissions"', 'name="_csrf"'):
        assert field in user_edit
    assert 'body[data-workspace-path^="/replacement"] .replace-card:nth-child(1)' in CSS
    assert 'body[data-workspace-path^="/users/"] .user-edit-card' in CSS


def test_error_view_has_consistent_product_colors():
    template = (ROOT / "employee_movements/templates/error.html").read_text(encoding="utf-8")
    assert 'class="error-page"' in template
    app_css = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
    assert '.error-page::before' in app_css
    assert '.error-page .error-code' in app_css
