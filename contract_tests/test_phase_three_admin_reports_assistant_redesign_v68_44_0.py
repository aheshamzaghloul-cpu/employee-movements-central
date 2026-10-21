from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
STRUCTURE = (ROOT / "employee_movements/templates/structure.html").read_text(encoding="utf-8")
USERS = (ROOT / "employee_movements/templates/users.html").read_text(encoding="utf-8")
USER_EDIT = (ROOT / "employee_movements/templates/user_edit.html").read_text(encoding="utf-8")
REPORTS = (ROOT / "employee_movements/templates/reports.html").read_text(encoding="utf-8")
REPORTS_MISSIONS = (ROOT / "employee_movements/templates/reports_missions.html").read_text(encoding="utf-8")
MISSION_REPORTS = (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8")
MANAGER = (ROOT / "employee_movements/templates/manager_hub.html").read_text(encoding="utf-8")
AUDIT = (ROOT / "employee_movements/templates/audit.html").read_text(encoding="utf-8")
DOCK = (ROOT / "employee_movements/templates/assistant_dock.html").read_text(encoding="utf-8")
ASSISTANT = (ROOT / "employee_movements/templates/assistant.html").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements/static/css/pages/admin-reports-assistant.css").read_text(encoding="utf-8")
ASSISTANT_CSS = (ROOT / "employee_movements/static/css/pages/assistant-dock.css").read_text(encoding="utf-8")


def test_release_metadata_and_global_stylesheet_cache_buster_are_synchronized():
    assert (ROOT / "VERSION.md").read_text(encoding="utf-8").strip() == CURRENT_VERSION
    assert f'version = "{CURRENT_VERSION}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"__version__ = '{CURRENT_VERSION}'" in (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert 'data-app-version="{{app_version}}"' in BASE
    assert BASE.count("v=app_version") == 24
    assert BASE.index("css/design-system-cyan.css") < BASE.index("css/pages/admin-reports-assistant.css")
    assert "filename='css/pages/assistant-dock.css', v=app_version)" in BASE
    assert "startswith('/structure')" in BASE[:BASE.index("css/pages/admin-reports-assistant.css")]


def test_admin_and_user_permission_markup_keeps_role_gates_and_form_contracts():
    assert "{% if admin_view %}" in STRUCTURE
    for href in ('href="/governorates"', 'href="/branches"', 'href="/users"', 'href="/audit"'):
        assert href in STRUCTURE
    assert 'name="roles"' in USERS and 'name="permissions"' in USERS
    assert 'name="governorate_id"' in USERS
    assert 'data-create-permission-picker' in USERS
    assert 'name="roles"' in USER_EDIT and 'name="permissions"' in USER_EDIT
    assert "{% if 'مسؤول التطبيق' in roles %}" in USER_EDIT


def test_reports_preserve_report_actions_scope_hints_and_filters():
    for href in ('/reports/leaves', '/reports/assignments', '/reports/permissions', '/reports/assignments/print-missions'):
        assert href in REPORTS
    assert "اختر المحافظة أولًا" not in REPORTS_MISSIONS
    assert "جميع المحافظات" in REPORTS_MISSIONS
    assert "محافظة العمل تحدد صلاحية تنفيذ التغييرات ولا تمنع الاطلاع على التقارير" in REPORTS_MISSIONS
    assert 'name="governorate_id"' in MISSION_REPORTS
    assert 'name="destination_governorate_id"' in MISSION_REPORTS
    assert 'name="mission_state"' in MISSION_REPORTS
    assert 'url_for(\'missions.mission_export_xlsx\'' in MISSION_REPORTS


def test_manager_and_audit_pages_use_structured_workspace_wrappers():
    assert '<div class="ui-page manager-hub-workspace">' in MANAGER
    assert MANAGER.count("/reports/assignments/edit-requests") >= 2
    assert '<div class="ui-page audit-workspace">' in AUDIT
    for column in ("التاريخ", "المستخدم", "العملية", "الكيان", "التفاصيل"):
        assert column in AUDIT
    assert "audit_users.get(x.user_id" in AUDIT


def test_assistant_launcher_shows_a_visible_label_and_retains_accessible_name():
    assert 'aria-label="فتح المساعد الذكي بسيوني"' in DOCK
    assert 'class="basyouni-mark" aria-hidden="true"><svg' in DOCK
    assert 'class="assistant-dock-label">المساعد الذكي</span>' in DOCK
    assert "بسيوني — المساعد الذكي" in DOCK
    assert 'id="assistantDockToggle"' in DOCK and 'id="assistantDockPanel"' in DOCK
    assert 'action="/assistant"' in ASSISTANT
    assert 'name="workspace_context"' in ASSISTANT and 'name="prompt"' in ASSISTANT


def test_scoped_visual_system_covers_admin_reports_permissions_audit_and_assistant():
    required = (
        ".admin-workspace .admin-ai-hero",
        ".users-workspace .users-choice-item:has(input:checked)",
        ".ui-report-link-grid > a:focus-visible",
        ".ui-mission-results",
        "body[data-workspace-path=\"/manager\"] .ui-grid-3-gap-16 > .ui-card",
        "body[data-workspace-path^=\"/audit\"] .audit-table-card",
        "@media (prefers-reduced-motion: reduce)",
    )
    for selector in required:
        assert selector in CSS, selector
    for selector in (".assistant-dock-trigger .basyouni-mark svg", ".assistant-chat-shell", ".assistant-dock-panel", "@media (prefers-reduced-motion: reduce)"):
        assert selector in ASSISTANT_CSS, selector
    assert "outline: 3px solid rgba(20, 124, 173, .2)" in CSS
    assert "@media (max-width: 620px)" in CSS


def test_official_print_document_templates_are_not_restyled_by_this_page_css():
    # The new CSS targets interactive workspace classes and does not target official print body/layout classes.
    assert ".assignment-print" not in CSS
    assert ".mission-print" not in CSS
