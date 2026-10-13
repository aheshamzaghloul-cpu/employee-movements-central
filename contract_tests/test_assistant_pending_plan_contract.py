from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'employee_movements' / 'assistant' / 'routes.py').read_text(encoding='utf-8')
AGENT = (ROOT / 'employee_movements' / 'assistant' / 'agent.py').read_text(encoding='utf-8')
PENDING = (ROOT / 'employee_movements' / 'assistant' / 'pending.py').read_text(encoding='utf-8')


def test_pending_plan_uses_shared_store_and_single_take_helper():
    assert 'from .pending import store_pending_plan, take_single_pending_plan' in ROUTES
    assert 'from .pending import store_pending_plan' in AGENT
    assert "store_pending_plan('assistant_manager_pending'" in ROUTES
    assert "store_pending_plan('assistant_pending'" in ROUTES
    assert 'take_single_pending_plan()' in ROUTES


def test_pending_plan_is_bound_expires_and_has_one_active_slot():
    assert 'user_id' in PENDING
    assert 'active_role' in PENDING
    assert 'created_at' in PENDING
    assert 'PENDING_PLAN_TTL_SECONDS = 10 * 60' in PENDING
    assert "PENDING_PLAN_KEYS = ('assistant_manager_pending', 'assistant_pending')" in PENDING
    assert 'time.time() - float(pending.get("created_at"))' in PENDING
    store = PENDING[PENDING.index('def store_pending_plan'):PENDING.index('def take_pending_plan')]
    assert 'for other_key in PENDING_PLAN_KEYS:' in store
    assert 'session.pop(other_key, None)' in store


def test_pending_plan_confirmation_consumes_both_slots_and_rejects_conflict():
    helper = PENDING[PENDING.index('def take_single_pending_plan'):]
    assert 'for key in PENDING_PLAN_KEYS:' in helper
    assert 'plan = take_pending_plan(key)' in helper
    assert 'if len(valid) > 1:' in helper
    assert 'return None, None, True' in helper
    assert 'take_single_pending_plan()' in ROUTES


def test_agent_does_not_import_routes_for_pending_storage():
    assert 'from .routes import store_pending_plan' not in AGENT
    assert 'from .routes import take_pending_plan' not in AGENT
