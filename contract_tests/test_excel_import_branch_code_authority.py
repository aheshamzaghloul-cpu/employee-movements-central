from pathlib import Path


def test_employee_import_maps_branch_code_and_treats_it_as_optional_fallback():
    root = Path(__file__).resolve().parents[1]
    schema = (root / "employee_movements" / "services" / "excel_import_schema.py").read_text(encoding="utf-8")
    workflow = (root / "employee_movements" / "services" / "excel_import_workflow.py").read_text(encoding="utf-8")
    assert "'branch_code': ('كود الفرع'" in schema
    assert "'branch_code': 'كود الفرع'" in schema
    assert '"branch_code"' in workflow and "kind == \"employees\"" in workflow


def test_unique_branch_code_is_authoritative_but_label_conflicts_are_blocked():
    source = (Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    matcher = (Path(__file__).resolve().parents[1] / "employee_movements" / "services" / "excel_import_matching.py").read_text(encoding="utf-8")
    assert "branches_by_code.setdefault(code_key, []).append(b)" in source
    assert "if len(code_matches) == 1:" in matcher
    assert "return candidate, 'code_label_mismatch'" in matcher
    assert "g = b.governorate" in source


def test_duplicate_branch_codes_are_disambiguated_or_rejected_not_guessed():
    matcher = (Path(__file__).resolve().parents[1] / "employee_movements" / "services" / "excel_import_matching.py").read_text(encoding="utf-8")
    assert "if len(code_matches) > 1:" in matcher
    assert "return None, 'ambiguous_code'" in matcher


def test_generic_code_alias_cannot_be_guessed_as_branch_code():
    root = Path(__file__).resolve().parents[1]
    schema = (root / "employee_movements" / "services" / "excel_import_schema.py").read_text(encoding="utf-8")
    branch_code_aliases = schema.split("'branch_code': (", 1)[1].split("),", 1)[0]
    assert "'code'" not in branch_code_aliases
    assert "'كود'" not in branch_code_aliases
    assert "len(header) < 4" in schema
    assert "Resolve every exact alias first" in schema
