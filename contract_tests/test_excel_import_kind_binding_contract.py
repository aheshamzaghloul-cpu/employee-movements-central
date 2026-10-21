"""Static source contract: a staged Excel workbook cannot change import kind."""
from pathlib import Path


def test_excel_preview_binds_uploaded_workbook_to_selected_kind():
    source_path = Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "excel_import.py"
    source = source_path.read_text(encoding="utf-8")
    assert "session['excel_import_kind'] = kind" in source
    assert "_get_pending_excel(expected_kind=kind)" in source
    assert "session.get('excel_import_kind') != kind" in source
    assert "review.get('kind') != kind" in source
