from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'employee_movements' / 'assistant' / 'routes.py').read_text(encoding='utf-8')
AGENT = (ROOT / 'employee_movements' / 'assistant' / 'agent.py').read_text(encoding='utf-8')
PENDING = (ROOT / 'employee_movements' / 'assistant' / 'pending.py').read_text(encoding='utf-8')


def test_pending_plan_uses_shared_store_and_take_helpers():
    assert 'from .pending import take_pending_plan, store_pending_plan' in ROUTES
    assert 'from .pending import store_pending_plan' in AGENT
    assert 'store_pending_plan(\'assistant_manager_pending\'' in ROUTES
    assert 'store_pending_plan(\'assistant_pending\'' in ROUTES
    assert 'take_pending_plan(\'assistant_manager_pending\'' in ROUTES
    assert 'take_pending_plan(\'assistant_pending\'' in ROUTES


def test_pending_plan_is_bound_and_expires():
    assert 'user_id' in PENDING
    assert 'active_role' in PENDING
    assert 'created_at' in PENDING
    assert 'PENDING_PLAN_TTL_SECONDS = 10 * 60' in PENDING
    assert 'time.time() - float(pending.get("created_at"))' in PENDING


def test_agent_does_not_import_routes_for_pending_storage():
    assert 'from .routes import store_pending_plan' not in AGENT
    assert 'from .routes import take_pending_plan' not in AGENT
