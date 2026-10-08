"""Shared visibility predicates for assistant read paths.

These helpers deliberately delegate scope decisions to the central access layer.
They do not grant permissions; they only answer whether an active record is
visible to the current assistant user.
"""

from ..access import branch_ok, roles


def global_movement_actor() -> bool:
    """Whether the current user has the global movement-read role."""
    current_roles = roles()
    return 'مسؤول التطبيق' in current_roles or 'مشرف محافظة' in current_roles


def visible_employee(employee) -> bool:
    """Return whether an active employee is visible to assistant read paths."""
    return bool(
        employee
        and getattr(employee, 'is_active', False)
        and (global_movement_actor() or branch_ok(employee.branch_id))
    )
