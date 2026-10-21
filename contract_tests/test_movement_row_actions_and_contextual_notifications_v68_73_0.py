"""Contracts for compact, state-aware movement actions and notification CTAs."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "employee_movements" / "templates"


def test_movement_listings_share_one_permission_aware_action_menu():
    template_path = TEMPLATES / "movements.html"
    source = template_path.read_text(encoding="utf-8")
    partial = (TEMPLATES / "partials" / "movement_actions.html").read_text(encoding="utf-8")
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    env.get_template("movements.html")
    env.get_template("partials/movement_actions.html")

    assert source.count("include 'partials/movement_actions.html'") == 3
    assert "can('manage_movements') and not (m.movement_type=='انتداب' and mission_is_closed)" in partial
    assert "can('view_reports') and can_view_movement(m)" in partial
    assert "عرض / طباعة المأمورية" in partial
    assert "m.is_active and m.from_date and not mission_is_closed" in partial
    assert "{% macro movement_action_menu" not in source  # Avoid duplicating the shared partial.
    # Prevent the old wrong action: every follow-up row linked to the assignment form,
    # even when the movement itself was a leave or permission.
    assert 'href="/movements/{{m.id}}/assignment-form">المأمورية' not in source


def test_table_action_menu_expands_in_flow_instead_of_being_clipped_by_scroll_wrap():
    css = (ROOT / "employee_movements" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".movement-row-action-menu-table[open] { display: inline-grid;" in css
    assert ".movement-row-action-menu-table[open] > .movement-row-action-list { position: static;" in css
    assert ".movement-row-action-menu > summary:focus-visible" in css
    assert ".movement-row-action-list a:focus-visible" in css


def test_notification_primary_action_depends_on_edit_scope_and_read_permission():
    source = (ROOT / "employee_movements" / "blueprints" / "notifications.py").read_text(encoding="utf-8")
    item = source.split("def _followup_item(", 1)[1].split("\n\ndef _followup_rows(", 1)[0]
    rows = source.split("def _followup_rows(", 1)[1].split("\n\n@bp.get('/notifications')", 1)[0]
    assert "*, can_edit=False" in item
    assert "action_label = 'مراجعة وتصحيح الحركة'" in item
    assert "action_url = f'/movements/{m.id}/edit'" in item
    assert "action_label = 'عرض المأمورية'" in item
    assert "action_url = f'/reports/assignments/print-mission/{m.id}'" in item
    assert "editable_branch_ids = set(bids())" in rows
    assert "supported_mutation_roles = {'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'}" in rows
    assert "items.append(_followup_item(movement, expressions, can_edit=can_edit))" in rows
    assert "can_manage_movement(movement)" not in rows
    assert "action_url': f'/movements/{m.id}/history'" not in item


def test_movement_and_notification_actions_keep_server_side_authorization_as_authority():
    access = (ROOT / "employee_movements" / "access.py").read_text(encoding="utf-8")
    routes = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    assert "def can_manage_movement(m=None):" in access
    edit_route = routes.split("def movement_edit(i):", 1)[1].split("\n\n@bp.", 1)[0]
    assert "can_manage_movement(m)" in edit_route
    assert "can('manage_movements')" in edit_route


def test_row_action_menus_close_on_outside_click_and_escape_restores_focus():
    js = (ROOT / "employee_movements" / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "details.movement-row-action-menu" in js
    assert "movementActionMenus.forEach(other=>{if(other!==menu)other.open=false;})" in js
    assert "event.key!=='Escape'" in js
    assert "opened.querySelector('summary')?.focus({preventScroll:true})" in js


def test_notification_action_links_are_descriptive_for_assistive_technology():
    page = (TEMPLATES / "notifications.html").read_text(encoding="utf-8")
    js = (ROOT / "employee_movements" / "static" / "js" / "notifications.js").read_text(encoding="utf-8")
    assert 'aria-label="{{item.action_label}}: {{item.title}}"' in page
    assert 'aria-label="${esc(x.action_label)}: ${esc(x.title)}"' in js
    assert 'aria-label="فتح ملف الموظف' in page
    assert 'aria-label="فتح ملف الموظف ${esc(x.title)}"' in js
