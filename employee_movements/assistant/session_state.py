"""Server-side, session-scoped state for the in-app assistant.

The signed Flask cookie contains only an opaque random locator. Pending plans,
workspace text, and the contextual employee ID are persisted in the database,
scoped to the authenticated user and active role.
"""
from __future__ import annotations

import hashlib
import secrets
import time
from datetime import UTC, datetime, timedelta

from flask import current_app, session

from ..access import me, roles
from ..extensions import db
from ..models import AssistantSessionState

SESSION_TOKEN_KEY = 'assistant_state_token'
LEGACY_PENDING_DISCARDED_KEY = '_assistant_legacy_pending_discarded'
LEGACY_PENDING_KEYS = ('assistant_manager_pending', 'assistant_pending')
LEGACY_CONTEXT_KEYS = ('assistant_workspace_context', 'assistant_context_employee_id')
STATE_TTL_SECONDS = 24 * 60 * 60
WORKSPACE_CONTEXT_MAX_CHARS = 4000


def utcnow_naive() -> datetime:
    """Return a UTC timestamp without tzinfo for existing naive DB columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _session_key_hash(*, create: bool) -> str | None:
    token = session.get(SESSION_TOKEN_KEY)
    if not isinstance(token, str) or len(token) < 40:
        if not create:
            return None
        token = secrets.token_urlsafe(32)
        session[SESSION_TOKEN_KEY] = token
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _cleanup_expired_rows() -> None:
    """Periodically prune abandoned session state without a scheduled worker."""
    now_tick = time.monotonic()
    extension_key = 'assistant_state_cleanup_last_monotonic'
    try:
        last_tick = float(current_app.extensions.get(extension_key, 0))
        if now_tick - last_tick < 15 * 60:
            return
        # Throttle independently in each worker. The operation is idempotent and
        # runs only occasionally, avoiding a DELETE on every chat request.
        current_app.extensions[extension_key] = now_tick
        cutoff = utcnow_naive() - timedelta(seconds=STATE_TTL_SECONDS)
        AssistantSessionState.query.filter(AssistantSessionState.updated_at < cutoff).delete(
            synchronize_session=False,
        )
    except RuntimeError:
        # No Flask application context; callers can still use an existing row in
        # an appropriately configured test harness.
        return


def get_assistant_session_state(*, create: bool = True) -> AssistantSessionState | None:
    """Return state for the current authenticated browser session, if available."""
    user = me()
    if not user:
        return None
    # Validate and normalize the cookie's role against current database roles
    # before reading a pending plan. If this role was revoked, roles() removes
    # the stale selector; the role mismatch below then clears old assistant state.
    roles(user)
    # Remove plaintext context left in signed cookies by pre-server-state versions.
    # Legacy pending plans are deliberately handled by pending.py so confirmation
    # can fail closed with a useful conflict message instead of silently executing.
    for legacy_key in LEGACY_CONTEXT_KEYS:
        session.pop(legacy_key, None)
    key_hash = _session_key_hash(create=create)
    if not key_hash:
        return None
    _cleanup_expired_rows()

    state = AssistantSessionState.query.filter_by(session_key_hash=key_hash).first()
    if state is not None and state.user_id != user.id:
        # A locator must never transfer state between accounts. Delete the stale
        # row and rotate the locator instead of reassigning ownership.
        db.session.delete(state)
        db.session.flush()
        session.pop(SESSION_TOKEN_KEY, None)
        key_hash = _session_key_hash(create=create)
        state = None

    if state is None:
        if not create:
            return None
        state = AssistantSessionState(
            session_key_hash=key_hash,
            user_id=user.id,
            active_role=session.get('active_role'),
        )
        db.session.add(state)
        db.session.flush()
        return state

    now = utcnow_naive()
    if state.updated_at and (now - state.updated_at).total_seconds() > STATE_TTL_SECONDS:
        state.pending_key = None
        state.pending_plan_json = None
        state.pending_created_at = None
        state.workspace_context = None
        state.context_employee_id = None
        state.updated_at = now

    # A role transition invalidates all assistant context even if an older
    # session cookie survives from before the explicit role-switch cleanup.
    active_role = session.get('active_role')
    if state.active_role != active_role:
        state.pending_key = None
        state.pending_plan_json = None
        state.pending_created_at = None
        state.workspace_context = None
        state.context_employee_id = None
        state.active_role = active_role
        state.updated_at = now
    return state


def get_workspace_context() -> str:
    state = get_assistant_session_state(create=False)
    return str(state.workspace_context or '') if state else ''


def set_workspace_context(value: str | None) -> None:
    state = get_assistant_session_state(create=True)
    if state is None:
        return
    state.workspace_context = str(value or '')[:WORKSPACE_CONTEXT_MAX_CHARS]
    state.updated_at = utcnow_naive()


def get_context_employee_id() -> int | None:
    state = get_assistant_session_state(create=False)
    if not state or state.context_employee_id is None:
        return None
    try:
        value = int(state.context_employee_id)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def set_context_employee_id(employee_id: object) -> None:
    state = get_assistant_session_state(create=True)
    if state is None:
        return
    try:
        value = int(employee_id) if employee_id is not None else None
    except (TypeError, ValueError):
        value = None
    state.context_employee_id = value if value and value > 0 else None
    state.updated_at = utcnow_naive()


def clear_pending_state() -> bool:
    """Clear the pending operation and report whether anything was pending."""
    legacy_found = bool(session.pop(LEGACY_PENDING_DISCARDED_KEY, False)) or any(
        key in session for key in LEGACY_PENDING_KEYS
    )
    for key in LEGACY_PENDING_KEYS:
        session.pop(key, None)
    state = get_assistant_session_state(create=False)
    had_pending = bool(state and state.pending_key and state.pending_plan_json)
    if state is not None:
        state.pending_key = None
        state.pending_plan_json = None
        state.pending_created_at = None
        state.updated_at = utcnow_naive()
    return legacy_found or had_pending


def clear_assistant_state(*, revoke_token: bool = True) -> None:
    """Discard all transient assistant state for this browser session."""
    for key in (*LEGACY_PENDING_KEYS, *LEGACY_CONTEXT_KEYS, LEGACY_PENDING_DISCARDED_KEY):
        session.pop(key, None)
    state = get_assistant_session_state(create=False)
    if state is not None:
        db.session.delete(state)
    if revoke_token:
        session.pop(SESSION_TOKEN_KEY, None)
