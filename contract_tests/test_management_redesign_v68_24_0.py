from pathlib import Path
import re

import tinycss2

ROOT = Path(__file__).parents[1]
BASE = (ROOT / 'employee_movements/templates/base.html').read_text(encoding='utf-8')
USERS = (ROOT / 'employee_movements/templates/users.html').read_text(encoding='utf-8')
USER_EDIT = (ROOT / 'employee_movements/templates/user_edit.html').read_text(encoding='utf-8')
STRUCTURE = (ROOT / 'employee_movements/templates/structure.html').read_text(encoding='utf-8')
DELEGATIONS = (ROOT / 'employee_movements/templates/delegations.html').read_text(encoding='utf-8')
CSS = (ROOT / 'employee_movements/static/css/app.css').read_text(encoding='utf-8')
MANAGEMENT_CSS = (ROOT / 'employee_movements/static/css/pages/management.css').read_text(encoding='utf-8')


def test_management_stylesheet_is_loaded_only_for_management_routes():
    assert "request.path.startswith('/structure')" in BASE
    assert "request.path.startswith('/users')" in BASE
    assert "request.path.startswith('/delegations')" in BASE
    assert "filename='css/pages/management.css'" in BASE
    current_version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    assert f"?v={current_version}" in BASE
    assert (ROOT / 'employee_movements/static/css/pages/management.css').is_file()


def test_supervisor_user_creation_exposes_server_checked_governorate_scope():
    assert 'data-create-scope="supervisor" hidden' in USERS
    assert 'name="governorate_id" value="{{g.id}}"' in USERS
    assert "x.value==='مشرف محافظة'" in USERS
    assert 'scope.hidden=!sup' in USERS
    assert 'managerNote.hidden=!manager||admin' in USERS
    assert 'permissionPicker.hidden=admin' in USERS
    route = (ROOT / 'employee_movements/blueprints/users.py').read_text(encoding='utf-8')
    assert "request.form.getlist('governorate_id')" in route
    assert 'يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.' in route


def test_user_creation_describes_default_and_additional_permissions_truthfully():
    assert 'صلاحيات إضافية' in USERS
    assert 'هذا الدور لا يمنح صلاحيات إدارة الحسابات' in USERS
    assert 'يمنح الصلاحيات الإدارية الكاملة تلقائيًا' in USERS
    assert 'لا تلغي الافتراضيات' in USERS
    constants = (ROOT / 'employee_movements/constants.py').read_text(encoding='utf-8')
    assert "'مشرف محافظة':" in constants
    assert "'manage_employees'" in constants
    assert "'manage_movements'" in constants
    assert "'view_reports'" in constants


def test_admin_users_edit_and_delegation_templates_have_scoped_workspace_roots():
    assert 'class="ui-page admin-workspace"' in STRUCTURE
    assert 'class="ui-page users-workspace"' in USERS
    assert 'class="ui-page user-edit-workspace"' in USER_EDIT
    assert 'class="ui-page delegation-workspace"' in DELEGATIONS
    assert 'id="users-table"' in USERS
    assert 'data-delegation-filter="all"' in DELEGATIONS


def test_management_styles_are_responsive_and_preserve_accessible_focus():
    for media in ('@media (max-width: 1200px)', '@media (max-width: 900px)', '@media (max-width: 620px)', '@media (prefers-reduced-motion: reduce)'):
        assert media in MANAGEMENT_CSS
    assert '.users-choice-item:focus-within' in MANAGEMENT_CSS
    assert 'outline-offset: 2px' in MANAGEMENT_CSS
    assert '.admin-ai-kpi:focus-visible' in MANAGEMENT_CSS


def test_cleaned_shared_css_and_management_css_parse_without_css_syntax_errors():
    for source in (CSS, MANAGEMENT_CSS):
        rules = tinycss2.parse_stylesheet(source, skip_whitespace=False, skip_comments=False)
        assert not [rule for rule in rules if rule.type == 'error']
        # Inspect the nested rule lists, not only the top-level stylesheet tokens.
        pending = list(rules)
        while pending:
            rule = pending.pop()
            if rule.type == 'at-rule' and rule.content is not None:
                pending.extend(tinycss2.parse_rule_list(rule.content, skip_whitespace=False, skip_comments=False))
        assert re.search(r'\{[^{}]*\}', source, re.S)


def test_release_assets_use_the_single_68_24_0_cache_version():
    version = (ROOT / 'VERSION.md').read_text(encoding='utf-8').strip()
    init = (ROOT / 'employee_movements/__init__.py').read_text(encoding='utf-8')
    project = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    assert f"__version__ = '{version}'" in init
    assert f'version = "{version}"' in project
    assert BASE.count(f'?v={version}') == 14
    assert f'v{version}' in CSS.splitlines()[1]
