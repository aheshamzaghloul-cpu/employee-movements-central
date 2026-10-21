"""Source-only guard for one-time Excel import apply claims; intentionally not run in static rounds."""
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_excel_apply_claim_uses_exclusive_creation_and_stale_claim_recovery():
    source = (ROOT / "employee_movements" / "services" / "excel_import_storage.py").read_text(encoding="utf-8")
    claim = source.split("def _claim_pending_excel_apply", 1)[1].split("def _release_pending_excel_apply", 1)[0]
    assert "os.O_EXCL" in claim
    assert "_EXCEL_PENDING_TTL_SECONDS" in claim
    assert "os.unlink(path)" in claim


def test_excel_apply_route_claims_before_mutations_and_releases_in_finally():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    body = source.split("def excel_import_apply(kind):", 1)[1]
    assert body.index("_claim_pending_excel_apply(token)") < body.index("validate_selected_excel_import_changes(")
    assert "finally:" in body
    assert "_release_pending_excel_apply(token)" in body
