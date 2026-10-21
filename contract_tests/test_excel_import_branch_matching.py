from pathlib import Path


def test_employee_import_uses_code_first_pure_branch_resolver_and_keeps_name_fallback():
    source = Path("employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    matcher = Path("employee_movements/services/excel_import_matching.py").read_text(encoding="utf-8")
    assert "branches_by_code.setdefault(code_key, []).append(b)" in source
    assert "resolve_employee_import_branch(" in source
    assert "_append_unique_catalog_candidate(branch_cache, (governorate_key, canonical_key), b)" in source
    assert "for alias_key in branch_alias_keys_by_id.get(b.id, set())" in source
    assert "_append_unique_catalog_candidate(branches_by_name, alias_key, b)" in source
    assert "return None, 'ambiguous_name'" in matcher
    assert "unique_candidates = {getattr(candidate, 'id', id(candidate)): candidate for candidate in candidates}" in matcher
    assert "scoped_import_branches = (" in source
    assert "branch.is_active and branch.governorate and branch.governorate.is_active" in source
    assert "Branch.governorate_id.in_(allowed_gids)" in source
    assert "for b in scoped_import_branches:" in source
