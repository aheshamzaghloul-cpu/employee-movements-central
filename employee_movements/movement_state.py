"""Canonical assignment-state rules shared by queries and business services.

Historical rows may encode closure in either ``assignment_state`` or
``mission_state``. All read and validation paths must interpret both fields the
same way; otherwise a closed mission can appear current or block a new movement.
"""
from __future__ import annotations


def assignment_is_closed(movement: object | None) -> bool:
    """Return whether a movement is closed, including legacy closure records."""
    return bool(
        movement is not None
        and (
            getattr(movement, "assignment_state", None) == "مغلق"
            or getattr(movement, "mission_state", None) == "مغلقة"
        )
    )


def assignment_closed_filter(model):
    """Build a SQLAlchemy predicate matching the canonical closed-state rule."""
    from sqlalchemy import or_

    return or_(model.assignment_state == "مغلق", model.mission_state == "مغلقة")


def assignment_open_filter(model):
    """Build a SQLAlchemy predicate for rows not closed in either state column.

    Explicit NULL handling is important: a missing legacy state means "not
    explicitly closed", not SQL UNKNOWN/false.
    """
    from sqlalchemy import and_, or_

    return and_(
        or_(model.assignment_state.is_(None), model.assignment_state != "مغلق"),
        or_(model.mission_state.is_(None), model.mission_state != "مغلقة"),
    )
