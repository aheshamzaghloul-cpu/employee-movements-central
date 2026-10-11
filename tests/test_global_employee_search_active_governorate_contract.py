from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "employee_movements" / "blueprints" / "employees.py"

def test_global_employee_search_excludes_inactive_governorates():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def employee_search():")
    end = source.index("@bp.route('/employees'", start)
    block = source[start:end]
    assert ".join(Governorate, Governorate.id == Branch.governorate_id)" in block
    assert "Governorate.is_active == True" in block
    assert "Branch.is_active == True" in block

def test_global_employee_search_is_independent_of_work_governorate():
    source = SOURCE.read_text(encoding="utf-8")
    start = source.index("def employee_search():")
    end = source.index("@bp.route('/employees'", start)
    block = source[start:end]
    assert "bids()" not in block
    assert "gids()" not in block



def test_home_employee_search_is_global_but_movement_picker_remains_scoped():
    source = (ROOT / 'employee_movements' / 'blueprints' / 'movements.py').read_text(encoding='utf-8')
    assert 'global_home_search = bool(q) and not movement_type' in source
    assert "if not global_home_search and not global_assignment_picker and 'مسؤول التطبيق' not in rs:" in source
    assert "global_assignment_picker = movement_type == 'انتداب'" in source
