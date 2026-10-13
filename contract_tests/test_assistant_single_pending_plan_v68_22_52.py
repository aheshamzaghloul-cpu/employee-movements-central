from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = (ROOT / 'employee_movements' / 'assistant' / 'pending.py').read_text(encoding='utf-8')
ROUTES = (ROOT / 'employee_movements' / 'assistant' / 'routes.py').read_text(encoding='utf-8')


def test_storing_plan_clears_the_other_pending_namespace():
    store = PENDING[PENDING.index('def store_pending_plan'):PENDING.index('def take_pending_plan')]
    assert 'for other_key in PENDING_PLAN_KEYS:' in store
    assert "session.pop(other_key, None)" in store


def test_confirmation_consumes_both_pending_slots_before_execution():
    helper = PENDING[PENDING.index('def take_single_pending_plan'): ]
    assert 'for key in PENDING_PLAN_KEYS:' in helper
    assert 'plan = take_pending_plan(key)' in helper
    assert 'if len(valid) > 1:' in helper
    assert 'return None, None, True' in helper


def test_natural_confirmation_and_form_confirmation_use_single_plan_guard():
    natural = ROUTES[ROUTES.index('def _execute_pending_naturally'):ROUTES.index('def build_movement_plan')]
    form = ROUTES[ROUTES.index('def assistant_confirm'): ]
    assert 'take_single_pending_plan()' in natural
    assert 'take_single_pending_plan()' in form
    assert "manager_pending = session.pop('assistant_manager_pending', None)" in natural
    assert "movement_pending = session.pop('assistant_pending', None)" in natural
    assert 'if conflict:' in natural and 'if conflict:' in form


def test_cancel_clears_both_slots_without_boolean_short_circuit():
    natural = ROUTES[ROUTES.index('def _execute_pending_naturally'):ROUTES.index('def build_movement_plan')]
    assert "manager_pending = session.pop('assistant_manager_pending', None)" in natural
    assert "movement_pending = session.pop('assistant_pending', None)" in natural
    assert "or session.pop('assistant_pending', None)" not in natural
