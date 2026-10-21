from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
TEMPLATES = ROOT / "employee_movements" / "templates"
CSS = ROOT / "employee_movements" / "static" / "css"


def test_application_shell_cache_version_is_current():
    base = (TEMPLATES / "base.html").read_text(encoding="utf-8")
    assert 'data-app-version="{{app_version}}"' in base
    assert "68.45.2" not in base
    assert "filename='css/pages/management.css', v=app_version)" in base
    assert "filename='css/pages/workspace-pages.css', v=app_version)" in base


def test_admin_dashboard_kpis_keep_destinations_and_have_accessible_svg_icons():
    html = (TEMPLATES / "structure.html").read_text(encoding="utf-8")
    for href in ("/governorates", "/branches", "/users", "/employees", "/delegations", "/audit"):
        assert f'href="{href}" class="admin-ai-kpi"' in html
    assert html.count('class="admin-ai-kpi-icon ') == 6
    assert html.count('class="admin-ai-tool-icon" aria-hidden="true"') >= 9
    assert '<svg viewBox="0 0 24 24">' in html
    assert 'data-basyouni-prompt=' in html


def test_governorates_and_branches_use_consistent_line_icon_language():
    gov = (TEMPLATES / "governorates.html").read_text(encoding="utf-8")
    branch = (TEMPLATES / "branches.html").read_text(encoding="utf-8")
    assert 'class="catalog-kpi-icon" aria-hidden="true"><svg' in gov
    assert 'class="catalog-record-symbol" aria-hidden="true"><svg' in gov
    assert 'class="catalog-kpi-icon" aria-hidden="true"><svg' in branch
    assert 'class="catalog-record-symbol" aria-hidden="true"><svg' in branch
    assert 'data-catalog-search' in gov and 'data-catalog-search' in branch
    assert 'data-catalog-reset' in gov and 'data-catalog-reset' in branch


def test_users_and_permissions_workflows_are_preserved():
    users = (TEMPLATES / "users.html").read_text(encoding="utf-8")
    edit = (TEMPLATES / "user_edit.html").read_text(encoding="utf-8")
    for field in ('name="full_name"', 'name="username"', 'name="roles"', 'name="permissions"', 'name="governorate_id"'):
        assert field in users or field in edit
    assert 'action="/users/{{u.id}}/toggle"' in users
    assert 'action="/users/{{u.id}}/reset"' in users
    assert 'action="/users/{{u.id}}/delete"' in users
    assert 'input type="hidden" name="_csrf"' in users
    assert 'input type="hidden" name="_csrf"' in edit
    assert 'data-choice-all="permissions"' in edit
    assert 'data-choice-none="permissions"' in edit


def test_delegation_visual_states_do_not_change_post_actions_or_filters():
    html = (TEMPLATES / "delegations.html").read_text(encoding="utf-8")
    for state in ("is-live", "is-planned", "is-closed"):
        assert f"delegation-summary-item {state}" in html
    assert 'action="/delegations/add"' in html
    assert 'action="/delegations/{{d.id}}/revoke"' in html
    assert 'name="reason" required minlength="3"' in html
    assert 'name="_csrf"' in html
    for state in ("all", "live", "planned", "closed"):
        assert f'data-delegation-filter="{state}"' in html


def test_governance_visual_tokens_include_responsive_and_accessible_states():
    management = (CSS / "pages" / "management.css").read_text(encoding="utf-8")
    workspace = (CSS / "pages" / "workspace-pages.css").read_text(encoding="utf-8")
    assert "v68.46.0 — governance workspace visual system" in management
    assert ".admin-ai-kpi-icon.is-governorates" in management
    assert ".admin-ai-kpi-icon.is-users" in management
    assert ".delegation-summary-icon" in management
    assert "@media (max-width: 620px)" in management
    assert "body[data-page=\"governorates\"] .catalog-kpi" in workspace
    assert "body[data-page=\"branches\"] .catalog-kpi" in workspace
    assert ":focus-within" in workspace
