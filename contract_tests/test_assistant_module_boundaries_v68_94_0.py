from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "employee_movements" / "assistant"


def read(name):
    return (ASSISTANT / name).read_text(encoding="utf-8")


def test_render_compatibility_module_exports_existing_public_functions():
    source = read("render.py")
    assert "from . import render_read as _render_read" in source
    assert "from .topic_options import topic_options" in source
    for name in ("render_read", "render_branch_entry", "topic_options"):
        assert f'"{name}"' in source


def test_read_renderer_and_topic_options_are_separated():
    render_read = read("render_read.py")
    topic_options = read("topic_options.py")
    assert "def render_read(a):" in render_read
    helpers = read("read_helpers.py")
    assert "def employee_status_text(e):" in helpers
    assert "def topic_options(topic):" in topic_options
    assert "def topic_options(topic):" not in render_read
    assert "from .read_helpers import" in render_read
    assert "handle_employee_info" in render_read


def test_intent_helpers_are_imported_for_backward_compatibility():
    source = read("intents.py")
    assert "from .intent_helpers import detect_employee_field, employee_from_mixed_phrase, greeting_reply, is_greeting" in source
    helper_source = read("intent_helpers.py")
    for name in ("is_greeting", "greeting_reply", "detect_employee_field", "employee_from_mixed_phrase"):
        assert f"def {name}(" in helper_source


def test_management_intent_parser_is_classification_only():
    source = read("intent_management.py")
    assert "def parse_management_intent(" in source
    assert "authorization" in source.lower() and "execution remain" in source.lower()
    assert "can(" not in source
    assert "db.session" not in source


def test_management_parser_preserves_password_reset_redaction_boundary():
    source = read("intent_management.py")
    start = source.index("if has_any('غير كلمة مرور'")
    end = source.index("if has_any(\n        'عين مدخل أول'", start)
    block = source[start:end]
    assert "'password':" not in block
    assert "'employee_name': target" in block


def test_render_read_implementation_keeps_server_side_read_gates():
    source = read("render_read.py")
    assert "if intent in report_intents and not can('view_reports')" in source
    assert "if intent == 'employee_info' and not (can('manage_employees') or can('view_reports'))" in source
    directory_handlers = read("read_directory_handlers.py")
    movement_handlers = read("read_movement_handlers.py")
    assert "if not visible_employee(e)" in directory_handlers
    assert "if not visible_employee(e)" in movement_handlers
    assert "visible_movement(m)" in directory_handlers
    assert "visible_movement(m)" in movement_handlers


def _load_management_parser():
    import importlib.util

    path = ASSISTANT / "intent_management.py"
    spec = importlib.util.spec_from_file_location("assistant_intent_management_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.parse_management_intent


def _simple_matcher(text):
    normalized = text.lower()

    def has_any(*words):
        return any(word in text or word.lower() in normalized for word in words)

    return has_any


def test_management_parser_classifies_password_reset_without_extracting_a_password():
    parse_management_intent = _load_management_parser()
    text = "غيّر كلمة المرور للحساب أحمد علي إلى Secret-991!"
    result = parse_management_intent(text, _simple_matcher(text))
    assert result == {"intent": "user_password_reset", "employee_name": "أحمد علي"}
    assert "password" not in result


def test_management_parser_preserves_common_account_and_structure_intents():
    parse_management_intent = _load_management_parser()
    samples = [
        ("أنشئ حساب", {"intent": "user_create", "username": None, "employee_name": None, "role": None}),
        ("أضف فرع طما بمحافظة سوهاج", {"intent": "branch_create", "branch_name": "طما", "governorate_name": "سوهاج"}),
        ("عيّن مسؤول إدخال الفروع محمد حسن على فرع النيل", {"intent": "entry_assign", "employee_name": "محمد حسن", "branch_name": "فرع النيل"}),
        ("أريد تقرير الحركات", None),
    ]
    for text, expected in samples:
        assert parse_management_intent(text, _simple_matcher(text)) == expected
