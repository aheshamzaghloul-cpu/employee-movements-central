"""Local record resolvers used by the assistant application manager.

These helpers only resolve records and enforce role-shape constraints. They do not
perform mutations or grant permissions; execution remains in ``manager.execute``.
"""

from ..models import User, UserRole
from ..access import actual_roles


SUPERVISOR_ROLE = 'مشرف محافظة'


def resolve_active_supervisor_by_name(name, limit=50):
    """Return a unique active governorate supervisor matching ``name``.

    The role is checked in SQL through the user's role relationship rather than
    loading unrelated active users and filtering their roles in Python.
    """
    value = str(name or '').strip()
    if not value:
        return None
    query = (
        User.query
        .join(UserRole, UserRole.user_id == User.id)
        .filter(
            User.is_active == True,
            User.full_name.ilike(f'%{value}%'),
        )
        .filter(UserRole.role == SUPERVISOR_ROLE)
        .distinct()
        .limit(limit)
    )
    matches = query.all()
    return matches[0] if len(matches) == 1 else None


def is_active_supervisor(user):
    return bool(user and user.is_active and SUPERVISOR_ROLE in actual_roles(user))
