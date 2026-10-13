from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_bootstrap_never_prints_or_generates_an_unrecoverable_admin_password():
    source = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")
    block = source[source.index("def ensure_admin_account(app):"):source.index("def apply_admin_role_migrations") ]
    assert "raise ConfigError" in block
    assert "ADMIN_PASSWORD مطلوب" in block
    assert "secrets.token_urlsafe" not in block
    assert "logger.warning('تم إنشاء المسؤول" not in block
    assert "logger.warning('تم إنشاء المسؤول %r بكلمة مرور مؤقتة: %s'" not in block


def test_local_password_reset_intent_does_not_capture_user_supplied_password():
    source = (ROOT / "employee_movements/assistant/intents.py").read_text(encoding="utf-8")
    start = source.index("if has_any('غير كلمة مرور'")
    end = source.index("if has_any('عين مدخل أول'", start)
    block = source[start:end]
    assert "'password':" not in block
    assert "'employee_name': target" in block
    assert "سيُولّد" not in block  # the parser only extracts the target, not a credential


def test_arabic_password_label_variants_are_redacted_before_storage():
    source = (ROOT / "employee_movements/assistant/privacy.py").read_text(encoding="utf-8")
    assert r"كلمة\s+(?:ال)?مرور" in source
    assert r"مؤقت[ةه]" in source
    assert "redact_secrets_for_storage" in source


def test_historical_chat_cleanup_uses_the_updated_redaction_migration_key():
    source = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")
    assert "migration:assistant-chat-credential-redaction-v68.22.58" in source


def test_exception_logging_does_not_serialize_database_or_provider_error_payloads():
    paths = {
        "agent": ROOT / "employee_movements/assistant/agent.py",
        "assistant_routes": ROOT / "employee_movements/assistant/routes.py",
        "intent_llm": ROOT / "employee_movements/assistant/llm.py",
        "excel_import": ROOT / "employee_movements/blueprints/excel_import.py",
        "global_errors": ROOT / "employee_movements/errors.py",
    }
    source = {key: path.read_text(encoding="utf-8") for key, path in paths.items()}
    assert '"debug": str(exc)' not in source["agent"]
    assert 'logger.exception("Assistant tool' not in source["agent"]
    assert "logger.exception('Excel import" not in source["excel_import"]
    assert "logger.exception('Unhandled error" not in source["global_errors"]
    assert "logger.warning('Gemini intent request failed: %s', exc)" not in source["intent_llm"]
    assert "type(exc).__name__" in source["assistant_routes"]
