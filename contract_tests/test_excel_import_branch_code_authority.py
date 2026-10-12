from pathlib import Path


def test_employee_import_maps_branch_code_and_treats_it_as_optional_fallback():
    source = (Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "'branch_code': ('كود الفرع'" in source
    assert "'branch_code': 'كود الفرع'" in source
    assert "'branch_code'} if kind == 'employees'" in source


def test_unique_active_branch_code_is_authoritative_over_excel_names():
    source = (Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "branches_by_code.setdefault(code_key, []).append(b)" in source
    assert "if len(code_matches) == 1:" in source
    assert "return code_matches[0], 'code'" in source
    assert "g = b.governorate" in source


def test_duplicate_branch_codes_are_disambiguated_or_rejected_not_guessed():
    source = (Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "if len(code_matches) > 1:" in source
    assert "return None, 'ambiguous_code'" in source
    assert "كود الفرع" in source and "غير فريد" in source
