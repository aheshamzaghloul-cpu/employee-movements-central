"""Minimal shared HTTP transport for Gemini generateContent requests.

This module handles only request construction and response decoding. Callers retain
control over timeout configuration, safe diagnostic logging, prompt policy, schemas,
and local restoration of private tokens.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def generate_content(*, model: str, payload: dict, api_key: str, timeout: int, ensure_ascii: bool = False):
    """POST a prepared payload to Gemini and decode its JSON response.

    The caller must sanitize content before invoking this function. No request or
    response body is logged or persisted here.
    """
    if not api_key:
        return None
    normalized_model = str(model or "").removeprefix("models/")
    endpoint = GEMINI_URL.format(model=urllib.parse.quote(normalized_model, safe=""))
    request_obj = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=ensure_ascii).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(request_obj, timeout=int(timeout)) as response:
        return json.loads(response.read().decode("utf-8"))
