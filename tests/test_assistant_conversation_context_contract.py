from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'employee_movements' / 'assistant'


def test_intent_parser_packs_recent_user_turns_with_current_message():
    text = (ROOT / 'llm.py').read_text(encoding='utf-8')
    assert "def _history_for_language(chat, current_text='')" in text
    assert "prior = prior[-MAX_CONTEXT_TURNS:]" in text
    assert "MAX_CONTEXT_TURNS = 20" in text
    assert "رسائل المستخدم السابقة بالترتيب" in text
    assert "رسالة المستخدم الحالية" in text
    assert "contents = _history_for_language(chat, text)" in text


def test_agent_uses_compact_conversation_context_without_assistant_data():
    text = (ROOT / 'agent.py').read_text(encoding='utf-8')
    assert 'prior = prior[-MAX_CONVERSATION_TURNS:]' in text
    assert 'رسائل المستخدم السابقة بالترتيب' in text
    assert 'رسالة المستخدم الحالية' in text
    assert 'MAX_CONVERSATION_TURNS = 20' in text
    assert 'contents = [{"role": "user", "parts": [{"text": packed[-MAX_CONVERSATION_CHARS:]}]}]' in text
    assert 'لا تضع قيودًا اصطناعية على أنواع الأسئلة أو الصفحات' in text


def test_assistant_prompt_requires_merging_followup_fields():
    text = (ROOT / 'llm.py').read_text(encoding='utf-8')
    assert 'ولا تُسقط حقولًا سابقة ما زالت لازمة للطلب الجاري' in text


def test_context_packing_reserves_current_request_and_prefers_newest_history():
    llm = (ROOT / 'llm.py').read_text(encoding='utf-8')
    agent = (ROOT / 'agent.py').read_text(encoding='utf-8')
    for text in (llm, agent):
        assert 'current_section = ' in text
        assert 'for value in reversed(prior):' in text
        assert 'رسائل المستخدم السابقة بالترتيب (الأحدث أقرب للرسالة الحالية)' in text
        assert 'packed[-' in text
