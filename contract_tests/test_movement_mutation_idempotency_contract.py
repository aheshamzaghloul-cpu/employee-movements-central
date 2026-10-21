"""Source-only contracts for safe, retry-resistant movement mutations.

These checks are intended for CI. They were not executed during the current
static-review round, per the release owner's instruction.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manual_submit_serializes_on_employee_then_movement_and_is_idempotent():
    source = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    submit = source.split("def movement_submit(i):", 1)[1].split("@bp.post('/movements/<int:i>/close-assignment')", 1)[0]
    assert "lock_employee_for_movement(m.employee_id)" in submit
    assert "lock_movement_for_employee(i, employee.id)" in submit
    assert "if m.status == 'مسجلة':" in submit
    assert "لم يتم إنشاء إجراء مكرر" in submit


def test_manual_delete_serializes_and_rechecks_after_locking():
    source = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    delete = source.split("def movement_delete(i):", 1)[1].split("@bp.get('/movements/<int:i>/history')", 1)[0]
    assert "lock_employee_for_movement(m.employee_id)" in delete
    assert "lock_movement_for_employee(i, employee.id)" in delete
    assert "if not can('delete_movements') or not can_manage_movement(m):" in delete
    assert "if not m.is_active:" in delete


def test_assistant_admin_delete_uses_common_locks_and_cannot_bypass_closed_mission_workflow():
    source = (ROOT / "employee_movements" / "assistant" / "manager_execution.py").read_text(encoding="utf-8")
    delete = source.split("elif kind == 'movement_delete':", 1)[1].split("elif kind == 'movement_reopen':", 1)[0]
    assert "lock_employee_for_movement(x.employee_id)" in delete
    assert "lock_movement_for_employee(x.id, employee.id)" in delete
    assert "movement_is_closed(x)" in delete
    assert "لا يمكن حذف مأمورية مغلقة مباشرة" in delete
