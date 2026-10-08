from pathlib import Path
import ast


ROOT = Path("employee_movements/assistant")
AGENT = (ROOT / "agent.py").read_text(encoding="utf-8")
ROUTES = (ROOT / "routes.py").read_text(encoding="utf-8")


def _calls(source, name):
    tree = ast.parse(source)
    return [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ((isinstance(node.func, ast.Name) and node.func.id == name)
             or (isinstance(node.func, ast.Attribute) and node.func.attr == name))
    ]


def test_agent_tool_boundary_only_prepares_mutations():
    assert "def tool_execute(name, args, ctx):" in AGENT
    assert "if name == \"prepare_action\":" in AGENT
    assert "manager_execute(" not in AGENT
    assert "_execute_movement_plan(" not in AGENT


def test_prepare_action_routes_writes_through_plan_layer():
    assert "manager_plan(normalized)" in AGENT
    assert "build_movement_plan(normalized)" in AGENT
    assert "manager_execute(" in ROUTES
    assert "_execute_movement_plan(" in ROUTES


def test_no_direct_execute_calls_inside_agent_tool_dispatch():
    dispatch = AGENT[AGENT.index("def tool_execute"):AGENT.index("def _prepare_action")]
    assert not _calls(dispatch, "execute")


def test_confirm_is_the_only_route_from_pending_plan_to_execution():
    confirm = ROUTES[ROUTES.index("def assistant_confirm"):]
    assert "take_pending_plan('assistant_manager_pending')" in confirm
    assert "take_pending_plan('assistant_pending')" in confirm
    assert "manager_execute(manager_pending)" in confirm
    assert "_execute_movement_plan(a)" in confirm
