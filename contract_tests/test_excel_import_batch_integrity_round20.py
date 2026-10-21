"""Round 20 source-only guards for fail-closed, whole-batch Excel approval.

This file is intentionally not executed during the static-only review.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_selection_plan_rejects_unknown_or_stale_checkbox_tokens():
    source = (ROOT / "employee_movements/services/excel_import_workflow.py").read_text(encoding="utf-8")
    assert "allowed_selection_tokens: set[str] = set()" in source
    assert "selected - allowed_selection_tokens" in source
    assert "unknown or stale action token" in source


def test_postgres_excel_employee_and_governorate_imports_use_separate_transaction_gates():
    source = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock(:lock_key)" in source
    assert "0x454D504C" in source
    assert "0x474F5652" in source
    assert "different governorates from both passing the same global identity scan" in source


def test_governorate_additions_are_validated_as_a_batch_before_mutations():
    source = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    assert "if kind == 'governorates' and selected_adds:" in source
    assert "desired_name_keys" in source
    assert "desired_exact_keys" in source
    assert "duplicate or conflicting governorate names" in source


def test_selected_updates_fail_closed_if_a_target_disappears_during_persistence():
    source = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    assert "Selected Excel branch update target disappeared before persistence" in source
    assert "Selected Excel employee update target disappeared or was deleted before persistence" in source
    assert "never silently turn an explicitly selected addition into a skip" in source


def test_route_validates_whole_plan_before_mutations_and_commits_only_after_apply():
    source = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    validate = source.index("validate_selected_excel_import_changes(")
    apply = source.index("apply_selected_excel_import_changes(", validate)
    commit = source.index("db.session.commit()", apply)
    rollback = source.index("db.session.rollback()", commit)
    assert validate < apply < commit < rollback


def test_current_release_manifest_remains_blocked_from_production():
    manifest = (ROOT / "REVIEW_MANIFEST.json").read_text(encoding="utf-8")
    assert '"review_round": 32' in manifest
    assert "employee-movements-v69.00.2-full-source-upload-round32.zip" in manifest
    assert "NOT CLEARED FOR PRODUCTION" in manifest
