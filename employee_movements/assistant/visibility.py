"""Shared visibility predicates for assistant read paths.

These helpers deliberately delegate scope decisions to the central access layer.
They do not grant permissions; they only answer whether an active record is
visible to the current assistant user.
"""

from ..access import branch_ok, can, can_view_movement, roles


def global_movement_actor() -> bool:
    """Whether the current user has global employee-read visibility.

    This remains intentionally broad for the Home employee search. Operational
    movement/branch reads use their dedicated central scope checks instead.
    """
    current_roles = roles()
    return 'مسؤول التطبيق' in current_roles or 'مشرف محافظة' in current_roles


def visible_movement(movement) -> bool:
    """Return whether a movement is readable under the central access rules."""
    return bool(movement and can_view_movement(movement))


def visible_employee(employee) -> bool:
    """Return whether the active employee is readable in the current work scope.

    The homepage has its own intentionally global identity search. Assistant read
    tools must not inherit that global shortcut: they need a directory/report
    capability and must stay within the actor's active operational scope. Admin
    remains globally scoped when Admin is the active role.
    """
    if not employee or not getattr(employee, 'is_active', False):
        return False
    if not (can('manage_employees') or can('view_reports')):
        return False
    if 'مسؤول التطبيق' in roles():
        return True
    return bool(branch_ok(employee.branch_id))
