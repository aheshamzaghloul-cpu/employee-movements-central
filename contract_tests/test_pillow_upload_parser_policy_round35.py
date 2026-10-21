"""Static security contract for the image-upload parser boundary in round 35."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_current_pillow_pin_includes_october_security_release():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert "Pillow==13.0.0" in requirements
    assert "Pillow==12.3.0" not in requirements


def test_untrusted_ticket_uploads_limit_decoder_plugins_and_dimensions():
    missions = (ROOT / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    storage = (ROOT / "employee_movements/services/ticket_image_storage.py").read_text(encoding="utf-8")
    ocr = (ROOT / "employee_movements/services/ticket_screenshot_ocr.py").read_text(encoding="utf-8")

    assert "Image.open(BytesIO(image_bytes), formats=tuple(SUPPORTED_FORMATS))" in missions
    assert "Image.DecompressionBombWarning" in missions
    assert "image_format not in SUPPORTED_FORMATS" in missions
    assert "formats=tuple(SUPPORTED_TICKET_IMAGE_FORMATS)" in storage
    assert "MAX_TICKET_IMAGE_PIXELS = 12_000_000" in storage
    assert 'SUPPORTED_TICKET_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}' in storage
    assert 'SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}' in ocr


def test_mission_pdf_only_opens_the_expected_raster_formats_for_ticket_evidence():
    source = (ROOT / "employee_movements/services/mission_documents.py").read_text(encoding="utf-8")
    assert source.count('formats=("PNG", "JPEG", "WEBP")') == 2
