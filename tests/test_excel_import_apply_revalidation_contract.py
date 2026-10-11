from pathlib import Path


def test_excel_apply_revalidates_references_before_any_import_mutation():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    start = source.index("def excel_import_apply(kind):")
    body = source[start:]
    checks = [
        "Revalidate every database reference at apply time",
        "not governorate.is_active",
        "not branch.is_active",
        "not employee or employee.deleted_at is not None",
        "func.lower(func.trim(Employee.job_code))",
        "func.lower(Employee.email)",
    ]
    for check in checks:
        assert check in body
    first_mutation = min(position for position in (body.find("db.session.add(Governorate("), body.find("b = Branch("), body.find("e = Employee(")) if position >= 0)
    assert body.index("Revalidate every database reference at apply time") < first_mutation
