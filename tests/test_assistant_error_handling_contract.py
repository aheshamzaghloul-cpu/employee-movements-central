from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "employee_movements" / "assistant" / "routes.py"


def test_unhandled_assistant_errors_are_logged_and_pending_actions_cleared():
    source = ROUTES.read_text(encoding="utf-8")
    assert "try:\n                result = answer_prompt(" in source
    assert "current_app.logger.exception(" in source
    assert "session.pop('assistant_pending', None)" in source
    assert "session.pop('assistant_manager_pending', None)" in source
    assert "لم يتم اعتماد أي إجراء" in source
