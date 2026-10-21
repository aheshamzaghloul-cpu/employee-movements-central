"""Executable tests for bounded and metadata-stripped ticket image normalization."""
from importlib.util import module_from_spec, spec_from_file_location
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / 'employee_movements' / 'services' / 'ticket_image_storage.py'
_spec = spec_from_file_location('ticket_image_storage_contract_module', SERVICE_PATH)
assert _spec and _spec.loader
_service = module_from_spec(_spec)
_spec.loader.exec_module(_service)


def _image_bytes(fmt='PNG', size=(900, 1200)):
    image = Image.new('RGB', size, 'white')
    output = BytesIO()
    image.save(output, format=fmt)
    return output.getvalue()


def test_png_jpeg_and_webp_are_sanitized_into_supported_storage_formats():
    for fmt in ('PNG', 'JPEG', 'WEBP'):
        raw = _image_bytes(fmt)
        normalized, mime_type, sha = _service.normalize_ticket_image(raw)
        assert normalized
        assert len(normalized) <= _service.MAX_TICKET_IMAGE_BYTES
        assert mime_type in {'image/png', 'image/jpeg'}
        assert len(sha) == 64
        assert sha == __import__('hashlib').sha256(normalized).hexdigest()
        with Image.open(BytesIO(normalized)) as reopened:
            reopened.verify()


def test_corrupt_oversized_and_unsupported_images_are_rejected():
    with pytest.raises(ValueError):
        _service.normalize_ticket_image(b'not-an-image')
    with pytest.raises(ValueError, match='2 ميجابايت'):
        _service.normalize_ticket_image(b'x' * (_service.MAX_TICKET_IMAGE_BYTES + 1))

    bmp = _image_bytes('BMP', (16, 16))
    with pytest.raises(ValueError, match='PNG وJPG وWEBP'):
        _service.normalize_ticket_image(bmp)


def test_large_screenshot_is_downscaled_and_remains_within_safe_storage_bound():
    raw = _image_bytes('PNG', (4000, 3000))
    normalized, mime_type, _ = _service.normalize_ticket_image(raw)
    with Image.open(BytesIO(normalized)) as reopened:
        assert max(reopened.size) <= _service.MAX_TICKET_IMAGE_DIMENSION
        assert reopened.width * reopened.height <= _service.MAX_TICKET_IMAGE_PIXELS
    assert len(normalized) <= _service.MAX_TICKET_IMAGE_BYTES
    assert mime_type in {'image/png', 'image/jpeg'}
