from pathlib import Path

from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = ROOT / "employee_movements" / "blueprints" / "movements.py"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
BASE_TEMPLATE = ROOT / "employee_movements" / "templates" / "base.html"
MOVEMENT_TEMPLATE = ROOT / "employee_movements" / "templates" / "movement_edit.html"
MISSION_TEMPLATE = ROOT / "employee_movements" / "templates" / "mission_edit.html"
ALERT_CSS = ROOT / "employee_movements" / "static" / "css" / "design-system-cyan.css"


def test_movement_edit_correctable_validation_errors_rerender_submitted_values():
    source = MOVEMENTS.read_text(encoding="utf-8")
    helper = source.split("def _render_movement_edit_form(m, form_values=None, return_to=None):", 1)[1].split(
        "@bp.route('/movements/<int:i>/edit'", 1
    )[0]
    route = source.split("def movement_edit(i):", 1)[1].split(
        "@bp.post('/movements/<int:i>/submit')", 1
    )[0]
    template = MOVEMENT_TEMPLATE.read_text(encoding="utf-8")

    assert "form_values=dict(form_values or {})" in helper
    assert "return _render_movement_edit_form(m, f.to_dict(), return_to)" in route
    validation_section = route.split("err = validate_movement_fields(", 1)[1]
    assert "return _render_movement_edit_form(m, f.to_dict(), return_to)" in validation_section
    assert "return redirect(url_for('movements.movement_edit', i=i))" not in validation_section
    for field in ("movement_type", "leave_type", "destination_governorate_id", "destination_branch_id", "from_date", "to_date", "permission_date"):
        assert f"form_values.get('{field}'" in template
    assert 'name="destination_governorate_id"' in template
    assert "emps=(" not in route and "bs=(" not in route
    assert "allBranches.filter(x=>x.gov===gid)" in template
    assert "branch.disabled=!gid" in template


def test_mission_edit_validation_rerenders_values_and_preserves_return_path():
    source = MISSIONS.read_text(encoding="utf-8")
    helper = source.split("def _render_mission_edit_form(m, form_values=None, return_to=None):", 1)[1].split(
        "@bp.get('/reports/assignments/mission-edit/<int:movement_id>')", 1
    )[0]
    route = source.split("def mission_edit_save(movement_id):", 1)[1].split(
        "@bp.post('/reports/assignments/mission-ticket-image/", 1
    )[0]
    template = MISSION_TEMPLATE.read_text(encoding="utf-8")

    assert "form_values=dict(form_values or {})" in helper
    assert "return_to=_mission_center_return_url(return_to)" in helper
    assert "_render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))" in route
    assert 'name="destination_governorate_id"' in template
    for field in ("destination_governorate_id", "destination_branch_id", "from_date", "to_date"):
        assert f"form_values.get('{field}'" in template
    assert "missionEditFormHint" in template


def test_global_flash_messages_preserve_categories_and_accessible_live_roles():
    template = BASE_TEMPLATE.read_text(encoding="utf-8")
    css = ALERT_CSS.read_text(encoding="utf-8")
    assert "get_flashed_messages(with_categories=true)" in template
    assert "enterprise-alert--{{alert_tone}}" in template
    assert "role=\"{% if alert_tone in ['warning', 'error', 'danger'] %}alert{% else %}status{% endif %}\"" in template
    for tone in ("success", "info", "warning", "error", "danger", "message"):
        assert f".enterprise-alert--{tone}" in css


def test_edited_templates_remain_valid_jinja():
    env = Environment()
    for path in (BASE_TEMPLATE, MOVEMENT_TEMPLATE, MISSION_TEMPLATE):
        env.parse(path.read_text(encoding="utf-8"))
