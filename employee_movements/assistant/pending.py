"""Single-use assistant confirmation plans stored only on the server."""
from __future__ import annotations

import json
import re

from flask import session

from ..access import me
from ..extensions import db
from ..models import AssistantSessionState
from .session_state import (
    LEGACY_PENDING_DISCARDED_KEY,
    LEGACY_PENDING_KEYS,
    get_assistant_session_state,
    utcnow_naive,
)

PENDING_PLAN_TTL_SECONDS = 10 * 60
PENDING_PLAN_KEYS = ('assistant_manager_pending', 'assistant_pending')
MAX_PENDING_PLAN_CHARS = 32_000
_SECRET_PLAN_FIELDS = {
    'password', 'password_hash', 'temporary_password', 'new_password',
    'api_key', 'gemini_api_key', 'secret_key', 'access_token', 'refresh_token',
    'authorization', 'bearer_token', 'credential', 'credentials',
}
_SECRET_PLAN_FIELDS_COMPACT = {
    'password', 'passwordhash', 'temporarypassword', 'newpassword',
    'apikey', 'geminiapikey', 'secretkey', 'accesstoken', 'refreshtoken',
    'authorization', 'bearertoken', 'credential', 'credentials',
}


def _is_secret_plan_field(key):
    raw = str(key).strip().lower()
    normalized = raw.replace('-', '_').replace(' ', '_')
    compact = re.sub(r'[^a-z0-9]', '', raw)
    return normalized in _SECRET_PLAN_FIELDS or compact in _SECRET_PLAN_FIELDS_COMPACT


def _without_credentials(value):
    """Defensively strip credential-like fields from any persisted plan tree."""
    if isinstance(value, dict):
        return {
            str(key): _without_credentials(item)
            for key, item in value.items()
            if not _is_secret_plan_field(key)
        }
    if isinstance(value, list):
        return [_without_credentials(item) for item in value]
    if isinstance(value, tuple):
        return [_without_credentials(item) for item in value]
    return value


def store_pending_plan(key, plan):
    """Persist one bounded plan server-side, replacing every competing plan."""
    if key not in PENDING_PLAN_KEYS:
        raise ValueError('Unsupported pending-plan key')
    user = me()
    if not user or not isinstance(plan, dict):
        return
    payload = json.dumps(_without_credentials(plan), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if len(payload) > MAX_PENDING_PLAN_CHARS:
        raise ValueError('Assistant confirmation plan exceeds the permitted size')
    state = get_assistant_session_state(create=True)
    if state is None or state.user_id != user.id:
        return
    # The database row has one pending-plan slot, so a new action necessarily
    # replaces an older plan. Remove pre-v69 cookie fields to fail closed.
    for legacy_key in LEGACY_PENDING_KEYS:
        session.pop(legacy_key, None)
    session.pop(LEGACY_PENDING_DISCARDED_KEY, None)
    state.pending_key = key
    state.pending_plan_json = payload
    state.pending_created_at = utcnow_naive()
    state.active_role = session.get('active_role')
    state.updated_at = utcnow_naive()


def _consume_plan(expected_key=None):
    """Atomically claim and remove a valid plan before any business write runs."""
    legacy_found = bool(session.pop(LEGACY_PENDING_DISCARDED_KEY, False))
    for legacy_key in LEGACY_PENDING_KEYS:
        if legacy_key in session:
            session.pop(legacy_key, None)
            legacy_found = True
    if legacy_found:
        # Old cookies may contain full plans in plaintext. Never execute plans
        # carried forward from pre-server-side-state releases. Conditionally
        # clear any simultaneous server plan without overwriting a newer one.
        state = get_assistant_session_state(create=False)
        if state is not None and state.pending_plan_json:
            raw_plan, key, created_at = state.pending_plan_json, state.pending_key, state.pending_created_at
            query = AssistantSessionState.query.filter_by(
                id=state.id,
                pending_key=key,
                pending_plan_json=raw_plan,
                pending_created_at=created_at,
            )
            if query.update({
                'pending_key': None,
                'pending_plan_json': None,
                'pending_created_at': None,
                'updated_at': utcnow_naive(),
            }, synchronize_session=False) == 1:
                db.session.commit()
        return None, None, True

    state = get_assistant_session_state(create=False)
    user = me()
    if not state or not user or state.user_id != user.id:
        return None, None, False
    key = state.pending_key
    raw_plan = state.pending_plan_json
    created_at = state.pending_created_at
    if not key or not raw_plan or key not in PENDING_PLAN_KEYS:
        return None, None, False
    if expected_key and key != expected_key:
        return None, None, False
    if state.active_role != session.get('active_role'):
        return None, None, False
    if not created_at or (utcnow_naive() - created_at).total_seconds() > PENDING_PLAN_TTL_SECONDS:
        AssistantSessionState.query.filter_by(
            id=state.id,
            pending_key=key,
            pending_plan_json=raw_plan,
            pending_created_at=created_at,
        ).update({
            'pending_key': None,
            'pending_plan_json': None,
            'pending_created_at': None,
            'updated_at': utcnow_naive(),
        }, synchronize_session=False)
        db.session.commit()
        return None, None, False
    try:
        plan = json.loads(raw_plan)
        if not isinstance(plan, dict):
            raise ValueError('Stored plan must be an object')
    except (TypeError, ValueError, json.JSONDecodeError):
        AssistantSessionState.query.filter_by(
            id=state.id,
            pending_key=key,
            pending_plan_json=raw_plan,
            pending_created_at=created_at,
        ).update({
            'pending_key': None,
            'pending_plan_json': None,
            'pending_created_at': None,
            'updated_at': utcnow_naive(),
        }, synchronize_session=False)
        db.session.commit()
        return None, None, True

    # Conditional UPDATE is the single-use claim. If two requests race, only one
    # can match the exact current payload/timestamp and proceed to execution.
    claimed = AssistantSessionState.query.filter_by(
        id=state.id,
        user_id=user.id,
        active_role=session.get('active_role'),
        pending_key=key,
        pending_plan_json=raw_plan,
        pending_created_at=created_at,
    ).update({
        'pending_key': None,
        'pending_plan_json': None,
        'pending_created_at': None,
        'updated_at': utcnow_naive(),
    }, synchronize_session=False)
    if claimed != 1:
        db.session.rollback()
        return None, None, False
    # Commit the claim separately so another request cannot execute the same
    # plan while the first request is still performing the business operation.
    db.session.commit()
    return key, plan, False


def take_pending_plan(key):
    """Backward-compatible helper that consumes only the named plan kind."""
    _, plan, conflict = _consume_plan(expected_key=key)
    return None if conflict else plan


def take_single_pending_plan():
    """Return ``(key, plan, conflict)`` while enforcing atomic, one-time use."""
    return _consume_plan()
