from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "employee_movements" / "assistant"


def read(name):
    return (ASSISTANT / name).read_text(encoding="utf-8")


def _top_level_function(source, name):
    tree = ast.parse(source)
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)


def test_gemini_tool_schemas_are_separate_and_keep_known_tool_names():
    agent = read("agent.py")
    schemas = read("tool_schemas.py")
    assert "from .tool_schemas import ACTION_NAMES as ACTION_NAMES, tool_schemas" in agent
    for tool_name in ("get_workspace_context", "search_employees", "get_employee_profile", "search_branches", "search_governorates", "search_movements", "prepare_action", "navigate_to"):
        assert f'"name": "{tool_name}"' in schemas
    prepare = schemas[schemas.index('"name": "prepare_action"'):schemas.index('"name": "navigate_to"')]
    assert '"password"' not in prepare
    assert "ACTION_NAMES" in schemas


def test_tool_result_rendering_is_local_and_compatibility_wrapper_is_retained():
    agent = read("agent.py")
    renderer = read("tool_responses.py")
    assert "from .tool_responses import render_tool_result_response" in agent
    wrapper = _top_level_function(agent, "_tool_result_response")
    assert "render_tool_result_response(name, result, args, context)" in ast.unparse(wrapper)
    assert "def render_tool_result_response(name, result, args, context):" in renderer
    assert "from ..access import can" in renderer
    assert "generativelanguage.googleapis.com" not in renderer
    assert "API_KEY" not in renderer


def test_governorate_matcher_is_a_side_effect_free_resolver_and_compatibility_alias_remains():
    manager = read("manager.py")
    resolvers = read("manager_resolvers.py")
    assert "resolve_governorate as _match_gov" in manager
    assert "def resolve_governorate(name):" in resolvers
    block = resolvers[resolvers.index("def resolve_governorate(name):"):resolvers.index("def resolve_active_supervisor_by_name", resolvers.index("def resolve_governorate(name):"))]
    assert "governorate_search_filter(q)" in block
    assert "rank_governorate_suggestions(q, pool, limit=8)" in block
    assert "return None, [item['governorate'] for item in ranked]" in block
    assert "db.session.add(" not in block
    assert "db.session.commit(" not in block


def test_assistant_response_modules_keep_provider_orchestration_separate_from_local_rendering():
    agent = read("agent.py")
    tool_schemas = read("tool_schemas.py")
    tool_responses = read("tool_responses.py")
    assert "def tool_execute(name, args, ctx):" in agent
    assert "def run_agent(prompt, prior_chat, workspace_context):" in agent
    assert "def tool_schemas():" in tool_schemas
    assert "def render_tool_result_response(name, result, args, context):" in tool_responses
    assert "do not append function responses" in agent
