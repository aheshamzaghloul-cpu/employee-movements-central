"""Source contracts for the route-specific upload limit and helpful 413 message."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_excel_upload_limit_is_larger_than_general_request_limit():
    source = (ROOT / "employee_movements" / "config.py").read_text(encoding="utf-8")
    assert "'MAX_CONTENT_LENGTH': 2 * 1024 * 1024" in source
    assert "'EXCEL_UPLOAD_MAX_CONTENT_LENGTH': 16 * 1024 * 1024" in source

def test_upload_limit_is_applied_before_csrf_can_parse_the_multipart_body():
    hooks = (ROOT / "employee_movements" / "hooks.py").read_text(encoding="utf-8")
    assert "request.max_content_length = limit" in hooks
    assert hooks.index("app.before_request(apply_request_size_limit)") < hooks.index("app.before_request(csrf_check)")
    assert "excel_import.excel_import_preview" in hooks

def test_413_message_reports_the_correct_limit_for_excel_uploads():
    errors = (ROOT / "employee_movements" / "errors.py").read_text(encoding="utf-8")
    assert "حجم ملف Excel يتجاوز الحد المسموح" in errors
