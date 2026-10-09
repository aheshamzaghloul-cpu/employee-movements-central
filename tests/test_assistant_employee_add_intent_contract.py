from pathlib import Path


ROUTES = Path(__file__).resolve().parents[1] / "employee_movements" / "assistant" / "routes.py"


def test_employee_add_local_intent_cannot_be_overwritten_by_generic_gemini_intent():
    source = ROUTES.read_text(encoding="utf-8")
    assert "local_a.get('intent') in ('register_movement', 'employee_add')" in source
    assert "a.get('intent') in ('help', 'topic_options', 'employee_topic')" in source


def test_employee_add_action_targets_real_add_form():
    source = ROUTES.read_text(encoding="utf-8")
    assert "'url': '/employees#employee-add'" in source
