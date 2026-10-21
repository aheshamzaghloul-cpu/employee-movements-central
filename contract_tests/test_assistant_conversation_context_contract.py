from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'employee_movements' / 'assistant'


def test_intent_parser_packs_recent_user_turns_with_current_message():
    llm = (ROOT / 'llm.py').read_text(encoding='utf-8')
    context = (ROOT / 'conversation_context.py').read_text(encoding='utf-8')
    assert "def _history_for_language(chat, current_text='')" in llm
    assert "return _pack_history_for_language(chat, current_text)" in llm
    assert "prior = prior[-MAX_CONTEXT_TURNS:]" in context
    assert "MAX_CONTEXT_TURNS = 20" in context
    assert "رسائل المستخدم السابقة بالترتيب" in context
    assert "رسالة المستخدم الحالية" in context
    assert "contents = _history_for_language(chat, text)" in llm


def test_agent_uses_compact_conversation_context_without_assistant_data():
    agent = (ROOT / 'agent.py').read_text(encoding='utf-8')
    context = (ROOT / 'conversation_context.py').read_text(encoding='utf-8')
    assert 'contents = build_agent_contents(prior_chat, prompt)' in agent
    assert 'prior = prior[-MAX_CONVERSATION_TURNS:]' in context
    assert 'رسائل المستخدم السابقة بالترتيب' in context
    assert 'رسالة المستخدم الحالية' in context
    assert 'MAX_CONVERSATION_TURNS = 20' in context
    assert 'packed = "\\n\\n".join(sections)' in context
    assert 'packed[-MAX_CONVERSATION_CHARS:]' in context
    assert 'لا تضع قيودًا اصطناعية على أنواع الأسئلة أو الصفحات' in agent


def test_assistant_prompt_requires_merging_followup_fields():
    text = (ROOT / 'llm.py').read_text(encoding='utf-8')
    assert 'ولا تُسقط حقولًا سابقة ما زالت لازمة للطلب الجاري' in text


def test_context_packing_reserves_current_request_and_prefers_newest_history():
    context = (ROOT / 'conversation_context.py').read_text(encoding='utf-8')
    for marker in (
        'current_section = ',
        'for value in reversed(prior):',
        'رسائل المستخدم السابقة بالترتيب (الأحدث أقرب للرسالة الحالية)',
        'packed[-',
    ):
        assert marker in context

