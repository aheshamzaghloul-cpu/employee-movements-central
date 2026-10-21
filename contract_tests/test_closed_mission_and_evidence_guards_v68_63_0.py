"""Regression contracts for legacy closure states and mission evidence handling."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_legacy_mission_state_also_marks_assignment_as_closed():
    assignments = _read("employee_movements/assignments.py")
    start = assignments.index("def assignment_state(")
    end = assignments.index("\n\ndef latest_assignment_summaries(", start)
    section = assignments[start:end]
    assert "if movement_is_closed(m):" in section
    assert "from .access import actual_roles, bids, branch_ok, me, movement_is_closed" in assignments


def test_current_movement_resolver_excludes_both_closed_markers():
    assignments = _read("employee_movements/assignments.py")
    start = assignments.index("def resolve_current_movement(")
    end = assignments.index("\n\ndef current_assignment_for_employee(", start)
    section = assignments[start:end]
    assert "not movement_is_closed(m)" in section
    assert "from .access import actual_roles, bids, branch_ok, me, movement_is_closed" in assignments
    assert "assignment_open_filter(Movement)" in assignments
    for name in ("current_assignment_for_employee", "employees_effectively_in_branches", "assignment_followups"):
        start = assignments.index(f"def {name}(")
        next_def = assignments.find("\n\ndef ", start + 5)
        section = assignments[start: next_def if next_def >= 0 else len(assignments)]
        assert "assignment_open_filter" in section or "movement_is_closed" in section, name


def test_home_status_sql_does_not_mark_closed_legacy_missions_as_current():
    source = _read("employee_movements/blueprints/dashboard.py")
    start = source.index("def current_employee_status_rows(")
    end = source.index("\n\n@bp.get('/')", start)
    section = source[start:end]
    assert "assignment_open_filter(Movement)" in section
    assert "from ..movement_state import assignment_open_filter" in source


def test_permission_matrix_keeps_global_read_separate_from_scoped_mutations():
    constants = _read("employee_movements/constants.py")
    access = _read("employee_movements/access.py")
    assert "'مسؤول التطبيق': set(PERMISSIONS)" in constants
    assert "'Manager Application Support':" in constants
    assert "'delete_movements'" in constants
    assert "if permission == 'view_reports' and active_roles & set(LOGIN_ROLES):" in access
    assert "Mutations require the selected work governorate" in access
    assert "if not selected:" in access[access.index("def can_manage_movement("):]


def test_mission_image_is_reviewed_then_persisted_and_appended_to_official_pdf():
    missions = _read("employee_movements/blueprints/missions.py")
    docs = _read("employee_movements/services/mission_documents.py")
    scan = missions[missions.index("def mission_from_screenshot_scan("):missions.index("@bp.post('/missions/from-screenshot/create')")]
    create = missions[missions.index("def mission_from_screenshot_create("):missions.index("@bp.", missions.index("def mission_from_screenshot_create("))]
    assert "extract_ticket_fields(image)" in scan
    assert "MissionTicketImageDraft(" in scan
    assert "ticket_image_saved=True" in scan
    assert "expects_ticket_image" in create
    assert "MissionTicketImage(" in create
    assert "ticket_image_data=ticket_image.image_data if ticket_image else None" in missions
    assert "if ticket_image_data:" in docs
    assert "_append_ticket_image_page(doc, ticket_image_data, mission, employee, root_path)" in docs


def test_closed_mission_edit_decision_is_manager_only_and_not_direct_edit():
    missions = _read("employee_movements/blueprints/missions.py")
    start = missions.index("def mission_edit_request_save(")
    end = missions.find("@bp.", start)
    section = missions[start:end if end >= 0 else len(missions)]
    assert "if 'Manager Application Support' not in rs or not can('manage_movements'):" in section
    edit_start = missions.index("def mission_edit_save(")
    edit_end = missions.index("@bp.post('/reports/assignments/mission-ticket-image", edit_start)
    direct_edit = missions[edit_start:edit_end]
    assert "if mission_state_label(m) == 'مغلقة':" in direct_edit
    assert "لا تعدّل المأمورية المغلقة مباشرة" in direct_edit
