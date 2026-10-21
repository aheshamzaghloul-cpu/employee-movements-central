"""Runtime coverage for database-backed assistant state and single-use plans."""
import hashlib
from datetime import timedelta

from flask import session

from employee_movements.assistant.pending import store_pending_plan, take_single_pending_plan
from employee_movements.assistant.session_state import (
    get_context_employee_id,
    get_workspace_context,
    set_context_employee_id,
    set_workspace_context,
    utcnow_naive,
)
from employee_movements.extensions import db
from employee_movements.models import AssistantSessionState, User


def _admin_id(app):
    with app.app_context():
        user = User.query.filter_by(username='admin').first()
        assert user is not None
        return user.id


def test_pending_plan_and_sensitive_context_are_only_server_side(app):
    user_id = _admin_id(app)
    with app.test_request_context('/assistant'):
        session['uid'] = user_id
        session['active_role'] = 'مسؤول التطبيق'

        set_workspace_context('صفحة الموظف: بيانات سياقية خاصة')
        set_context_employee_id(837)
        store_pending_plan('assistant_manager_pending', {
            'action': 'employee_edit',
            'employee_id': 837,
            'temporary_password': 'must-never-be-persisted',
        })
        db.session.commit()

        token = session.get('assistant_state_token')
        assert isinstance(token, str) and len(token) >= 40
        assert 'assistant_workspace_context' not in session
        assert 'assistant_context_employee_id' not in session
        assert 'assistant_manager_pending' not in session
        assert 'assistant_pending' not in session
        assert get_workspace_context() == 'صفحة الموظف: بيانات سياقية خاصة'
        assert get_context_employee_id() == 837

        state = AssistantSessionState.query.filter_by(
            session_key_hash=hashlib.sha256(token.encode('utf-8')).hexdigest(),
        ).one()
        assert 'صفحة الموظف: بيانات سياقية خاصة' == state.workspace_context
        assert state.context_employee_id == 837
        assert 'must-never-be-persisted' not in (state.pending_plan_json or '')
        assert 'temporary_password' not in (state.pending_plan_json or '')

        key, plan, conflict = take_single_pending_plan()
        assert (key, plan, conflict) == (
            'assistant_manager_pending',
            {'action': 'employee_edit', 'employee_id': 837},
            False,
        )
        assert take_single_pending_plan() == (None, None, False)
        assert state.pending_plan_json is None


def test_role_change_invalidates_context_and_pending_plan(app):
    user_id = _admin_id(app)
    with app.test_request_context('/assistant'):
        session['uid'] = user_id
        session['active_role'] = 'مسؤول التطبيق'
        set_workspace_context('context from the old role')
        set_context_employee_id(837)
        store_pending_plan('assistant_manager_pending', {'action': 'employee_delete', 'employee_id': 837})
        db.session.commit()

        session['active_role'] = 'مشرف محافظة'
        assert get_workspace_context() == ''
        assert get_context_employee_id() is None
        db.session.commit()
        state = AssistantSessionState.query.filter_by(
            session_key_hash=hashlib.sha256(session['assistant_state_token'].encode('utf-8')).hexdigest(),
        ).one()
        assert state.pending_plan_json is None
        assert state.workspace_context is None
        assert state.context_employee_id is None


def test_expired_pending_plan_cannot_be_executed(app):
    user_id = _admin_id(app)
    with app.test_request_context('/assistant'):
        session['uid'] = user_id
        session['active_role'] = 'مسؤول التطبيق'
        store_pending_plan('assistant_manager_pending', {'action': 'employee_delete', 'employee_id': 837})
        db.session.commit()
        state = AssistantSessionState.query.filter_by(
            session_key_hash=hashlib.sha256(session['assistant_state_token'].encode('utf-8')).hexdigest(),
        ).one()
        state.pending_created_at = utcnow_naive() - timedelta(minutes=15)
        db.session.commit()

        assert take_single_pending_plan() == (None, None, False)
        db.session.refresh(state)
        assert state.pending_plan_json is None


def test_pre_server_state_cookie_plans_are_rejected(app):
    user_id = _admin_id(app)
    with app.test_request_context('/assistant'):
        session['uid'] = user_id
        session['active_role'] = 'مسؤول التطبيق'
        session['assistant_pending'] = {'plan': {'action': 'old movement'}}

        assert take_single_pending_plan() == (None, None, True)
        assert 'assistant_pending' not in session
        assert 'assistant_state_token' not in session
