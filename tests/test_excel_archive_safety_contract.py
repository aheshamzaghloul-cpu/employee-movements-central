"""Static contract: XLSX ZIP contents are bounded before openpyxl parses them."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_excel_upload_validates_archive_before_workbook_parsing():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    storage = (ROOT / "employee_movements" / "services" / "excel_import_storage.py").read_text(encoding="utf-8")
    assert "def _validate_excel_archive(path:" in storage
    assert "len(infos) > 256" in storage
    assert "64 * 1024 * 1024" in storage
    assert "info.file_size / info.compress_size > 1000" in storage
    assert 'required = {"[Content_Types].xml", "xl/workbook.xml"}' in storage
    assert "_validate_excel_archive(path)" in storage
    assert storage.index("_validate_excel_archive(path)") < storage.index("return token, path")


def test_excel_preview_failure_cleans_pending_upload_and_session_tokens():
    from pathlib import Path

    source = Path("employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    preview = source.split("def excel_import_preview(kind):", 1)[1].split("@bp.post('/excel-import/<kind>/confirm')", 1)[0]
    assert "token = None" in preview
    failure = preview.split("except Exception as exc:", 1)[1]
    assert "_remove_pending_excel(token)" in failure
    assert "session.pop('excel_import_token', None)" in failure
    assert "session.pop('excel_review_token', None)" in failure


def test_excel_workbook_dimensions_are_bounded_before_row_iteration():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    schema = (ROOT / "employee_movements" / "services" / "excel_import_schema.py").read_text(encoding="utf-8")
    assert "MAX_EXCEL_ROWS = 50001" in schema
    assert "MAX_EXCEL_COLUMNS = 64" in schema
    assert "def _validate_excel_dimensions(ws):" in schema
    assert source.count("_validate_excel_dimensions(ws)") >= 2
    confirm = source.split("def excel_import_confirm(kind):", 1)[1].split("@bp.post('/excel-import/<kind>/apply')", 1)[0]
    assert confirm.index("_validate_excel_dimensions(ws)") < confirm.index("ws.iter_rows(min_row=2")
