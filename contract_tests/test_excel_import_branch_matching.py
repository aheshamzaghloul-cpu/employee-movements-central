from pathlib import Path


def test_employee_import_accepts_branch_name_or_code_within_governorate():
    source = Path("employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "branch_cache[(governorate_key, _excel_key(b.name))] = b" in source
    assert "branch_cache[(governorate_key, _excel_key(b.code))] = b" in source
    assert "b = branch_cache.get((governorate_key, branch_key))" in source
    assert "Branch.is_active == True" in source
    assert "Branch.governorate_id.in_(allowed_gids)" in source
