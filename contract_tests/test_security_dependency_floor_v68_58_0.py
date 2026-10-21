"""Prevent regression to dependency versions below the reviewed security baseline."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _pinned_version(package_name: str) -> tuple[int, ...]:
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    match = re.search(rf"(?m)^{re.escape(package_name)}==([0-9]+(?:\.[0-9]+)+)\s*$", requirements)
    assert match, f"Expected an exact version pin for {package_name} in requirements.txt"
    return tuple(int(part) for part in match.group(1).split("."))


def test_flask_has_session_vary_security_fix():
    assert _pinned_version("Flask") >= (3, 1, 3)


def test_werkzeug_meets_reviewed_security_maintenance_floor():
    assert _pinned_version("Werkzeug") >= (3, 1, 9)


def test_psycopg2_binary_includes_latest_2_9_malformed_input_fixes():
    assert _pinned_version("psycopg2-binary") >= (2, 9, 13)


def test_pymupdf_includes_current_reviewed_pdf_security_fixes():
    assert _pinned_version("PyMuPDF") >= (2, 0, 0)


def test_gunicorn_pin_is_available_in_the_deployment_package_index():
    # The deployment resolver reported the package index only through 26.2.0.
    # Upstream changelog/tag references to 26.2.2 do not make that version
    # installable from this index. Raise this floor only after the index exposes it.
    assert _pinned_version("gunicorn") >= (26, 2, 0)


def test_pdf_service_uses_the_current_pymupdf_package_name():
    source = (ROOT / "employee_movements" / "services" / "mission_documents.py").read_text(encoding="utf-8")
    assert "import pymupdf as fitz" in source
    assert "\nimport fitz\n" not in source
