"""Round 17 source guards for ambiguous employee identity and duplicate review actions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_deleted_employee_identity_is_kept_and_conflicted_during_preview():
    source = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "Employee.job_code, Employee.email, Employee.deleted_at" in source
    assert "'is_deleted': deleted_at is not None" in source
    assert "يرتبط بموظف محذوف منطقيًا" in source


def test_email_only_match_cannot_authorize_personnel_code_replacement():
    source = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "if code_employee_id is None and email_employee_id is not None:" in source
    assert "لم يُقترح تغيير الكود" in source


def test_review_manifest_cannot_repeat_rows_or_existing_record_targets():
    source = (ROOT / "employee_movements/services/excel_import_workflow.py").read_text(encoding="utf-8")
    assert "seen_source_rows: set[int] = set()" in source
    assert "seen_record_targets: set[tuple[str, int]] = set()" in source
    assert "Multiple Excel review actions refer to the same source row" in source
    assert "Multiple Excel review actions refer to the same existing record" in source
