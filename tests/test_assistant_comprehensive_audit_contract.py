from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "employee_movements" / "assistant"


def test_movement_scope_helpers_are_imported_where_used():
    text = (ROOT / "routes.py").read_text(encoding="utf-8")
    imports = text.split("from ..extensions", 1)[0]
    assert "can_manage_movement_employee" in imports
    assert "can_manage_movement_destination" in imports


def test_high_confidence_employee_add_bypasses_generic_agent_answer():
    text = (ROOT / "routes.py").read_text(encoding="utf-8")
    start = text.index("def answer_prompt")
    end = text.index("    agent_result = run_agent", start)
    section = text[start:end]
    assert "local_fast.get('intent') == 'employee_add'" in section
    assert "'/employees#employee-add'" in section


def test_gemini_history_excludes_persisted_assistant_replies():
    agent = (ROOT / "agent.py").read_text(encoding="utf-8")
    llm = (ROOT / "llm.py").read_text(encoding="utf-8")
    assert 'if item.get("role") != "user":' in agent
    assert "if item.get('role') != 'user':" in llm
    assert "MAX_CONVERSATION_TURNS = 20" in agent
    assert "MAX_CONTEXT_TURNS = 20" in llm


def test_model_visible_workspace_context_redacts_selected_record_ids():
    text = (ROOT / "agent.py").read_text(encoding="utf-8")
    assert 'key: True for key, value in (ctx.get("selected", {}) or {}).items()' in text


def test_branch_info_uses_operational_scope_not_global_supervisor_bypass():
    text = (ROOT / "render.py").read_text(encoding="utf-8")
    start = text.index("def _visible_branch")
    end = text.index("\n\ndef topic_options", start)
    section = text[start:end]
    assert "branch_ok(b.id)" in section
    assert "global_movement_actor()" not in section
