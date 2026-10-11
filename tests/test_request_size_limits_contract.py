"""Static contract: request and multipart parsing have explicit resource bounds."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_request_body_and_multipart_limits_are_configured():
    source = (ROOT / "employee_movements" / "config.py").read_text(encoding="utf-8")
    assert "'MAX_CONTENT_LENGTH': 2 * 1024 * 1024" in source
    assert "'MAX_FORM_MEMORY_SIZE': 512 * 1024" in source
    assert "'MAX_FORM_PARTS': 100" in source
