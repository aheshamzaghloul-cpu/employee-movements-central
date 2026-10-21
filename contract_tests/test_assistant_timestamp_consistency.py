"""Prevent the UTC-naive assistant timestamp migration from leaving stale tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PENDING = (ROOT / 'employee_movements' / 'assistant' / 'pending.py').read_text(encoding='utf-8')
PENDING_CONTRACT = (ROOT / 'tests' / 'test_assistant_pending_plan_contract.py').read_text(encoding='utf-8')
PENDING_RUNTIME = (ROOT / 'tests' / 'test_assistant_server_state_runtime.py').read_text(encoding='utf-8')


def test_assistant_pending_timestamp_source_and_tests_use_the_same_utc_helper():
    assert 'utcnow_naive,' in PENDING
    assert 'state.pending_created_at = utcnow_naive()' in PENDING
    assert "assert 'state.pending_created_at = utcnow_naive()' in PENDING" in PENDING_CONTRACT
    assert 'utcnow_naive,' in PENDING_RUNTIME
    assert 'state.pending_created_at = utcnow_naive() - timedelta(minutes=15)' in PENDING_RUNTIME
    assert 'state.pending_created_at = datetime.utcnow()' not in PENDING_CONTRACT
    assert 'state.pending_created_at = datetime.utcnow()' not in PENDING_RUNTIME
