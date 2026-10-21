"""Round 18 source guards for ambiguous branch names and approval-time collisions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_branch_name_catalogs_preserve_ambiguous_candidates_instead_of_overwriting():
    source = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    matcher = (ROOT / "employee_movements/services/excel_import_matching.py").read_text(encoding="utf-8")
    assert "def _append_unique_catalog_candidate(catalog, key, record):" in source
    assert "branches_by_gov.setdefault(branch.governorate_id, {})" in source
    assert "_append_unique_catalog_candidate(branch_cache, (governorate_key, canonical_key), b)" in source
    assert "return None, 'ambiguous_name'" in matcher
    assert "اسم الفرع أو اسمه البديل يطابق سجلًا آخر" in source


def test_selected_branch_names_are_revalidated_against_the_batch_final_state():
    source = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    blueprint = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "branch_name_updates = {}" in source
    assert "scope_governorate_id = getattr(scope_branch, 'governorate_id', None)" in source
    assert "final_name_owners = {}" in source
    assert "selected_new_branch_name_keys = []" in source
    assert "existing_count + selected_add_count > 1" in source
    assert "Excel branch import conflicts with an existing branch name in the same governorate" in source
    assert "BranchNameAlias.query.with_entities(" in source
    assert "BranchNameAlias=BranchNameAlias" in blueprint
    assert "Excel branch import conflicts with a confirmed branch-name alias" in source


def test_round18_release_metadata_names_current_archive_and_remains_blocked():
    manifest = (ROOT / "REVIEW_MANIFEST_v69.00.0_round18.json").read_text(encoding="utf-8")
    assert '"review_round": 18' in manifest
    assert 'employee-movements-v69.00.0-pre-release-static-round18.zip' in manifest
    assert "NOT CLEARED FOR PRODUCTION" in manifest
