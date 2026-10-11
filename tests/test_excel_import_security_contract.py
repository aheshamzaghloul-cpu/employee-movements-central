"""Source-contract checks for Excel import authorization and apply-time validation."""
from pathlib import Path


SOURCE = Path('employee_movements/blueprints/excel_import.py').read_text(encoding='utf-8')


def test_excel_import_rejects_unknown_kinds_and_keeps_admin_only_data_imports():
    start = SOURCE.index('def _excel_import_permissions(kind):')
    end = SOURCE.index('\ndef _excel_scope_governorates', start)
    permissions = SOURCE[start:end]
    assert "kind not in ('governorates', 'branches', 'employees')" in permissions
    assert "kind == 'governorates' and not has_role('مسؤول التطبيق')" in permissions
    assert "kind == 'branches' and 'مسؤول التطبيق' not in roles()" in permissions
    assert "kind == 'employees' and not has_role('مسؤول التطبيق')" in permissions


def test_all_excel_mutation_endpoints_recheck_permissions():
    for endpoint in (
        "def excel_import_preview(kind):",
        "def excel_import_confirm(kind):",
        "def excel_import_apply(kind):",
    ):
        start = SOURCE.index(endpoint)
        body = SOURCE[start:]
        first_return = body.find('\n@bp.', 1)
        if first_return != -1:
            body = body[:first_return]
        assert '_excel_import_permissions(kind)' in body


def test_excel_apply_revalidates_references_and_rolls_back_failures():
    start = SOURCE.index("@bp.post('/excel-import/<kind>/apply')")
    route = SOURCE[start:]
    assert 'Revalidate every database reference at apply time' in route
    assert 'not branch.is_active' in route
    assert 'not governorate.is_active' in route
    assert 'Employee.query.filter(func.lower(func.trim(Employee.job_code)) == job_code).first()' in route
    assert 'db.session.commit()' in route
    assert 'db.session.rollback()' in route
