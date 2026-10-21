"""Shared role gate for the application-manager assistant."""

from ..access import roles

ADMIN_ROLE = 'مسؤول التطبيق'


def is_app_manager():
    """Return whether the current session has the application-admin role."""
    return ADMIN_ROLE in roles()
