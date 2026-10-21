from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSIONS = ROOT / "employee_movements" / "blueprints" / "missions.py"

def test_manager_mission_edit_queue_requires_selected_work_scope_and_filters_source_records():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_edit_requests(")
    end = source.index("@bp.get('/reports/assignments/edit-requests/<int:request_id>')", start)
    route = source[start:end]
    assert "if not scope_governorate_id():" in route
    assert "scoped_branch_ids = set(bids())" in route
    assert "list_pending_mission_edit_requests(rs, scoped_branch_ids)" in route
    assert "all_branch_ids" not in route

def test_manager_review_page_requires_source_mission_inside_selected_scope():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_edit_request_review(")
    end = source.index("@bp.post('/reports/assignments/edit-requests/<int:request_id>')", start)
    route = source[start:end]
    assert "if not scope_governorate_id():" in route
    assert "not branch_ok(r.movement.employee.branch_id)" in route
    assert "mission_edit_request_review_context(r)" in route

def test_manager_save_rechecks_source_scope_and_allows_valid_active_destination():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_edit_request_save(")
    end = source.index("@bp.get('/reports/assignments/export.xlsx')", start)
    route = source[start:end]
    assert "not scope_governorate_id()" in route
    assert "not branch_ok(m.employee.branch_id)" in route
    assert "allowed_destination_ids = {" in route
    assert "allowed_destination_branch_ids=allowed_destination_ids" in route

def test_closed_mission_direct_edit_remains_blocked_outside_manager_request_workflow():
    source = MISSIONS.read_text(encoding="utf-8")
    start = source.index("def mission_edit_save(")
    end = source.index("@bp.post('/reports/assignments/mission-close/<int/movement_id>')", start)
    route = source[start:end]
    assert "if mission_state_label(m) == 'مغلقة':" in route
    assert "لا تعدّل المأمورية المغلقة مباشرة" in route
