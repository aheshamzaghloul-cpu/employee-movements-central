"""Regression contracts for bounded operational notifications and actionable alerts."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _notification_source():
    return (ROOT / "employee_movements" / "blueprints" / "notifications.py").read_text(encoding="utf-8")


def test_notification_list_is_page_bounded_and_eager_loads_displayed_relationships():
    source = _notification_source()
    start = source.index("def _followup_rows(")
    end = source.index("\n\n@bp.get('/notifications')", start)
    section = source[start:end]
    assert ".limit(page_size)" in section
    assert ".offset((page - 1) * page_size)" in section
    assert "joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate)" in section
    assert "joinedload(Movement.destination).joinedload(Branch.governorate)" in section


def test_notification_metrics_are_aggregated_in_sql_instead_of_loading_all_rows():
    source = _notification_source()
    start = source.index("def _followup_stats(")
    end = source.index("\n\ndef _followup_item(", start)
    section = source[start:end]
    assert "func.count(Movement.id)" in section
    assert ".group_by(severity)" in section
    assert "for level, count in query.order_by(None).with_entities(" in section
    assert "query.order_by(None).all()" not in section


def test_followup_rules_include_missing_fields_and_inconsistent_dates():
    source = _notification_source()
    for expected in (
        "missing_destination =",
        "missing_start =",
        "reversed_dates =",
        "closed_missing_end =",
        "'تعارض تواريخ'",
        "'تاريخ نهاية مفقود'",
        "'جهة انتداب غير محددة'",
    ):
        assert expected in source


def test_notification_api_returns_global_totals_not_only_popover_slice():
    source = _notification_source()
    start = source.index("def notifications_items():")
    end = source.index("\n\n@bp.get('/api/notifications/summary')", start)
    section = source[start:end]
    assert "items, stats, _, _ = _followup_rows(page=1, page_size=8)" in section
    assert "**stats" in section
    js = (ROOT / "employee_movements" / "static" / "js" / "notifications.js").read_text(encoding="utf-8")
    assert "d.total??items.length" in js
    assert "d.urgent" in js
    assert "async function loadSummary()" in js
    assert "fetch('/api/notifications/summary'" in js
    assert js.rstrip().endswith("loadSummary();\n})();")


def test_notification_page_shows_full_severity_metrics_and_pagination():
    template = (ROOT / "employee_movements" / "templates" / "notifications.html").read_text(encoding="utf-8")
    assert "notification_stats.urgent" in template
    assert "notification_stats.warning" in template
    assert "notification_stats.info" in template
    assert "notification_page_count" in template
    assert "عاجل / يحتاج تصحيح" in template
    assert "نقص بيانات أو قرب الانتهاء" in template
    assert "previous_page_url" in template
    assert "next_page_url" in template
