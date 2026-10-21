"""Regression contracts for the reports and assistant visual pass v68.53.1."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
REPORTS_HOME = (ROOT / "employee_movements/templates/reports_missions.html").read_text(encoding="utf-8")
REPORT_CATALOG = (ROOT / "employee_movements/templates/reports.html").read_text(encoding="utf-8")
MISSION_REPORTS = (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8")
MANAGER = (ROOT / "employee_movements/templates/manager_hub.html").read_text(encoding="utf-8")
ASSISTANT = (ROOT / "employee_movements/templates/assistant.html").read_text(encoding="utf-8")
ASSISTANT_DOCK = (ROOT / "employee_movements/templates/assistant_dock.html").read_text(encoding="utf-8")
REPORT_CSS = (ROOT / "employee_movements/static/css/pages/admin-reports-assistant.css").read_text(encoding="utf-8")
ASSISTANT_CSS = (ROOT / "employee_movements/static/css/pages/assistant-dock.css").read_text(encoding="utf-8")


def test_current_release_and_cache_busting_are_unified():
    assert (ROOT / "VERSION.md").read_text(encoding="utf-8").strip() == CURRENT_VERSION
    assert f'version = "{CURRENT_VERSION}"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"__version__ = '{CURRENT_VERSION}'" in (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert 'data-app-version="{{app_version}}"' in BASE
    assert BASE.count("v=app_version") == 24


def test_report_metrics_have_accessible_semantic_icons_and_distinct_categories():
    for kind in ("total", "leave", "assignment", "permission"):
        assert f"smart-report-metric {kind}" in REPORTS_HOME
        assert f"smart-report-metric-icon" in REPORTS_HOME
    assert REPORTS_HOME.count('aria-hidden="true"><svg viewBox="0 0 24 24">') >= 9
    for category in ("total", "leave", "assignment", "permission"):
        assert f".smart-report-metric.{category} .smart-report-metric-icon" in REPORT_CSS


def test_report_actions_preserve_routes_and_receive_semantic_icon_tiles():
    for href, cls in (
        ("/reports/leaves", "report-action-leave"),
        ("/reports/assignments", "report-action-assignment"),
        ("/reports/permissions", "report-action-permission"),
        ("/reports/assignments/print-missions", "report-action-print"),
        ("/missions/from-screenshot", "report-action-scan"),
    ):
        assert f'href="{href}"' in REPORTS_HOME
        assert cls in REPORTS_HOME
    assert "can('view_reports')" in REPORTS_HOME
    assert "can('manage_movements')" in REPORTS_HOME
    assert "smart-report-action-icon" in REPORT_CSS


def test_report_workspaces_keep_scope_filters_export_and_print_routes():
    assert "scope_required and not scope_selected" not in REPORTS_HOME
    assert "جميع المحافظات" in REPORTS_HOME
    assert "selected_governorate.id" in REPORTS_HOME
    assert 'href="/reports.csv"' in REPORTS_HOME
    assert 'href="/reports/assignments/print-missions"' in MISSION_REPORTS
    assert 'name="governorate_id"' in MISSION_REPORTS
    assert 'name="destination_governorate_id"' in MISSION_REPORTS
    assert "can('manage_movements')" in MISSION_REPORTS
    assert 'href="/reports/assignments/edit-requests"' in MISSION_REPORTS


def test_manager_and_audit_pages_get_shared_report_visual_tokens():
    assert "ui-grid-3-gap-16" in MANAGER
    assert 'href="/reports/assignments/edit-requests"' in MANAGER
    assert 'href="/reports/assignments/monthly"' in MANAGER
    assert 'body[data-workspace-path="/manager"] .ui-grid-3-gap-16 > .ui-card:nth-child(1)' in REPORT_CSS
    assert 'body[data-workspace-path^="/audit"] .audit-table-card table thead th' in REPORT_CSS


def test_assistant_dock_has_accessible_title_and_visual_header_mark():
    assert 'aria-label="فتح المساعد الذكي بسيوني"' in ASSISTANT_DOCK
    assert 'class="assistant-dock-label">المساعد الذكي</span>' in ASSISTANT_DOCK
    assert 'class="assistant-dock-panel-mark" aria-hidden="true"' in ASSISTANT_DOCK
    assert 'name="workspace_context"' in ASSISTANT_DOCK
    assert 'name="_csrf"' in ASSISTANT_DOCK
    assert ".assistant-dock-panel-title" in ASSISTANT_CSS
    assert ".assistant-dock-panel-mark" in ASSISTANT_CSS


def test_full_assistant_keeps_post_confirmation_privacy_and_scope_context():
    assert 'action="/assistant"' in ASSISTANT
    assert 'action="/assistant/confirm"' in ASSISTANT
    assert 'action="/assistant/clear"' in ASSISTANT
    assert 'name="workspace_context"' in ASSISTANT
    assert 'name="_csrf"' in ASSISTANT
    assert "assistant-chat-topbar" in ASSISTANT_CSS
    assert "assistant-chat-body .assistant-msg .chat-bubble" in ASSISTANT_CSS
    assert "assistant-chat-body .user-msg .chat-bubble" in ASSISTANT_CSS


def test_reports_assistant_styles_are_responsive_and_respect_reduced_motion():
    assert "@media (max-width:620px)" in REPORT_CSS
    assert "@media (max-width:620px)" in ASSISTANT_CSS
    assert "prefers-reduced-motion:reduce" in ASSISTANT_CSS
    assert "prefers-reduced-motion: reduce" in REPORT_CSS
