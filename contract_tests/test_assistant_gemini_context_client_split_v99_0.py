from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "employee_movements" / "assistant"


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_gemini_http_transport_is_shared_and_does_not_own_prompt_policy():
    client = (ASSISTANT / "gemini_client.py").read_text(encoding="utf-8")
    agent = (ASSISTANT / "agent.py").read_text(encoding="utf-8")
    llm = (ASSISTANT / "llm.py").read_text(encoding="utf-8")
    assert "def generate_content(*, model: str, payload: dict, api_key: str, timeout: int" in client
    assert "x-goog-api-key" in client and "Content-Type" in client
    assert "logger." not in client
    assert "def _call_gemini(contents, context):" in agent
    assert "_generate_content(" in agent
    assert "generate_content(" in llm
    assert "sanitize_conversation_for_model(prior_chat, prompt)" in agent
    assert "sanitize_conversation_for_model(chat, text)" in llm


def test_agent_and_intent_history_packers_are_centralized_and_keep_compatibility_wrappers():
    context = (ASSISTANT / "conversation_context.py").read_text(encoding="utf-8")
    agent = (ASSISTANT / "agent.py").read_text(encoding="utf-8")
    llm = (ASSISTANT / "llm.py").read_text(encoding="utf-8")
    assert "def build_agent_contents(prior_chat, prompt):" in context
    assert "def history_for_language(chat, current_text=''):" in context
    assert "contents = build_agent_contents(prior_chat, prompt)" in agent
    assert "def _history_for_language(chat, current_text=''):" in llm
    assert "return _pack_history_for_language(chat, current_text)" in llm
    assert 'if item.get("role") != "user":' in context


def test_packing_never_forwards_assistant_replies_and_preserves_current_request():
    module = _load_module("conversation_context_test", ASSISTANT / "conversation_context.py")
    contents = module.build_agent_contents(
        [
            {"role": "user", "text": "طلب قديم"},
            {"role": "assistant", "text": "رد يحتوي بيانات سجل لا يجب إرساله"},
            {"role": "user", "text": "متابعة من المستخدم"},
        ],
        "الطلب الحالي المميز",
    )
    packed = contents[0]["parts"][0]["text"]
    assert "طلب قديم" in packed
    assert "متابعة من المستخدم" in packed
    assert "الطلب الحالي المميز" in packed
    assert "رد يحتوي بيانات سجل لا يجب إرساله" not in packed
    intent_contents = module.history_for_language(
        [{"role": "assistant", "text": "بيانات سرية"}, {"role": "user", "text": "سؤال سابق"}],
        "السؤال الحالي",
    )
    intent_packed = intent_contents[0]["parts"][0]["text"]
    assert "سؤال سابق" in intent_packed and "السؤال الحالي" in intent_packed
    assert "بيانات سرية" not in intent_packed


def test_gemini_transport_encodes_model_and_uses_configured_auth_timeout_and_payload():
    client = _load_module("gemini_client_test", ASSISTANT / "gemini_client.py")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"candidates": []}'

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["api_key"] = request.get_header("X-goog-api-key")
        captured["content_type"] = request.get_header("Content-type")
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    with patch.object(client.urllib.request, "urlopen", fake_urlopen):
        result = client.generate_content(
            model="models/gemini test",
            payload={"system_instruction": {"parts": [{"text": "سياق عربي"}]}},
            api_key="test-key-placeholder",
            timeout=13,
            ensure_ascii=False,
        )
    assert result == {"candidates": []}
    assert "/models/gemini%20test:generateContent" in captured["url"]
    assert captured["api_key"] == "test-key-placeholder"
    assert captured["content_type"] == "application/json"
    assert captured["body"]["system_instruction"]["parts"][0]["text"] == "سياق عربي"
    assert captured["timeout"] == 13


def test_gemini_transport_without_key_does_not_open_network():
    client = _load_module("gemini_client_no_key_test", ASSISTANT / "gemini_client.py")
    with patch.object(client.urllib.request, "urlopen", side_effect=AssertionError("network must not be called")):
        assert client.generate_content(
            model="gemini-test", payload={}, api_key="", timeout=2
        ) is None
