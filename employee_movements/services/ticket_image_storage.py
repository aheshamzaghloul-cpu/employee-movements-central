"""Safe, bounded normalization for locally uploaded ServiceDesk ticket images."""
from __future__ import annotations

import hashlib
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_TICKET_IMAGE_BYTES = 2 * 1024 * 1024
MAX_TICKET_IMAGE_PIXELS = 12_000_000
MAX_TICKET_IMAGE_DIMENSION = 2400
SUPPORTED_TICKET_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP"}


def normalize_ticket_image(data: bytes) -> tuple[bytes, str, str]:
    """Validate an image, remove embedded metadata, and return (bytes, MIME, SHA-256).

    Lossless optimized PNG is preferred for screenshots and text. If it exceeds the
    storage bound, the image is encoded as a high-quality JPEG. No uploaded filename
    or EXIF metadata is retained.
    """
    if not isinstance(data, (bytes, bytearray)) or not data:
        raise ValueError("ملف الصورة فارغ أو غير صالح.")
    if len(data) > MAX_TICKET_IMAGE_BYTES:
        raise ValueError("حجم الصورة أكبر من 2 ميجابايت.")

    try:
        with Image.open(BytesIO(data)) as probe:
            image_format = (probe.format or "").upper()
            if image_format not in SUPPORTED_TICKET_IMAGE_FORMATS:
                raise ValueError("الصيغ المدعومة هي PNG وJPG وWEBP فقط.")
            if probe.width * probe.height > MAX_TICKET_IMAGE_PIXELS:
                raise ValueError("أبعاد الصورة أكبر من الحد المسموح.")
            probe.verify()
        with Image.open(BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("تعذر فتح الصورة. تأكد أنها لقطة شاشة سليمة بصيغة PNG أو JPG أو WEBP.") from exc

    if max(image.size) > MAX_TICKET_IMAGE_DIMENSION:
        ratio = MAX_TICKET_IMAGE_DIMENSION / float(max(image.size))
        image = image.resize(
            (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )

    encoded = BytesIO()
    image.save(encoded, format="PNG", optimize=True)
    image_bytes = encoded.getvalue()
    mime_type = "image/png"

    if len(image_bytes) > MAX_TICKET_IMAGE_BYTES:
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=92, optimize=True, progressive=True, subsampling=0)
        image_bytes = encoded.getvalue()
        mime_type = "image/jpeg"

    if len(image_bytes) > MAX_TICKET_IMAGE_BYTES:
        # A further gentle downscale preserves readability but guarantees that a
        # noisy photograph cannot turn each mission into an oversized database row.
        ratio = min(0.85, 1800 / float(max(image.size)))
        image = image.resize(
            (max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
            Image.Resampling.LANCZOS,
        )
        encoded = BytesIO()
        image.save(encoded, format="JPEG", quality=86, optimize=True, progressive=True, subsampling=0)
        image_bytes = encoded.getvalue()
        mime_type = "image/jpeg"

    if not image_bytes or len(image_bytes) > MAX_TICKET_IMAGE_BYTES:
        raise ValueError("تعذر تجهيز الصورة بحجم آمن. قصّ الصورة حول بيانات التيكيت ثم أعد رفعها.")

    return image_bytes, mime_type, hashlib.sha256(image_bytes).hexdigest()
