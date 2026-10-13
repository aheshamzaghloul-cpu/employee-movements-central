"""Privacy boundary regression tests for text passed to external AI services."""

from employee_movements.assistant.privacy import (
    redact_secrets_for_storage,
    restore_local_tokens,
    sanitize_conversation_for_model,
)
from employee_movements.extensions import db
from employee_movements.models import Branch, Employee, Governorate


def test_chat_storage_removes_temporary_passwords_and_api_secrets():
    source = (
        "تم إنشاء الحساب. كلمة المرور المؤقتة: TempSecret-391! "
        "والمفتاح API_KEY=AIza0123456789abcdefghijklmnopqrstuv"
    )

    stored = redact_secrets_for_storage(source)

    assert "TempSecret-391!" not in stored
    assert "AIza0123456789abcdefghijklmnopqrstuv" not in stored
    assert "تم إخفاء السر" in stored or "تم إخفاء قيمة سرية محتملة" in stored
    passphrase = "كلمة المرور: phrase with spaces and punctuation, rest"
    assert "phrase with spaces" not in redact_secrets_for_storage(passphrase)


def test_chat_storage_redacts_arabic_temporary_password_label_variants():
    variants = [
        "كلمة المرور المؤقتة: TempSecret-391!",
        "كلمة مرور مؤقتة: TempSecret-392!",
        "كلمة مرور مؤقته: TempSecret-393!",
        "كلمة المرور الجديدة: TempSecret-394!",
        "كلمة مرور جديدة: TempSecret-395!",
    ]
    for source in variants:
        secret = source.split(":", 1)[1].strip()
        stored = redact_secrets_for_storage(source)
        assert secret not in stored
        assert "تم إخفاء السر" in stored or "تم إخفاء قيمة سرية محتملة" in stored


def test_model_prompt_replaces_known_employee_name_code_and_phone(app):
    with app.app_context():
        gov = Governorate(name="خصوصية-اختبار-المحافظة")
        db.session.add(gov)
        db.session.flush()
        branch = Branch(name="خصوصية-اختبار-الفرع", code="PRIV-BR", governorate_id=gov.id)
        db.session.add(branch)
        db.session.flush()
        employee = Employee(
            full_name="أحمد شريف عبدالسلام",
            employee_code="817263",
            job_code="JOB-7284",
            email="ahmed.privacy@example.test",
            personal_phone="01012345678",
            company_phone="0223456789",
            branch_id=branch.id,
        )
        db.session.add(employee)
        db.session.commit()

        history = [{"role": "user", "text": "ابحث عن أحمد شريف عبدالسلام بالكود 817263"}]
        current = "رقم الهاتف 01012345678 وبريد ahmed.privacy@example.test"
        safe_history, safe_current, token_map = sanitize_conversation_for_model(history, current)
        outbound = "\n".join(item.get("text", "") for item in safe_history) + "\n" + safe_current

        assert "أحمد شريف عبدالسلام" not in outbound
        assert "817263" not in outbound
        assert "01012345678" not in outbound
        assert "ahmed.privacy@example.test" not in outbound
        assert "[[LOCAL_PRIVATE_" in outbound
        assert restore_local_tokens(safe_history[0]["text"], token_map) == history[0]["text"]
        assert restore_local_tokens(safe_current, token_map).endswith(current) or restore_local_tokens(safe_current, token_map) == current


def test_explicit_credentials_are_removed_not_reversibly_aliased():
    history, current, token_map = sanitize_conversation_for_model(
        [], "كلمة المرور المؤقتة: NeverSendThis-91! ثم أكمل إنشاء الحساب"
    )
    outbound = current + "\n".join(item.get("text", "") for item in history)

    assert "NeverSendThis-91!" not in outbound
    assert "[[LOCAL_PRIVATE_" not in outbound
    assert "تم حجب بيانات الاعتماد" in outbound
    assert all("NeverSendThis-91!" != value for value in token_map.values())


def test_model_sanitizer_preserves_explicit_dates_and_removes_credentials():
    # No application context is needed for the pure string-sanitization path.
    from employee_movements.assistant.privacy import sanitize_conversation_for_model

    history, current, token_map = sanitize_conversation_for_model(
        [], "انتداب من 2026-10-13 إلى 2026-10-19 وكلمة المرور المؤقتة DoNotSend-987!"
    )

    assert "2026-10-13" in current
    assert "2026-10-19" in current
    assert "DoNotSend-987!" not in current
    assert "TEMPSECRET" not in current
    assert not token_map


