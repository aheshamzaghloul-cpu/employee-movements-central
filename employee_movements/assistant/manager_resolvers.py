"""Local record resolvers used by the assistant application manager.

These helpers only resolve records and enforce role-shape constraints. They do not
perform mutations or grant permissions; execution remains in ``manager.execute``.
"""

from ..models import Governorate, User, UserRole
from ..access import actual_roles
from ..services.entity_matching import governorate_search_filter, rank_governorate_suggestions


SUPERVISOR_ROLE = 'مشرف محافظة'


def resolve_governorate(name):
    """Resolve exact/confirmed governorate names; fuzzy results always need a choice."""
    if not name:
        return None, []
    q = str(name).strip()
    if not q or len(q) > 120:
        return None, []
    scoped = Governorate.query.filter(Governorate.is_active == True)
    # Shared matcher includes confirmed governorate aliases and Arabic normalization.
    partial = scoped.filter(governorate_search_filter(q)).order_by(Governorate.name).limit(11).all()
    if len(partial) == 1:
        return partial[0], []
    if partial:
        return None, partial[:10]
    pool = scoped.order_by(Governorate.name).limit(2500).all()
    ranked = rank_governorate_suggestions(q, pool, limit=8)
    # Approximate matches are suggestions only: never silently target a governorate.
    return None, [item['governorate'] for item in ranked]


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
