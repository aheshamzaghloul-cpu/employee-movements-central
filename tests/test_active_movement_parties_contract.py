from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / "employee_movements" / "access.py"

def test_global_assignment_scope_does_not_allow_inactive_employee_branch_or_governorate():
    text = ACCESS.read_text(encoding="utf-8")
    start = text.index("def can_manage_movement_employee(")
    end = text.index("def can_manage_movement_destination(", start)
    block = text[start:end]
    assert "employee_branch" in block
    assert "employee_governorate" in block
    assert "not getattr(employee_branch, 'is_active', False)" in block
    assert "not getattr(employee_governorate, 'is_active', False)" in block

def test_global_assignment_scope_does_not_allow_inactive_destination_governorate():
    text = ACCESS.read_text(encoding="utf-8")
    start = text.index("def can_manage_movement_destination(")
    end = text.index("def movement_is_closed(", start)
    block = text[start:end]
    assert "destination_governorate" in block
    assert "not getattr(destination_governorate, 'is_active', False)" in block
    assert "movement_type == 'انتداب'" in block
