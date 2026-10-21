from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "employee_movements" / "templates"
APP = (ROOT / "employee_movements" / "static" / "js" / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements" / "static" / "css" / "app.css").read_text(encoding="utf-8")
BASE = (T / "base.html").read_text(encoding="utf-8")


def test_long_tables_have_progressive_show_more_and_clear_counts():
    assert "smart-data-more" in APP
    assert "عرض المزيد" in APP
    assert "عرض أقل" in APP
    assert "عرض ${visible} من ${matches.length}" in APP or "عرض ${shown} من ${matches.length} نتيجة" in APP
    assert "smart-data-more[hidden]" in CSS


def test_report_filters_keep_primary_choices_visible_and_collapse_secondary_choices():
    missions = (T / "mission_reports.html").read_text(encoding="utf-8")
    employee_report = (T / "employee_type_report.html").read_text(encoding="utf-8")
    assert "workspace-advanced-filters" in missions
    assert "destination_governorate_id" in missions and "destination_branch_id" in missions
    assert "workspace-advanced-filters" in employee_report
    assert "date_from" in employee_report and "date_to" in employee_report


def test_admin_people_and_notifications_are_searchable_progressive_lists():
    users = (T / "users.html").read_text(encoding="utf-8")
    notifications = (T / "notifications.html").read_text(encoding="utf-8")
    assert 'data-progressive-list data-page-size="8"' in users
    assert "data-progressive-item data-search=" in users
    assert "data-progressive-search" in users
    assert 'data-progressive-list data-page-size="8"' in notifications
    assert "data-progressive-item data-search=" in notifications
    assert "data-progressive-search" in notifications
    assert "workspace-optional-options" in users


def test_remaining_report_tables_use_the_shared_smart_table_surface():
    for name in ("mission_monthly.html", "mission_edit_requests.html", "manager_hub.html"):
        template = (T / name).read_text(encoding="utf-8")
        assert "data-smart-table" in template, name
    assert "data-page-size=\"8\"" in (T / "manager_hub.html").read_text(encoding="utf-8")


def test_current_release_and_assets_are_synchronized():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    init = (ROOT / "employee_movements" / "__init__.py").read_text(encoding="utf-8")
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert len(version.split(".")) == 3 and all(part.isdigit() for part in version.split("."))
    assert f"__version__ = '{version}'" in init
    assert f'version = "{version}"' in project
    assert "v=app_version" in BASE


def test_employee_report_groups_and_supervisor_governorate_checklist_are_progressive():
    app_js = (ROOT / "employee_movements" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    users = (T / "users.html").read_text(encoding="utf-8")
    assert "data-report-search-more" in app_js
    assert "const pageSize=8;let expanded=false,previousQuery=''" in app_js
    assert "users-governorate-options" in users
    assert "data-create-scope-summary" in users
    assert "input[name=\"governorate_id\"]" in users


def test_excel_import_review_is_progressive_without_scrolling_toolbar_away():
    excel = (T / "excel_import.html").read_text(encoding="utf-8")
    assert 'table class="ui-data-table ui-min-1000" data-smart-table data-page-size="10"' in excel
    assert "تحديد كل التغييرات" in excel and "جميع مربعات التحديث في الطلب" in excel
    assert "const scrollSurface=table.closest('.ui-overflow-auto')" in APP
    assert "wrap.insertBefore(bar,surface)" in APP
    assert "surface.insertAdjacentElement('afterend',more)" in APP
