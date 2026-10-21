"""Safe request-local form values for re-rendering validation errors.

Form drafts are intentionally not stored in Flask's signed client-side cookie,
which is signed but not encrypted. This helper only sanitizes values from the
current POST request for immediate template rendering. Credentials, CSRF values,
tokens, uploads, and file payloads are never returned.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from flask import request

_MAX_FIELDS = 40
_MAX_VALUES_PER_FIELD = 12
_MAX_VALUE_LENGTH = 500
_MAX_TOTAL_CHARACTERS = 3000
_SENSITIVE_TOKENS = {
    "password", "passwd", "secret", "csrf", "token", "file", "files",
    "filename", "filedata", "upload", "uploads", "screenshot", "image", "signature",
}
_SENSITIVE_COMPOUNDS = {
    "api_key", "apikey", "access_token", "accesstoken", "refresh_token",
    "refreshtoken", "image_data", "imagedata",
}


def _is_sensitive_name(name: str) -> bool:
    """Match sensitive words as field tokens, not arbitrary substrings.

    Token matching avoids suppressing a legitimate field such as ``profile``
    merely because its spelling contains the letters ``file``.
    """
    snake_name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    parts = set(re.findall(r"[a-z0-9]+", snake_name))
    compact = snake_name.replace("_", "")
    return bool(parts & _SENSITIVE_TOKENS) or any(
        compound.replace("_", "") in compact for compound in _SENSITIVE_COMPOUNDS
    )


def _safe_values(form: Any) -> dict[str, str | list[str]]:
    """Copy a bounded subset of form fields safe for immediate HTML rendering."""
    result: dict[str, str | list[str]] = {}
    total = 0
    try:
        keys = list(form.keys())[:_MAX_FIELDS]
    except (AttributeError, TypeError):
        return result

    for raw_name in keys:
        name = str(raw_name)[:100]
        if not name or name.startswith("_") or _is_sensitive_name(name):
            continue
        try:
            values = form.getlist(raw_name)[:_MAX_VALUES_PER_FIELD]
        except (AttributeError, TypeError):
            value = form.get(raw_name, "") if isinstance(form, Mapping) else ""
            values = [value]

        cleaned: list[str] = []
        for raw_value in values:
            value = str(raw_value or "")[:_MAX_VALUE_LENGTH]
            available = _MAX_TOTAL_CHARACTERS - total
            if available <= 0:
                break
            value = value[:available]
            total += len(value)
            cleaned.append(value)
        if cleaned:
            result[name] = cleaned if len(cleaned) > 1 else cleaned[0]
        if total >= _MAX_TOTAL_CHARACTERS:
            break
    return result


def form_values_from_request(form: Any | None = None) -> dict[str, str | list[str]]:
    """Return sanitized form values for immediate rendering after a POST."""
    return _safe_values(form if form is not None else request.form)
