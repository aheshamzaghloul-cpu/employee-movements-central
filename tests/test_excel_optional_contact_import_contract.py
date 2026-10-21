from pathlib import Path


def test_employee_excel_contact_fields_are_optional():
    root = Path(__file__).resolve().parents[1]
    source = (root / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    workflow = (root / "employee_movements/services/excel_import_workflow.py").read_text(encoding="utf-8")
    template = (root / "employee_movements/templates/excel_import.html").read_text(encoding="utf-8")
    assert '_OPTIONAL_EMPLOYEE_FIELDS = frozenset(' in workflow
    assert "if vals['email'] and not valid_email(vals['email'])" in source
    assert "email=(v.get('email') or '').strip() or None" in source
    assert "seen_job_codes = set()" in source and "seen_emails = set()" in source
    assert "field in ['email','company_phone','personal_phone','branch_code']" in template


def test_employee_import_keeps_core_fields_required():
    root = Path(__file__).resolve().parents[1]
    source = (root / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "required = ['name', 'job_title', 'job_code', 'hire_date']" in source
    assert "missing_values = [field for field in required if not vals.get(field)]" in source
