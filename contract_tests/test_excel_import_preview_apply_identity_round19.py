"""Round 19 source guards for stale Excel identity evidence; not run in this review."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_employee_review_actions_keep_branch_and_employee_identity_snapshots():
    source = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "'branch_identity': {" in source
    assert "'employee_identity': {" in source
    assert "'job_code': normalized_code" in source
    assert "'email_matched': bool(ek and email_employee_id == e.id)" in source
    assert "'name_matched': bool(e.id in name_match_ids)" in source
    assert "GovernorateNameAlias=GovernorateNameAlias" in source


def test_approval_revalidates_branch_code_alias_and_employee_identity_evidence():
    service = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    assert "def _validate_branch_identity_snapshot(action):" in service
    assert "branch code changed or no longer identifies the reviewed branch" in service
    assert "branch name no longer uniquely identifies the reviewed branch" in service
    assert "def _validate_employee_identity_snapshot(action, employee):" in service
    assert "personnel-code identity changed after preview" in service
    assert "Existing employee identity fields changed after Excel preview" in service
    assert "email identity changed after preview" in service
    assert "canonical name or confirmed alias changed after preview" in service
    assert "branch does not match the reviewed workbook identity" in service


def test_ambiguous_governorate_names_and_aliases_are_not_overwritten():
    source = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    matcher = (ROOT / "employee_movements/services/excel_import_matching.py").read_text(encoding="utf-8")
    assert "_append_unique_catalog_candidate(govs, _excel_key(governorate.name), governorate)" in source
    assert "len(governorate_candidates) > 1" in source
    assert "return None, 'ambiguous_governorate'" in matcher
    schema = (ROOT / "employee_movements/services/excel_import_schema.py").read_text(encoding="utf-8")
    assert "'أكثر من محافظة'" in schema


def test_current_metadata_keeps_production_gate_closed():
    manifest = (ROOT / "REVIEW_MANIFEST.json").read_text(encoding="utf-8")
    assert '"review_round": 32' in manifest
    assert 'employee-movements-v69.00.2-full-source-upload-round32.zip' in manifest
    assert "NOT CLEARED FOR PRODUCTION" in manifest
