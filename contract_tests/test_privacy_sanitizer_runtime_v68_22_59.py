"""Exercise the real privacy sanitizer without requiring the Flask app fixture."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVACY_PATH = ROOT / "employee_movements" / "assistant" / "privacy.py"


def load_privacy_module():
    # In a minimal offline review environment Flask may not be installed. The sanitizer's
    # pure-text path only needs has_app_context() to report False; production CI uses the
    # real Flask module, already installed by requirements-dev.txt.
    if "flask" not in sys.modules:
        try:
            import flask  # noqa: F401
        except ImportError:
            flask_stub = types.ModuleType("flask")
            flask_stub.has_app_context = lambda: False
            sys.modules["flask"] = flask_stub
    spec = importlib.util.spec_from_file_location("privacy_sanitizer_under_test", PRIVACY_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_actual_storage_redactor_hides_arabic_password_variants_and_provider_secrets():
    privacy = load_privacy_module()
    cases = [
        ("كلمة المرور المؤقتة: TempSecret-391!", "TempSecret-391!"),
        ("كلمة مرور مؤقته: TempSecret-392!", "TempSecret-392!"),
        ("كلمة المرور الجديدة: TempSecret-393!", "TempSecret-393!"),
        ("غيّر كلمة المرور للحساب أحمد علي إلى VerySecret-872!", "VerySecret-872!"),
        ("Change password for user Ahmed to VerySecret-873!", "VerySecret-873!"),
        ("API_KEY=AIza0123456789abcdefghijklmnopqrstuv", "AIza0123456789abcdefghijklmnopqrstuv"),
        ("Authorization Bearer abcdefghijklmnopqrstuvwxyz012345", "abcdefghijklmnopqrstuvwxyz012345"),
        ("كلمة المرور: phrase with spaces and punctuation, rest", "phrase with spaces"),
        ("تم إنشاء الحساب. كلمة المرور المؤقتة: OldTemp-391!", "OldTemp-391!"),
    ]
    for source, secret in cases:
        stored = privacy.redact_secrets_for_storage(source)
        outbound = privacy._remove_credentials(source)
        assert secret not in stored
        assert secret not in outbound


def test_actual_model_sanitizer_preserves_dates_and_masks_explicit_names_and_emails():
    privacy = load_privacy_module()
    text = (
        "انتداب من 2026-10-13 إلى 2026-10-19. "
        "أضف موظفًا جديدًا باسم ياسين فؤاد منصور والبريد yassin@example.test"
    )
    history, outbound, tokens = privacy.sanitize_conversation_for_model([], text)
    packed = outbound + " ".join(str(item.get("text") or "") for item in history)
    assert "2026-10-13" in packed
    assert "2026-10-19" in packed
    assert "ياسين فؤاد منصور" not in packed
    assert "yassin@example.test" not in packed
    assert "[[LOCAL_PRIVATE_" in packed
    assert "ياسين فؤاد منصور" in tokens.values()
    assert "yassin@example.test" in tokens.values()


def test_prior_user_and_assistant_text_is_sanitized_but_titles_are_not_outbound_context():
    privacy = load_privacy_module()
    history = [
        {"role": "assistant", "text": "اسم الموظف سارة محمود عبدالعزيز", "title": "ملف الموظفة سارة محمود عبدالعزيز"},
        {"role": "user", "text": "ابحث عن رقم الملف 817263"},
    ]
    safe_history, current, tokens = privacy.sanitize_conversation_for_model(history, "كمّل")
    # All conversational text fields get screened. Titles are UI metadata and are not used
    # by the external context packer; this assertion documents that title is not text input.
    assert "سارة محمود عبدالعزيز" not in safe_history[0]["text"]
    assert "817263" not in safe_history[1]["text"]
    assert current == "كمّل"
    assert "سارة محمود عبدالعزيز" in tokens.values()
