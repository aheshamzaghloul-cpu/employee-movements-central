"""Shared Arabic-aware search normalization for UI and database queries.

The SQL helper deliberately uses REPLACE/LOWER operations supported by both
PostgreSQL and SQLite, and escapes SQL LIKE wildcards so user input is treated
as text rather than as a pattern.
"""
from __future__ import annotations

import re
import unicodedata

_DIGITS_FROM = "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹"
_DIGITS_TO = "01234567890123456789"
_CHAR_MAP = str.maketrans({
    **dict(zip(_DIGITS_FROM, _DIGITS_TO)),
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ئ": "ي", "ؤ": "و",
    "ـ": None,
})
_DIACRITICS = tuple(chr(codepoint) for codepoint in (
    *range(0x064B, 0x0660), 0x0670, *range(0x06D6, 0x06EE)
))
_FORMAT_CONTROLS = tuple(chr(codepoint) for codepoint in (0x200E, 0x200F, *range(0x202A, 0x202F)))
_CHAR_MAP.update({ord(char): None for char in _FORMAT_CONTROLS})
_SQL_REPLACEMENTS = (
    *((char, "") for char in _FORMAT_CONTROLS),
    *((char, "") for char in _DIACRITICS),
    ("ـ", ""),
    ("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
    ("ى", "ي"), ("ة", "ه"), ("ئ", "ي"), ("ؤ", "و"),
    *((char, digit) for char, digit in zip(_DIGITS_FROM, _DIGITS_TO)),
)


def normalize_search_text(value: object) -> str:
    """Normalize common Arabic spelling variants and Arabic/Persian digits."""
    # Bound CPU and SQL parameter size for user-controlled search strings while
    # leaving ample room for long names and aliases. Truncate before Unicode
    # normalization so a very long query cannot trigger unbounded normalization.
    raw = str(value or "")[:1024]
    text = unicodedata.normalize("NFKC", raw).translate(_CHAR_MAP)
    text = "".join(char for char in text if char not in _DIACRITICS)
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()[:256]


def normalized_sql_text(column):
    """Return a SQL expression with the same core normalization as the UI."""
    from sqlalchemy import func

    expression = func.lower(func.coalesce(column, ""))
    for source, target in _SQL_REPLACEMENTS:
        expression = func.replace(expression, source, target)
    return expression


def search_contains(column, value: object):
    """Case-insensitive contains predicate with Arabic normalization and LIKE escaping."""
    from sqlalchemy import false

    needle = normalize_search_text(value)
    if not needle:
        return false()
    escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return normalized_sql_text(column).like(f"%{escaped}%", escape="\\")
