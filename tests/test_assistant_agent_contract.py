from pathlib import Path
import ast


def test_agent_declares_application_tools():
    source = Path("employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.add(node.value)
    required = {
        "get_workspace_context", "search_employees", "get_employee_profile",
        "search_branches", "search_governorates", "search_movements",
        "prepare_action", "navigate_to",
    }
    assert required.issubset(names)


def test_old_theme_layers_are_not_loaded_by_base():
    base = Path("employee_movements/templates/base.html").read_text(encoding="utf-8")
    for legacy in ("professional-v55.css", "professional-v56.css", "professional-v57.css"):
        assert legacy not in base
