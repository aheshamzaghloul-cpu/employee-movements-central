from pathlib import Path

from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "employee_movements" / "templates"
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
CENTER = TEMPLATES / "mission_reports.html"


def test_mission_center_uses_one_selected_record_action_surface():
    text = CENTER.read_text(encoding="utf-8")
    assert "data-mission-selection" in text
    assert 'name="mission_selected"' in text
    assert "data-selected-print" in text
    assert "data-selected-edit" in text
    assert "data-selected-close" in text
    assert "data-selected-reopen" not in text
    assert "class=\"ui-mission-actions\"" not in text
    assert 'data-smart-server-page="true"' in text


def test_mission_date_range_is_visible_before_advanced_filters():
    text = CENTER.read_text(encoding="utf-8")
    assert 'id="missionDateFrom" type="date" name="date_from"' in text
    assert 'id="missionDateTo" type="date" name="date_to"' in text
    assert text.index("mission-period-bar") < text.index("workspace-advanced-filters")
    assert "mission_state" in text and "destination_governorate_id" in text


def test_legacy_mission_preview_url_redirects_to_canonical_pdf_workflow():
    text = MISSIONS.read_text(encoding="utf-8")
    start = text.index("def mission_print(movement_id):")
    body = text[start:]
    assert "return redirect(url_for('missions.mission_pdf', movement_id=m.id))" in body
    assert "return render_template(\n        'mission_print.html'" not in body
    assert "m.movement_type != 'انتداب'" in body


def test_same_page_mission_center_links_are_not_duplicated_as_cards():
    reports = (TEMPLATES / "reports.html").read_text(encoding="utf-8")
    assert reports.count('href="/reports/assignments/print-missions"') == 1
    reports_missions = (TEMPLATES / "reports_missions.html").read_text(encoding="utf-8")
    assert "smart-report-print-card" not in reports_missions
    workspace_actions = (TEMPLATES / "workspace_actions.html").read_text(encoding="utf-8")
    assert "request.path != '/reports/assignments/print-missions'" in workspace_actions


def test_mission_center_template_contracts_parse_and_close_routes_keep_server_guards():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)))
    for name in ("mission_reports.html", "reports.html", "reports_missions.html", "workspace_actions.html"):
        env.get_template(name)

    source = MISSIONS.read_text(encoding="utf-8")
    close = source.split("def mission_close(", 1)[1].split("@bp.post('/reports/assignments/mission-reopen", 1)[0]
    assert "not can('manage_movements') or not can_manage_movement(m)" in close
    assert "movement_overlaps(" in close
    assert "close_mission(m)" in close
    reopen_body = source.split("def mission_reopen(", 1)[1].split("@bp.get('/reports/assignments/mission-print-date", 1)[0]
    assert "لا يمكن إعادة فتح المأمورية مباشرة" in reopen_body
    assert "context['mission_state_label'] = mission_state_label" in source


def test_mission_center_interactions_confirm_and_clear_hidden_selection():
    js = (ROOT / "employee_movements" / "static" / "js" / "mission_center.js").read_text(encoding="utf-8")
    assert "clearSelection" in js
    assert "new MutationObserver" in js
    assert "if (selected && selected.hidden) clearSelection();" in js
    assert "window.confirm('هل تريد إغلاق المأمورية المختارة؟" in js
    assert "data-selected-request-reason" in (ROOT / "employee_movements" / "templates" / "mission_reports.html").read_text(encoding="utf-8")



def test_supervisor_edit_request_returns_to_current_center_filters():
    source = MISSIONS.read_text(encoding="utf-8")
    body = source.split("def mission_edit_request_create(", 1)[1].split("@bp.get('/reports/assignments/edit-requests')", 1)[0]
    assert body.count("_mission_center_return_url()") == 4
