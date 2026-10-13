"""Static contract: request and multipart parsing have explicit resource bounds."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_request_body_and_multipart_limits_are_configured():
    source = (ROOT / "employee_movements" / "config.py").read_text(encoding="utf-8")
    assert "'MAX_CONTENT_LENGTH': 2 * 1024 * 1024" in source
    assert "'EXCEL_UPLOAD_MAX_CONTENT_LENGTH': 16 * 1024 * 1024" in source
    assert "'MAX_FORM_MEMORY_SIZE': 512 * 1024" in source
    assert "'MAX_FORM_PARTS': 100" in source


def test_excel_upload_has_a_route_specific_limit_before_csrf_form_parsing():
    hooks = (ROOT / "employee_movements" / "hooks.py").read_text(encoding="utf-8")
    assert "def apply_request_size_limit()" in hooks
    assert "request.max_content_length = limit" in hooks
    assert hooks.index("app.before_request(apply_request_size_limit)") < hooks.index("app.before_request(csrf_check)")
    assert "excel_import.excel_import_preview" in hooks


def test_oversize_error_message_matches_route_limit():
    errors = (ROOT / "employee_movements" / "errors.py").read_text(encoding="utf-8")
    assert "if request.endpoint == 'excel_import.excel_import_preview':" in errors
    assert "حجم ملف Excel يتجاوز الحد المسموح" in errors
