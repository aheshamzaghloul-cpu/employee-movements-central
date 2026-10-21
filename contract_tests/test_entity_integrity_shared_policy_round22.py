"""Source-only regression guard for the round-22 shared entity identity policy.

This file is intentionally not executed during the requested static-only review.
It guards source wiring and fail-closed confirmation behavior, not runtime semantics.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_shared_entity_integrity_policy_is_present_and_scoped():
    source = _source("employee_movements/services/entity_integrity.py")
    for symbol in (
        "governorate_name_conflict",
        "branch_name_conflict",
        "branch_code_conflict",
        "normalize_branch_code_key",
        "employee_name_conflict",
        "governorate_write_snapshot",
        "branch_write_snapshot",
    ):
        assert f"def {symbol}(" in source
    assert "Branch.governorate_id == int(governorate_id)" in source
    assert "Employee.branch_id == int(branch_id)" in source
    assert "_BRANCH_CODE_DIGITS" in source


def test_manual_excel_and_assistant_paths_share_integrity_guards():
    catalog = _source("employee_movements/blueprints/catalog.py")
    employees = _source("employee_movements/blueprints/employees.py")
    users = _source("employee_movements/blueprints/users.py")
    excel = _source("employee_movements/services/excel_import_apply.py")
    assistant = _source("employee_movements/assistant/manager_execution.py")
    plans = _source("employee_movements/assistant/manager_plan_structure.py")
    for source in (catalog, excel, assistant):
        assert "lock_entity_identity_writes" in source
    for source in (employees, users, excel, assistant):
        assert "employee_name_conflict" in source
    assert "branch_code_conflict" in catalog and "branch_name_conflict" in catalog
    assert "governorate_name_conflict" in catalog and "governorate_name_conflict" in excel
    assert "identity_snapshot" in plans
    assert "governorate_write_snapshot(x)" in assistant
    assert "branch_write_snapshot(x)" in assistant
    assert "تغيّرت المحافظة منذ إعداد المعاينة" in assistant
    assert "تغيّر الفرع أو كوده أو محافظته منذ إعداد المعاينة" in assistant


def test_current_round_manifest_contract_names_full_round_32_candidate():
    source = _source("contract_tests/test_release_manifest_consistency.py")
    assert "REVIEW_MANIFEST_v69.00.2_round32.json" in source
    assert "employee-movements-v69.00.2-full-source-upload-round32.zip" in source
