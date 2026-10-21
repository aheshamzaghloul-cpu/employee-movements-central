#!/usr/bin/env python3
"""Smoke-check that the real local OCR engine is installed and callable.

This intentionally validates runtime wiring rather than OCR accuracy: accuracy
requires representative, approved ticket screenshots and manual review of fields.
"""
from __future__ import annotations

import subprocess

from PIL import Image

from employee_movements.services.ticket_screenshot_ocr import extract_ticket_fields


def main() -> None:
    completed = subprocess.run(
        ["tesseract", "--list-langs"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    languages = {line.strip() for line in (completed.stdout + completed.stderr).splitlines()}
    missing = {"ara", "eng"} - languages
    if missing:
        raise SystemExit(f"OCR languages are missing: {', '.join(sorted(missing))}")

    # A blank image safely checks Pillow -> stdin -> Tesseract TSV -> field parser
    # without introducing fixture text that could imply recognition accuracy.
    fields = extract_ticket_fields(Image.new("RGB", (1200, 800), "white"))
    expected = {
        "basic_branch_name",
        "destination_branch_name",
        "job_code",
        "destination_is_basic",
        "needs_mission",
        "from_date",
        "to_date",
    }
    if set(fields) != expected:
        raise SystemExit("OCR runtime returned an unexpected field schema")
    print("TICKET_OCR_RUNTIME=OK languages=ara,eng fields=7")


if __name__ == "__main__":
    main()
