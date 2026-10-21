from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (ROOT / 'employee_movements' / 'assistant' / 'routes.py').read_text(encoding='utf-8')
AGENT = (ROOT / 'employee_movements' / 'assistant' / 'agent.py').read_text(encoding='utf-8')
PENDING = (ROOT / 'employee_movements' / 'assistant' / 'pending.py').read_text(encoding='utf-8')
STATE = (ROOT / 'employee_movements' / 'assistant' / 'session_state.py').read_text(encoding='utf-8')
MODEL = (ROOT / 'employee_movements' / 'models.py').read_text(encoding='utf-8')


def test_pending_plan_uses_shared_server_store_and_single_take_helper():
    assert 'from .pending import store_pending_plan, take_single_pending_plan' in ROUTES
    assert 'from .pending import store_pending_plan' in AGENT
    assert "store_pending_plan('assistant_manager_pending'" in ROUTES
    assert "store_pending_plan('assistant_pending'" in ROUTES
    assert 'take_single_pending_plan()' in ROUTES


def test_pending_plan_is_server_side_bounded_and_scoped_to_user_role():
    assert 'MAX_PENDING_PLAN_CHARS = 32_000' in PENDING
    assert 'PENDING_PLAN_TTL_SECONDS = 10 * 60' in PENDING
    assert 'state.pending_plan_json = payload' in PENDING
    assert '_without_credentials(plan)' in PENDING
    assert 'state.pending_created_at = utcnow_naive()' in PENDING
    assert 'utcnow_naive' in PENDING
    assert 'state.user_id != user.id' in PENDING
    assert 'state.active_role != session.get' in PENDING
    assert 'class AssistantSessionState(db.Model)' in MODEL
    assert 'pending_plan_json = db.Column(db.Text)' in MODEL


def test_plan_claim_is_conditionally_updated_before_execution():
    assert 'pending_plan_json=raw_plan' in PENDING
    assert 'pending_created_at=created_at' in PENDING
    assert 'if claimed != 1:' in PENDING
    assert 'db.session.commit()' in PENDING


def test_old_cookie_plan_is_rejected_and_transient_context_is_not_in_cookie():
    assert 'legacy_found = bool(session.pop(LEGACY_PENDING_DISCARDED_KEY, False))' in PENDING
    assert 'return None, None, True' in PENDING
    assert 'session.pop(legacy_key, None)' in PENDING
    assert "session['assistant_workspace_context']" not in ROUTES
    assert "session['assistant_context_employee_id']" not in ROUTES
    assert "SESSION_TOKEN_KEY = 'assistant_state_token'" in STATE
    assert 'hashlib.sha256(token.encode' in STATE
    hooks = (ROOT / 'employee_movements' / 'hooks.py').read_text(encoding='utf-8')
    assert 'def strip_legacy_assistant_cookie_state()' in hooks
    assert 'app.before_request(strip_legacy_assistant_cookie_state)' in hooks


def test_role_switch_logout_and_clear_revoke_assistant_state():
    auth = (ROOT / 'employee_movements' / 'blueprints' / 'auth.py').read_text(encoding='utf-8')
    assert 'clear_assistant_state()' in auth
    assert "@bp.post('/logout')" in auth
    assert 'clear_assistant_state()' in ROUTES
    assert 'clear_pending_state()' in ROUTES


def test_agent_does_not_import_routes_for_pending_storage():
    assert 'from .routes import store_pending_plan' not in AGENT
    assert 'from .routes import take_pending_plan' not in AGENT

def test_explicit_workspace_context_update_commits_even_without_a_prompt():
    marker = "if 'workspace_context' in request.form:"
    start = ROUTES.index(marker)
    end = ROUTES.index("if not prompt:", start)
    block = ROUTES[start:end]
    assert 'set_workspace_context(workspace_context)' in block
    assert 'db.session.commit()' in block
    assert block.index('set_workspace_context(workspace_context)') < block.index('db.session.commit()')

