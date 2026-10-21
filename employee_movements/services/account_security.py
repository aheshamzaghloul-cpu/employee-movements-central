"""Shared safeguards for administrator continuity and per-user pending work."""
from __future__ import annotations

from flask import has_request_context, session

from ..extensions import db
from ..models import AssistantSessionState, MissionTicketImageDraft, User, UserRole

ADMIN_ROLE = 'مسؤول التطبيق'


def administrator_statuses_for_update() -> dict[int, bool]:
    """Lock administrator role/account rows in stable order and return active state.

    The rows are intentionally locked before a role is revoked, an administrator
    account is disabled, or an account is deleted. This narrows the race where two
    concurrent administrator changes could each see the other admin and remove the
    last active route back into application administration.
    """
    rows = (
        db.session.query(User.id, User.is_active)
        .join(UserRole, UserRole.user_id == User.id)
        .filter(UserRole.role == ADMIN_ROLE)
        .order_by(User.id.asc())
        .with_for_update()
        .all()
    )
    return {int(user_id): bool(is_active) for user_id, is_active in rows}


def can_remove_admin_role(user_id: int) -> bool:
    """Whether removing this user's administrator role preserves recovery access."""
    statuses = administrator_statuses_for_update()
    if user_id not in statuses:
        return True
    remaining = {key: active for key, active in statuses.items() if key != user_id}
    if statuses[user_id]:
        # Removing/deactivating an active administrator must leave another active one.
        return any(remaining.values())
    # If the target is already inactive, preserve at least one administrator account
    # so an operator can reactivate it and recover the application.
    return bool(remaining)


def invalidate_user_workflows(user_id: int) -> int | None:
    """Revoke pending work and older login sessions after sensitive account changes.

    Chat history is retained; executable assistant state and ticket drafts are dropped.
    The session-version increment revokes other browsers. If the current browser is
    changing its own password/profile, update only that browser to the new version.
    """
    AssistantSessionState.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    MissionTicketImageDraft.query.filter_by(uploaded_by=user_id).delete(synchronize_session=False)
    target = db.session.get(User, int(user_id))
    if not target:
        return None
    target.auth_version = int(target.auth_version or 0) + 1
    if has_request_context() and session.get('uid') == target.id:
        session['auth_version'] = target.auth_version
    return target.auth_version
