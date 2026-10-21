from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / 'employee_movements' / 'assistant' / 'manager.py'
EXECUTOR = ROOT / 'employee_movements' / 'assistant' / 'manager_execution.py'


def test_manager_execute_owns_transaction_rollback_boundary():
    text = MANAGER.read_text(encoding='utf-8')
    public = text[text.index('def execute(plan):'):text.index('def _execute(plan):')]
    assert 'db.session.rollback()' in public
    assert 'ok, message = _execute(plan)' in public
    assert 'db.session.commit()' in public


def test_inner_manager_executor_keeps_single_commit_point():
    text = EXECUTOR.read_text(encoding='utf-8')
    assert text.count('db.session.commit()') == 0
    assert 'def execute_plan(plan):' in text
