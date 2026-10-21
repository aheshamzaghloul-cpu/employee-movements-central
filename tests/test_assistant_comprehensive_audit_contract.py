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


def test_branch_info_is_read_only_global_but_requires_active_branch_and_report_permission():
    text = (ROOT / "read_helpers.py").read_text(encoding="utf-8")
    start = text.index("def _visible_branch")
    end = text.index("\ndef render_branch_entry", start)
    section = text[start:end]
    assert "b.is_active" in section
    assert "governorate.is_active" in section
    assert "can('view_reports')" in section
    assert "global_movement_actor()" not in section
