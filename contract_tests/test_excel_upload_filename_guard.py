"""Source contract for multipart uploads with missing or malformed filenames.

Added for CI regression protection; not executed during the static-only review.
"""
from pathlib import Path


def test_excel_import_preview_checks_filename_before_suffix():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "employee_movements"
        / "blueprints"
        / "excel_import.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert "raw_filename = getattr(f, 'filename', '') if f else ''" in source
    assert "filename = raw_filename.strip() if isinstance(raw_filename, str) else ''" in source
    assert "if not filename or not filename.lower().endswith" in source
