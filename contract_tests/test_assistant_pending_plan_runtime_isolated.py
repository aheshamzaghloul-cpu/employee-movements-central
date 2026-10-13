"""Exercise the pending-plan helper with an isolated fake Flask session."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def _load_pending(monkeypatch, session):
    flask_stub = ModuleType('flask')
    flask_stub.session = session

    app_package = ModuleType('employee_movements')
    app_package.__path__ = [str(ROOT / 'employee_movements')]
    assistant_package = ModuleType('employee_movements.assistant')
    assistant_package.__path__ = [str(ROOT / 'employee_movements' / 'assistant')]
    access_stub = ModuleType('employee_movements.access')
    access_stub.me = lambda: SimpleNamespace(id=17)

    monkeypatch.setitem(sys.modules, 'flask', flask_stub)
    monkeypatch.setitem(sys.modules, 'employee_movements', app_package)
    monkeypatch.setitem(sys.modules, 'employee_movements.assistant', assistant_package)
    monkeypatch.setitem(sys.modules, 'employee_movements.access', access_stub)

    path = ROOT / 'employee_movements' / 'assistant' / 'pending.py'
    spec = spec_from_file_location('employee_movements.assistant.pending_runtime_isolated', path)
    module = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_new_plan_replaces_the_other_pending_slot(monkeypatch):
    session = {
        'active_role': 'Manager',
        'assistant_pending': {'plan': {'action': 'old movement'}, 'user_id': 17,
                              'active_role': 'Manager', 'created_at': int(time.time())},
    }
    module = _load_pending(monkeypatch, session)

    module.store_pending_plan('assistant_manager_pending', {'action': 'new admin change'})

    assert 'assistant_pending' not in session
    assert session['assistant_manager_pending']['plan'] == {'action': 'new admin change'}


def test_two_legacy_valid_plans_are_consumed_and_rejected(monkeypatch):
    now = int(time.time())
    session = {
        'active_role': 'Manager',
        'assistant_manager_pending': {'plan': {'action': 'manager change'}, 'user_id': 17,
                                      'active_role': 'Manager', 'created_at': now},
        'assistant_pending': {'plan': {'action': 'movement'}, 'user_id': 17,
                              'active_role': 'Manager', 'created_at': now},
    }
    module = _load_pending(monkeypatch, session)

    key, plan, conflict = module.take_single_pending_plan()

    assert (key, plan, conflict) == (None, None, True)
    assert 'assistant_manager_pending' not in session
    assert 'assistant_pending' not in session
