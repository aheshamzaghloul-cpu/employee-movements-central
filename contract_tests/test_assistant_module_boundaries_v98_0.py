from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "employee_movements" / "assistant"


def read(name):
    return (ASSISTANT / name).read_text(encoding="utf-8")


def test_tool_dispatch_is_a_separate_local_boundary():
    dispatch = read("tool_dispatch.py")
    agent = read("agent.py")
    assert "def dispatch_tool(name, args, ctx):" in dispatch
    assert "from .tool_read_handlers import execute_read_tool" in dispatch
    assert 'if name == "prepare_action":' in dispatch
    assert "return _dispatch_tool(name, args, ctx)" in agent
    assert "manager_execute(" not in dispatch
    assert "_execute_movement_plan(" not in dispatch


def test_action_preparation_only_builds_confirmation_ready_plans():
    preparation = read("action_preparation.py")
    assert "def prepare_action(args, ctx):" in preparation
    assert "manager_plan(normalized)" in preparation
    assert "build_movement_plan(normalized)" in preparation
    assert 'normalized.pop("password", None)' in preparation
    assert "needs_confirmation" in preparation
    assert "db.session.commit()" not in preparation
    assert "manager_execute(" not in preparation


def test_legacy_agent_names_remain_as_thin_compatibility_wrappers():
    agent = read("agent.py")
    assert "def tool_execute(name, args, ctx):" in agent
    assert "return _dispatch_tool(name, args, ctx)" in agent
    assert "def _prepare_action(args, ctx):" in agent
    assert "return _prepare_action_impl(args, ctx)" in agent
    assert "normalized.pop(\"password\", None)" not in agent


def test_action_preparation_and_dispatch_do_not_commit_or_execute_writes():
    combined = read("tool_dispatch.py") + read("action_preparation.py")
    for forbidden in ("db.session.commit(", "db.session.delete(", "manager_execute(", "_execute_movement_plan("):
        assert forbidden not in combined


def test_navigation_capability_checks_remain_in_local_dispatch():
    dispatch = read("tool_dispatch.py")
    for gate in (
        'if target == "delegations"',
        'if target in {"administration", "users", "branches", "governorates", "lookups"}',
        'if target == "audit" and not can("view_audit")',
        'if target in {"employees", "employee"}',
        'if target in {"movements", "reports", "missions"}',
    ):
        assert gate in dispatch
