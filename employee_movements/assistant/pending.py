"""Short-lived confirmation plans for the in-app assistant."""
from __future__ import annotations

import time

from flask import session

from ..access import me

PENDING_PLAN_TTL_SECONDS = 10 * 60


def store_pending_plan(key, plan):
    """Store a confirmation plan bound to the current user/session context."""
    user = me()
    if not user:
        return
    session[key] = {
        "plan": dict(plan),
        "user_id": user.id,
        "active_role": session.get("active_role"),
        "created_at": int(time.time()),
    }


def take_pending_plan(key):
    """Consume a valid pending plan only for the current user and role."""
    pending = session.pop(key, None)
    if not isinstance(pending, dict) or "plan" not in pending:
        return None
    user = me()
    if not user or pending.get("user_id") != user.id:
        return None
    try:
        if time.time() - float(pending.get("created_at")) > PENDING_PLAN_TTL_SECONDS:
            return None
    except (TypeError, ValueError):
        return None
    if pending.get("active_role") != session.get("active_role"):
        return None
    return pending["plan"]
