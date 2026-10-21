"""Defensive parsing for user-controlled page-number query parameters."""
from __future__ import annotations


MAX_PAGE_NUMBER = 1_000_000_000
MAX_PAGE_DIGITS = 10


def safe_page_number(value: object, page_count: int | None = None, *, default: int = 1) -> int:
    """Parse and clamp a page number without allowing hostile huge integers.

    Accepts decimal Unicode digits (including Arabic-Indic digits), rejects
    signs/fractions/other input, limits conversion work, and optionally clamps
    the value to an already-computed page count.
    """
    try:
        fallback = max(1, min(int(default), MAX_PAGE_NUMBER))
    except (TypeError, ValueError, OverflowError):
        fallback = 1

    raw = str(value if value is not None else "").strip()
    if not raw or len(raw) > MAX_PAGE_DIGITS or not raw.isdecimal():
        number = fallback
    else:
        try:
            number = int(raw)
        except (TypeError, ValueError, OverflowError):
            number = fallback

    number = max(1, min(number, MAX_PAGE_NUMBER))
    if page_count is not None:
        try:
            upper = max(1, int(page_count))
        except (TypeError, ValueError, OverflowError):
            upper = 1
        number = min(number, upper)
    return number
