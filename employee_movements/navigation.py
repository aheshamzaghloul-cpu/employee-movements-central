"""Safe internal navigation helpers shared by form workflows."""

from urllib.parse import unquote, urlsplit


def safe_local_return_to(value, fallback="/"):
    """Return a safe same-origin path, or ``fallback`` for untrusted values.

    Return targets are user-controlled query/form values. Restrict them to
    absolute-path references on this application origin and reject control
    characters, backslashes, scheme/netloc values and encoded protocol-relative
    paths before using them in redirects.
    """
    candidate = str(value or "").strip()
    if not candidate or any(ord(char) < 32 or ord(char) == 127 for char in candidate):
        return fallback
    if "\\" in candidate or not candidate.startswith("/") or candidate.startswith("//"):
        return fallback
    try:
        parsed = urlsplit(candidate)
        decoded_path = unquote(parsed.path or "")
    except (TypeError, ValueError):
        return fallback
    if parsed.scheme or parsed.netloc or decoded_path.startswith("//") or decoded_path.startswith("/\\"):
        return fallback
    return candidate
