from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")

def test_movement_filters_validate_active_parent_child_relationships():
    source = _read("employee_movements/blueprints/movements.py")
    block = source[source.index("def movements():"):source.index("def _render_movement_edit_form(")]
    assert "filter_conflict = False" in block
    assert "selected_filter_branch.governorate_id != selected_gov_id" in block
    assert "employee_branch_id != selected_branch_id" in block
    assert "employee_governorate_id != selected_gov_id" in block
    assert "Branch.is_active == True" in block and "Governorate.is_active == True" in block
    assert "return query.filter(Movement.id == -1)" in block

def test_movement_filter_conflicts_have_specific_feedback_in_the_page():
    source = _read("employee_movements/blueprints/movements.py")
    template = _read("employee_movements/templates/movements.html")
    assert "movement_filter_conflict=filter_conflict" in source
    assert "لا يتوافق مع الاختيار السابق" in template
    assert "لا يتبع للاختيار السابق" in template
