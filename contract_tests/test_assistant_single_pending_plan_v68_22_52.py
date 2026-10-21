from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = (ROOT / 'employee_movements' / 'assistant' / 'pending.py').read_text(encoding='utf-8')
STATE = (ROOT / 'employee_movements' / 'assistant' / 'session_state.py').read_text(encoding='utf-8')
ROUTES = (ROOT / 'employee_movements' / 'assistant' / 'routes.py').read_text(encoding='utf-8')


def test_plan_payload_is_json_serialized_to_server_state_not_client_cookie():
    store = PENDING[PENDING.index('def store_pending_plan'):PENDING.index('def _consume_plan')]
    assert 'json.dumps(_without_credentials(plan), ensure_ascii=False' in store
    assert 'state.pending_plan_json = payload' in store
    assert 'session[key]' not in store
    assert 'MAX_PENDING_PLAN_CHARS' in store
    assert '_without_credentials(plan)' in store


def test_plan_claim_is_atomic_and_single_use():
    consume = PENDING[PENDING.index('def _consume_plan'):PENDING.index('def take_pending_plan')]
    assert 'pending_plan_json=raw_plan' in consume
    assert 'pending_created_at=created_at' in consume
    assert 'if claimed != 1:' in consume
    assert 'db.session.commit()' in consume


def test_legacy_cookie_plan_is_fail_closed():
    consume = PENDING[PENDING.index('def _consume_plan'):PENDING.index('def take_pending_plan')]
    assert 'legacy_found = bool(session.pop(LEGACY_PENDING_DISCARDED_KEY, False))' in consume
    assert 'return None, None, True' in consume
    assert "session.pop(legacy_key, None)" in consume


def test_confirmation_routes_use_the_single_server_side_claim():
    natural = ROUTES[ROUTES.index('def _execute_pending_naturally'):ROUTES.index('def build_movement_plan')]
    form = ROUTES[ROUTES.index('def assistant_confirm'):]
    assert 'take_single_pending_plan()' in natural
    assert 'take_single_pending_plan()' in form
    assert 'if conflict:' in natural and 'if conflict:' in form
    assert 'clear_pending_state()' in natural


def test_transient_context_is_server_side_and_tied_to_user_and_role():
    assert "SESSION_TOKEN_KEY = 'assistant_state_token'" in STATE
    assert 'hashlib.sha256(token.encode' in STATE
    hooks = (ROOT / 'employee_movements' / 'hooks.py').read_text(encoding='utf-8')
    assert 'def strip_legacy_assistant_cookie_state()' in hooks
    assert 'app.before_request(strip_legacy_assistant_cookie_state)' in hooks
    assert 'state.user_id != user.id' in STATE
    assert 'state.active_role != active_role' in STATE
    assert "session['assistant_workspace_context']" not in ROUTES
    assert "session['assistant_context_employee_id']" not in ROUTES
