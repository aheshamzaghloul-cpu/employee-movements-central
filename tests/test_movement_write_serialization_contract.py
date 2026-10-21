from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _function_block(source, signature, next_marker):
    start = source.index(signature)
    end = source.index(next_marker, start)
    return source[start:end]


def test_employee_and_movement_lock_helpers_use_refreshing_row_locks():
    source = (ROOT / 'employee_movements' / 'validation.py').read_text(encoding='utf-8')
    assert 'def lock_employee_for_movement(employee_id):' in source
    assert 'Employee.query.filter(Employee.id == normalized_id)' in source
    assert '.populate_existing()' in source
    assert '.with_for_update()' in source
    assert 'def lock_movement_for_employee(movement_id, employee_id):' in source
    assert 'Movement.employee_id == normalized_employee_id' in source


def test_html_movement_create_and_edit_serialize_writes_before_overlap_check():
    source = (ROOT / 'employee_movements' / 'blueprints' / 'movements.py').read_text(encoding='utf-8')
    create = _function_block(source, 'def movement_create():', "@bp.route('/movements/<int:i>/edit'")
    assert 'employee = lock_employee_for_movement(employee.id)' in create
    assert create.index('lock_employee_for_movement') < create.index('movement_overlaps(')
    edit = _function_block(source, 'def movement_edit(i):', "@bp.post('/movements/<int:i>/submit'")
    assert 'lock_employee_for_movement(m.employee_id)' in edit
    assert 'lock_movement_for_employee(i, locked_employee.id)' in edit
    assert edit.index('lock_movement_for_employee') < edit.index('movement_overlaps(')
    close = _function_block(source, 'def close_assignment(i):', "@bp.get('/movements/<int:i>/assignment-form')")
    assert 'lock_employee_for_movement(m.employee_id)' in close
    assert 'lock_movement_for_employee(i, locked_employee.id)' in close
    assert close.index('lock_movement_for_employee') < close.index('movement_overlaps(')


def test_mission_ticket_create_and_lifecycle_writes_lock_before_conflict_check():
    source = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
    create = _function_block(source, 'def mission_from_screenshot_create():', "@bp.post('/reports/assignments/mission-edit/")
    assert 'lock_employee_for_movement(employee.id)' in create
    assert create.index('lock_employee_for_movement') < create.index('movement_overlaps(')
    edit = _function_block(source, 'def mission_edit_save(movement_id):', "@bp.post('/reports/assignments/mission-ticket-image/")
    assert 'lock_movement_for_employee(movement_id, locked_employee.id)' in edit
    assert edit.index('lock_movement_for_employee') < edit.index('movement_overlaps(')
    close = _function_block(source, 'def mission_close(movement_id):', "@bp.post('/reports/assignments/mission-reopen/")
    assert 'lock_movement_for_employee(movement_id, locked_employee.id)' in close
    assert close.index('lock_movement_for_employee') < close.index('movement_overlaps(')


def test_manager_assistant_close_uses_overlap_guard_and_cannot_bypass_closed_request_flow():
    planning = (ROOT / 'employee_movements' / 'assistant' / 'manager_planning.py').read_text(encoding='utf-8')
    execution = (ROOT / 'employee_movements' / 'assistant' / 'manager_execution.py').read_text(encoding='utf-8')
    assert "if (a.get('intent') or a.get('kind')) == 'movement_reopen'" in planning
    assert 'إعادة الفتح المباشر غير متاحة' in planning
    close_start = execution.index("elif kind == 'movement_close':")
    close_end = execution.index("elif kind == 'movement_edit':", close_start)
    close_block = execution[close_start:close_end]
    assert 'lock_employee_for_movement' in close_block
    assert 'movement_overlaps(' in close_block


def test_closed_mission_approval_service_locks_and_refreshes_before_conflict_check():
    source = (ROOT / 'employee_movements' / 'services' / 'mission_edit_request.py').read_text(encoding='utf-8')
    start = source.index('def validate_and_execute_mission_edit_request(')
    block = source[start:]
    assert 'lock_employee_for_movement' in block
    assert 'lock_movement_for_employee' in block
    assert block.index('lock_movement_for_employee') < block.index('movement_overlaps(')



def test_closed_mission_approval_locks_request_row_and_rechecks_closed_state():
    source = (ROOT / 'employee_movements' / 'services' / 'mission_edit_request.py').read_text(encoding='utf-8')
    start = source.index('def validate_and_execute_mission_edit_request(')
    block = source[start:]
    assert "MissionEditRequest.query.filter_by(id=getattr(request_row, 'id', None))" in block
    assert '.populate_existing()' in block
    assert '.with_for_update()' in block
    assert 'locked_request.status != PENDING_STATUS' in block
    assert 'movement_is_closed(movement)' in block
    assert 'Movement.query.filter_by(id=locked_request.movement_id)' in block
    assert "getattr(movement, 'id', None) != locked_request.movement_id" in block
    assert 'lock_movement_for_employee(locked_request.movement_id, locked_employee.id)' in block
    assert block.index('locked_request.status != PENDING_STATUS') < block.index('execute_edit_request(')


def test_assistant_action_planner_checks_admin_before_rejecting_direct_reopen():
    source = (ROOT / 'employee_movements' / 'assistant' / 'manager_planning.py').read_text(encoding='utf-8')
    start = source.index('def build_plan(a):')
    end = source.index("    if intent == 'employee_create':", start)
    block = source[start:end]
    assert block.index('if not is_app_manager()') < block.index("if (a.get('intent') or a.get('kind')) == 'movement_reopen'")
    allowed_block = block[block.index('if intent not in {'):]
    assert "'movement_reopen'" not in allowed_block


def test_second_manager_review_does_not_redirect_to_a_resolved_request_page():
    source = (ROOT / 'employee_movements' / 'blueprints' / 'missions.py').read_text(encoding='utf-8')
    start = source.index('def mission_edit_request_save(request_id):')
    end = source.index("@bp.get('/reports/assignments/export.xlsx')", start)
    block = source[start:end]
    assert "if r.status != 'قيد المراجعة':" in block
    assert "return redirect(url_for('missions.mission_edit_requests'))" in block
    assert block.index("if r.status != 'قيد المراجعة':") < block.index("return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))", block.index("if error:"))
