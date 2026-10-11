"""Static contract: XLSX ZIP contents are bounded before openpyxl parses them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_excel_upload_validates_archive_before_workbook_parsing():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "def _validate_excel_archive(path):" in source
    assert "len(infos) > 256" in source
    assert "64 * 1024 * 1024" in source
    assert "info.file_size / info.compress_size > 1000" in source
    assert "required = {'[Content_Types].xml', 'xl/workbook.xml'}" in source
    assert "_validate_excel_archive(path)" in source
    assert source.index("_validate_excel_archive(path)") < source.index("return token, path")


def test_excel_preview_failure_cleans_pending_upload_and_session_tokens():
    from pathlib import Path

    source = Path("employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    preview = source.split("def excel_import_preview(kind):", 1)[1].split("@bp.post('/excel-import/<kind>/confirm')", 1)[0]
    assert "token = None" in preview
    failure = preview.split("except Exception:", 1)[1]
    assert "_remove_pending_excel(token)" in failure
    assert "session.pop('excel_import_token', None)" in failure
    assert "session.pop('excel_review_token', None)" in failure


def test_excel_workbook_dimensions_are_bounded_before_row_iteration():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "MAX_EXCEL_ROWS = 50001" in source
    assert "MAX_EXCEL_COLUMNS = 64" in source
    assert "def _validate_excel_dimensions(ws):" in source
    assert source.count("_validate_excel_dimensions(ws)") >= 2
    confirm = source.split("def excel_import_confirm(kind):", 1)[1].split("@bp.post('/excel-import/<kind>/apply')", 1)[0]
    assert confirm.index("_validate_excel_dimensions(ws)") < confirm.index("ws.iter_rows(min_row=2")