def test_explicitly_labeled_new_employee_name_is_hidden_even_before_it_exists_locally():
    from employee_movements.assistant.privacy import sanitize_conversation_for_model

    _, current, token_map = sanitize_conversation_for_model(
        [], "أضف موظفًا جديدًا باسم ياسين فؤاد منصور إلى النظام"
    )

    assert "ياسين فؤاد منصور" not in current
    assert "[[LOCAL_PRIVATE_" in current
    assert "ياسين فؤاد منصور" in token_map.values()

    _, account_prompt, account_map = sanitize_conversation_for_model(
        [], "أنشئ حساب باسم سارة محمود عبدالعزيز والبريد sara@example.test واسم الدخول full_review_test"
    )
    assert "سارة محمود عبدالعزيز" not in account_prompt
    assert "full_review_test" not in account_prompt
    assert "sara@example.test" not in account_prompt
    assert len(account_map) >= 3


def test_password_reset_suffix_is_never_sent_or_persisted():
    from employee_movements.assistant.privacy import _remove_credentials

    prompts = [
        ("غيّر كلمة المرور للحساب أحمد علي إلى VerySecret-872!", "VerySecret-872!", "أحمد علي"),
        ("إعادة تعيين كلمة المرور للمستخدم سارة إلى Secret-9001", "Secret-9001", "سارة"),
        ("Change password for user Ahmed to VerySecret-872!", "VerySecret-872!", "Ahmed"),
        ("غيّر كلمة المرور للحساب أحمد علي إلى Very,Secret-872! ثم أكمل", "Very,Secret-872!", "أحمد علي"),
    ]
    for prompt, secret, target_name in prompts:
        sanitized = _remove_credentials(prompt)
        stored = redact_secrets_for_storage(prompt)
        assert secret not in sanitized
        assert secret not in stored
        assert target_name in sanitized
        assert target_name in stored


def test_assistant_history_is_sanitized_even_if_not_forwarded_today(app):
    with app.app_context():
        gov = Governorate(name="خصوصية-تاريخ-المساعد")
        db.session.add(gov)
        db.session.flush()
        branch = Branch(name="فرع-خصوصية-التاريخ", code="PRIV-HIST", governorate_id=gov.id)
        db.session.add(branch)
        db.session.flush()
        employee = Employee(
            full_name="سلمى عادل إبراهيم", employee_code="HIST-56321", branch_id=branch.id,
            personal_phone="01076543210", company_phone="0222223344",
        )
        db.session.add(employee)
        db.session.commit()
        chat = [
            {"role": "assistant", "text": "وجدت الموظفة سلمى عادل إبراهيم بالكود HIST-56321"},
            {"role": "user", "text": "افتح ملفها"},
        ]
        safe_chat, _, _ = sanitize_conversation_for_model(chat, "ما آخر حركة لها؟")
        outbound_history = " ".join(item["text"] for item in safe_chat)
        assert "سلمى عادل إبراهيم" not in outbound_history
        assert "HIST-56321" not in outbound_history


def test_historical_assistant_chat_passwords_are_redacted_by_one_time_migration(app):
    from employee_movements.bootstrap import _redact_historical_assistant_credentials
    from employee_movements.models import AssistantMessage, Lookup, User

    migration_key = "migration:assistant-chat-credential-redaction-v68.22.58"
    with app.app_context():
        # The app fixture initializes the DB; clear the one-time marker so this
        # test can exercise the migration against simulated pre-upgrade history.
        Lookup.query.filter_by(kind="system_migration", name=migration_key).delete()
        user = User.query.filter_by(username="admin").first()
        messages = [
            AssistantMessage(
                user_id=user.id, role="assistant",
                text="تم إنشاء الحساب. كلمة المرور المؤقتة: OldTemp-391!",
                title="كلمة المرور المؤقتة: OldTemp-391!",
            ),
            AssistantMessage(
                user_id=user.id, role="user",
                text="غيّر كلمة المرور للحساب أحمد علي إلى OldReset,Secret-882!",
            ),
        ]
        db.session.add_all(messages)
        db.session.commit()
        _redact_historical_assistant_credentials()
        for message in messages:
            db.session.refresh(message)
            assert "OldTemp-391!" not in message.text
            assert "OldReset,Secret-882!" not in message.text
            if message.title:
                assert "OldTemp-391!" not in message.title
        assert Lookup.query.filter_by(kind="system_migration", name=migration_key).first() is not None


def test_local_password_reset_intent_keeps_target_but_never_carries_supplied_password():
    from employee_movements.assistant.intents import parse_intent

    parsed = parse_intent('غيّر كلمة المرور للحساب أحمد علي إلى NeverShare-981!')

    assert parsed.get('intent') == 'user_password_reset'
    assert parsed.get('employee_name') == 'أحمد علي'
    assert 'password' not in parsed
    assert 'NeverShare-981!' not in str(parsed)
