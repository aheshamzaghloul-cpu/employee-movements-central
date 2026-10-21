"""Exercise server-side pending-plan consumption without Flask-SQLAlchemy installed."""
from datetime import UTC, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys

ROOT = Path(__file__).resolve().parents[1]


def _load_pending(monkeypatch, browser_session):
    state_box = {'state': None}

    class FakeState:
        def __init__(self, **kwargs):
            self.id = 1
            self.user_id = kwargs.get('user_id', 17)
            self.active_role = kwargs.get('active_role', 'Manager')
            self.session_key_hash = kwargs.get('session_key_hash', 'a' * 64)
            self.pending_key = kwargs.get('pending_key')
            self.pending_plan_json = kwargs.get('pending_plan_json')
            self.pending_created_at = kwargs.get('pending_created_at')
            self.updated_at = kwargs.get('updated_at', datetime.now(UTC).replace(tzinfo=None))
            self.workspace_context = kwargs.get('workspace_context')
            self.context_employee_id = kwargs.get('context_employee_id')

    class FakeQuery:
        def __init__(self, filters=None):
            self.filters = filters or {}

        def filter_by(self, **filters):
            return FakeQuery({**self.filters, **filters})

        def _matches(self):
            obj = state_box['state']
            return bool(obj) and all(getattr(obj, key, None) == val for key, val in self.filters.items())

        def first(self):
            return state_box['state'] if self._matches() else None

        def update(self, values, synchronize_session=False):
            if not self._matches():
                return 0
            for key, value in values.items():
                setattr(state_box['state'], key, value)
            return 1

    class FakeDbSession:
        commits = 0
        rollbacks = 0

        def add(self, obj):
            state_box['state'] = obj

        def flush(self):
            return None

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    fake_flask = ModuleType('flask')
    fake_flask.session = browser_session
    fake_app = ModuleType('employee_movements')
    fake_app.__path__ = [str(ROOT / 'employee_movements')]
    fake_assistant = ModuleType('employee_movements.assistant')
    fake_assistant.__path__ = [str(ROOT / 'employee_movements' / 'assistant')]
    fake_access = ModuleType('employee_movements.access')
    fake_access.me = lambda: SimpleNamespace(id=17)
    fake_db_module = ModuleType('employee_movements.extensions')
    fake_db_module.db = SimpleNamespace(session=FakeDbSession())
    fake_models = ModuleType('employee_movements.models')
    FakeState.query = FakeQuery()
    fake_models.AssistantSessionState = FakeState
    fake_state_module = ModuleType('employee_movements.assistant.session_state')
    fake_state_module.LEGACY_PENDING_KEYS = ('assistant_manager_pending', 'assistant_pending')
    fake_state_module.LEGACY_PENDING_DISCARDED_KEY = '_assistant_legacy_pending_discarded'
    fake_state_module.utcnow_naive = lambda: datetime.now(UTC).replace(tzinfo=None)

    def get_state(*, create=True):
        token = browser_session.get('assistant_state_token')
        if not token and not create:
            return None
        if not token:
            browser_session['assistant_state_token'] = 'x' * 48
        if state_box['state'] is None and create:
            state_box['state'] = FakeState(user_id=17, active_role=browser_session.get('active_role'))
        return state_box['state']

    fake_state_module.get_assistant_session_state = get_state
    for name, module in {
        'flask': fake_flask,
        'employee_movements': fake_app,
        'employee_movements.assistant': fake_assistant,
        'employee_movements.access': fake_access,
        'employee_movements.extensions': fake_db_module,
        'employee_movements.models': fake_models,
        'employee_movements.assistant.session_state': fake_state_module,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    path = ROOT / 'employee_movements' / 'assistant' / 'pending.py'
    spec = spec_from_file_location('employee_movements.assistant.pending_runtime_isolated', path)
    module = module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module, state_box, fake_db_module.db.session


def test_plan_is_stored_server_side_and_only_opaque_locator_remains_in_cookie(monkeypatch):
    browser_session = {'active_role': 'Manager'}
    module, state_box, fake_session = _load_pending(monkeypatch, browser_session)

    module.store_pending_plan('assistant_manager_pending', {'action': 'new admin change', 'employee_id': 83})

    assert state_box['state'].pending_key == 'assistant_manager_pending'
    assert 'new admin change' in state_box['state'].pending_plan_json
    assert 'assistant_manager_pending' not in browser_session
    assert 'assistant_pending' not in browser_session
    assert set(browser_session) == {'active_role', 'assistant_state_token'}


def test_plan_can_be_consumed_only_once(monkeypatch):
    browser_session = {'active_role': 'Manager'}
    module, state_box, fake_session = _load_pending(monkeypatch, browser_session)
    module.store_pending_plan('assistant_manager_pending', {'action': 'new admin change'})

    key, plan, conflict = module.take_single_pending_plan()
    second_key, second_plan, second_conflict = module.take_single_pending_plan()

    assert (key, plan, conflict) == ('assistant_manager_pending', {'action': 'new admin change'}, False)
    assert (second_key, second_plan, second_conflict) == (None, None, False)
    assert state_box['state'].pending_plan_json is None
    assert fake_session.commits >= 1


def test_legacy_cookie_plan_is_discarded_without_execution(monkeypatch):
    browser_session = {
        'active_role': 'Manager',
        'assistant_pending': {'plan': {'action': 'old movement'}, 'user_id': 17},
    }
    module, state_box, _ = _load_pending(monkeypatch, browser_session)

    key, plan, conflict = module.take_single_pending_plan()

    assert (key, plan, conflict) == (None, None, True)
    assert 'assistant_pending' not in browser_session
    assert state_box['state'] is None
