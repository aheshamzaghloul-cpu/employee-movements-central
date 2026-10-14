from pathlib import Path


def test_employee_import_prefers_branch_code_and_keeps_name_fallback():
    source = Path("employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "branches_by_code.setdefault(code_key, []).append(b)" in source
    assert "return code_matches[0], 'code'" in source
    assert "branch_cache[(governorate_key, canonical_key)] = b" in source
    assert "for alias_key in branch_alias_keys_by_id.get(b.id, set())" in source
    assert "branches_by_name.setdefault(alias_key, []).append(b)" in source
    assert "return named, 'name'" in source
    assert "Branch.is_active == True" in source
    assert "Branch.governorate_id.in_(allowed_gids)" in source
