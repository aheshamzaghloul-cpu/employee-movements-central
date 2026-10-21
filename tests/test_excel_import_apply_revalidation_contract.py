from pathlib import Path


def test_excel_apply_revalidates_references_before_any_import_mutation():
    root = Path(__file__).parents[1]
    source = (root / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    service = (root / "employee_movements" / "services" / "excel_import_apply.py").read_text(encoding="utf-8")
    start = source.index("def excel_import_apply(kind):")
    body = source[start:]
    assert body.index("validate_selected_excel_import_changes(") < body.index("apply_selected_excel_import_changes(")
    checks = [
        "Lock all existing targets and referenced branch/governorate rows",
        "_assert_reviewed_old_value",
        "populate_existing().with_for_update()",
        "An existing record changed after Excel preview",
        "not governorate.is_active",
        "not branch.is_active",
        "not employee or employee.deleted_at is not None",
        "job_code_lookup_variants",
        "target_variants",
        "func.lower(func.trim(Employee.email))",
    ]
    for check in checks:
        assert check in service
    validator = service[service.index("def validate_selected_excel_import_changes("):service.index("@dataclass(frozen=True)")]
    assert "session.add(" not in validator and "session.commit(" not in validator
