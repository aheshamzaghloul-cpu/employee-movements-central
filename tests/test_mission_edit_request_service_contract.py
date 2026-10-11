from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"
SERVICE = ROOT / "employee_movements" / "services" / "mission_edit_request.py"


def test_edit_request_routes_delegate_domain_work_to_service():
    text = MISSIONS.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")

    assert "create_mission_edit_request(m, reason)" in text
    assert "list_pending_mission_edit_requests(rs, bids())" in text
    assert "mission_edit_request_review_context(r)" in text
    assert "validate_and_execute_mission_edit_request(" in text

    create_body = text[text.index("def mission_edit_request_create"):text.index("@bp.get('/reports/assignments/edit-requests')")]
    list_body = text[text.index("def mission_edit_requests"):text.index("@bp.get('/reports/assignments/edit-requests/<int:request_id>')")]
    save_body = text[text.index("def mission_edit_request_save"):text.index("@bp.get('/reports/assignments/export.xlsx')")]

    assert "MissionEditRequest.query.filter_by" not in create_body
    assert "MissionEditRequest.query" not in list_body
    assert "movement_overlaps(" not in save_body
    assert "execute_edit_request(" not in save_body

    for marker in (
        "MissionEditRequest.query.filter_by",
        "create_mission_edit_request",
        "list_pending_mission_edit_requests",
        "mission_edit_request_review_context",
        "validate_and_execute_mission_edit_request",
        "movement_overlaps(",
        "execute_edit_request(",
        "PENDING_STATUS",
    ):
        assert marker in service, f"Mission edit-request service lost required behavior: {marker}"


def test_concurrent_duplicate_mission_edit_requests_roll_back_cleanly():
    service = SERVICE.read_text(encoding="utf-8")
    assert "from sqlalchemy.exc import IntegrityError" in service
    assert "except IntegrityError:" in service
    assert "db.session.rollback()" in service
    assert "return None" in service[service.index("except IntegrityError:"):service.index("except Exception:")]
    assert "db.session.commit()" in service


def test_reviewed_mission_edit_enforces_destination_scope_server_side():
    route = MISSIONS.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    save_body = route[route.index("def mission_edit_request_save"):route.index("@bp.get('/reports/assignments/export.xlsx')")]
    assert "allowed_destination_ids = None if 'مسؤول التطبيق' in rs else set(bids())" in save_body
    assert "allowed_destination_branch_ids=allowed_destination_ids" in save_body
    assert "destination.id not in set(allowed_destination_branch_ids)" in service
