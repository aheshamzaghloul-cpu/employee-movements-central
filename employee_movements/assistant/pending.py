"""Short-lived confirmation plans for the in-app assistant."""
from __future__ import annotations

import time

from flask import session

from ..access import me

PENDING_PLAN_TTL_SECONDS = 10 * 60
PENDING_PLAN_KEYS = ('assistant_manager_pending', 'assistant_pending')


def store_pending_plan(key, plan):
    """Store one confirmation plan and discard any competing pending action."""
    if key not in PENDING_PLAN_KEYS:
        raise ValueError('Unsupported pending-plan key')
    user = me()
    if not user:
        return
    # A user may confirm only one intended operation at a time. Clear the other
    # namespace before storing so a later affirmative reply cannot execute stale work.
    for other_key in PENDING_PLAN_KEYS:
        if other_key != key:
            session.pop(other_key, None)
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


def take_single_pending_plan():
    """Consume both pending slots and return at most one valid plan.

    Returns ``(key, plan, conflict)``. If two valid plans are found (for example,
    from a session created before the single-plan invariant), both are discarded
    and ``conflict`` is true; callers must not execute either one automatically.
    """
    valid = []
    for key in PENDING_PLAN_KEYS:
        plan = take_pending_plan(key)
        if plan is not None:
            valid.append((key, plan))
    if len(valid) > 1:
        return None, None, True
    if not valid:
        return None, None, False
    key, plan = valid[0]
    return key, plan, False
