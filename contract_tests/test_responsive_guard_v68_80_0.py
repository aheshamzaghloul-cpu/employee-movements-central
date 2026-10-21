from pathlib import Path

ROOT = Path(__file__).parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
CSS = (ROOT / "employee_movements/static/css/ui-components.css").read_text(encoding="utf-8")


def test_responsive_guard_is_in_the_final_shared_component_layer():
    assert "css/ui-components.css" in BASE
    assert "v68.80.0 — shared responsive safeguards" in CSS


def test_content_and_controls_can_shrink_without_forcing_page_overflow():
    assert ".premium-main.with-shell > *" in CSS
    assert "min-width: 0;" in CSS
    assert ":where(input,select,textarea)" in CSS
    assert "overflow-wrap: anywhere;" in CSS


def test_table_scrolling_is_confined_to_explicit_wrappers():
    assert ":where(.ui-table-wrap,.ui-overflow-auto,.ui-movement-audit-table)" in CSS
    assert "overflow-x: auto;" in CSS
    assert "overscroll-behavior-inline: contain;" in CSS


def test_small_viewports_and_reduced_motion_are_supported():
    assert "@media (max-width: 700px)" in CSS
    assert "@media (max-width: 380px)" in CSS
    assert "@media (prefers-reduced-motion: reduce)" in CSS


def test_sidebar_and_permission_context_remain_in_base_shell():
    assert 'id="appSidebar"' in BASE
    assert 'data-active-role="{{active_role or \'\'}}"' in BASE
    assert 'aria-label="تحديد محافظة العمل"' in BASE
