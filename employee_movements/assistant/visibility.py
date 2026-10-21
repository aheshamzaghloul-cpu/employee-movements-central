"""Shared visibility predicates for assistant read paths.

These helpers deliberately delegate scope decisions to the central access layer.
They do not grant permissions; they only answer whether an active record is
visible to the current assistant user.
"""

from ..access import can, can_view_movement


def global_movement_actor() -> bool:
    """All official login roles can read employee and movement data globally."""
    return can('view_reports')


def visible_movement(movement) -> bool:
    """Return whether a movement is readable under the central access rules."""
    return bool(movement and can_view_movement(movement))


def visible_employee(employee) -> bool:
    """Read employee records across active governorates before work-scope selection.

    The work governorate limits mutations, not directory/profile/report reads.
    """
    if not employee or not getattr(employee, 'is_active', False) or not can('view_reports'):
        return False
    branch = getattr(employee, 'branch', None)
    governorate = getattr(branch, 'governorate', None) if branch else None
    return bool(branch and branch.is_active and governorate and governorate.is_active)
