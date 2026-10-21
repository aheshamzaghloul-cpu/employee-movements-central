from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "employee_movements" / "assistant" / "routes.py"


def test_unhandled_assistant_errors_are_logged_safely_and_pending_actions_cleared():
    source = ROUTES.read_text(encoding="utf-8")
    assert "try:\n                result = answer_prompt(" in source
    # Keep useful categorical diagnostics but never serialize a traceback or raw exception
    # that could contain employee values, SQL parameters, or provider payloads.
    assert "current_app.logger.error(" in source
    assert "type(exc).__name__" in source
    assert "current_app.logger.exception(" not in source
    assert "str(exc)" not in source
    assert 'clear_pending_state()' in source
    assert "لم يتم اعتماد أي إجراء" in source
