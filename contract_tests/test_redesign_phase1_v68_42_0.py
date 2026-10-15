from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
LOGIN = (ROOT / "employee_movements/templates/login.html").read_text(encoding="utf-8")
DESIGN = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
TOKENS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")


def test_phase_one_version_and_cache_busting_are_synchronized():
    assert (ROOT / "VERSION.md").read_text(encoding="utf-8").strip() == "68.49.0"
    assert 'version = "68.49.0"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "__version__ = '68.49.0'" in (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert BASE.count("v=68.49.0") == 21
    assert 'data-app-version="68.49.0"' in BASE


def test_design_tokens_have_one_canonical_root_block():
    assert len(re.findall(r"(?m)^:root\s*\{", TOKENS)) == 1
    assert not re.search(r"(?m)^:root\s*\{", DESIGN)
    assert "--ui-brand: #147cad;" in TOKENS
    assert "--ui-brand-strong: #126c9b;" in TOKENS
    assert "--ui-accent: #147cad;" in TOKENS
    assert "--ui-content: 1580px;" in TOKENS


def test_sidebar_navigation_is_grouped_without_relaxing_role_gates():
    assert 'aria-label="مساحة العمل الأساسية"' in BASE
    assert 'aria-label="التقارير والمتابعة"' in BASE
    assert 'premium-nav-label">التقارير والمتابعة' in BASE
    assert "can('manage_movements') and can_manage_movement()" in BASE
    assert "'مشرف محافظة' in roles and 'مسؤول التطبيق' not in roles" in BASE
    assert "'Manager Application Support' in roles or 'مسؤول التطبيق' in roles" in BASE
    assert 'href="/structure"' in BASE


def test_scope_selector_uses_a_real_selected_value_and_clear_label():
    assert 'aria-label="تحديد محافظة العمل"' in BASE
    assert 'aria-label="محافظة العمل"' in BASE
    assert 'value="{{scope_selected}}" selected>{{scope_governorate.name}}' in BASE
    assert 'value="" selected disabled>اختر المحافظة</option>' in BASE
    assert 'class="ui-visually-hidden"' in BASE
    assert 'smart-scope-form' not in HOME
    # Work scope is represented once in the home hero; the actual selector remains in the topbar.
    context = HOME[HOME.index('<div class="smart-context">'):HOME.index('</div>', HOME.index('<div class="smart-context">'))]
    assert "today.strftime" in context
    assert "scope_governorate.name" not in context


def test_login_branding_is_shared_and_form_labels_are_programmatically_associated():
    assert 'aria-labelledby="loginBrandTitle"' in LOGIN
    assert 'id="loginBrandTitle"' in LOGIN
    assert '<svg viewBox="0 0 24 24"><path d="M6 4h12v4H9v4h7v4H9v4H6V4Z"/></svg>' in LOGIN
    assert 'label for="loginUsername"' in LOGIN
    assert 'id="loginUsername" name="username" type="text"' in LOGIN
    assert 'aria-labelledby="loginFormTitle"' in LOGIN
    assert "login-trust-note" in LOGIN


def test_mobile_topbar_does_not_hide_governorate_or_role_controls():
    assert ".ui-top-actions.premium-top-actions { display: flex !important;" in DESIGN
    assert "overflow-x: auto" in DESIGN
    assert ".premium-top-actions .ui-scope-form select" in DESIGN
    assert ".premium-top-actions .prominent-role-switch select" in DESIGN
    assert ".ui-visually-hidden" in DESIGN


def test_home_actions_and_status_keep_their_existing_workflow_entrypoints():
    assert 'id="homeStartMovementAction"' in HOME
    assert 'href="/movements#movement-create"' in HOME
    assert 'id="home-mission-from-attachment"' in HOME
    assert 'href="/missions/from-screenshot"' in HOME
    assert 'id="employee-search"' in (ROOT / "employee_movements/templates/home_global_search.html").read_text(encoding="utf-8")
    assert 'id="employee-status"' in HOME


def test_phase_one_changes_do_not_touch_data_and_permission_logic():
    # Scope rules remain permission-gated; user-facing role labels do not change submitted values.
    assert 'name="active_role"' in BASE
    assert '<option value="{{r}}"' in BASE
    assert "can('manage_movements') and can_manage_movement()" in BASE
    assert "name=\"governorate_id\"" in BASE
