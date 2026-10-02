"""Compatibility WSGI entry point for hosts that start Gunicorn with ``app:app``.

The canonical application factory lives in ``employee_movements`` and the
canonical WSGI entry point is ``wsgi.py``. This wrapper keeps compatibility
with hosting platforms configured for ``app:app``.
"""
from wsgi import app

__all__ = ["app"]
