from pathlib import Path


def test_manager_mission_edit_queue_uses_selected_scope():
    source = Path("employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    start = source.index("def mission_edit_requests(")
    end = source.index("@bp.get('/reports/assignments/edit-requests/<int:request_id>')", start)
    route = source[start:end]
    assert "if 'مسؤول التطبيق' in rs:" in route
    assert "list_pending_mission_edit_requests(rs, bids())" in route
    assert "all_branch_ids" in route


def test_manager_review_page_filters_destination_choices_and_source_scope():
    source = Path("employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    start = source.index("def mission_edit_request_review(")
    end = source.index("@bp.post('/reports/assignments/edit-requests/<int:request_id>')", start)
    route = source[start:end]
    assert "if 'مسؤول التطبيق' not in rs and not branch_ok(r.movement.employee.branch_id):" in route
    assert "allowed_ids = set(bids())" in route
    assert "branch.id in allowed_ids" in route
    assert "gov.id in allowed_gov_ids" in route


def test_manager_save_route_rechecks_source_scope():
    source = Path("employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    start = source.index("def mission_edit_request_save(")
    end = source.index("@bp.get('/reports/assignments/export.xlsx')", start)
    route = source[start:end]
    assert "if 'مسؤول التطبيق' not in rs and not branch_ok(m.employee.branch_id):" in route


def test_manager_direct_mission_edit_enforces_destination_scope():
    source = Path("employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    start = source.index("def mission_edit_save(")
    end = source.index("@bp.post('/reports/assignments/mission-close/<int:movement_id>')", start)
    route = source[start:end]
    assert "destination.id not in set(bids())" in route
    assert "'مسؤول التطبيق' not in roles()" in route

def test_manager_regular_movement_edit_enforces_destination_scope():
    source = Path("employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    start = source.index("def movement_edit(i):")
    end = source.index("@bp.post('/movements/<int:i>/submit')", start)
    route = source[start:end]
    assert "destination.id not in set(bids())" in route
    assert "'مسؤول التطبيق' not in roles()" in route
    assert "branch.id in set(bids())" in route
