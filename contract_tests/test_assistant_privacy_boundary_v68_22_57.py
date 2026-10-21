from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_both_gemini_paths_sanitize_user_authored_context_and_restore_locally():
    agent = (ROOT / "employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    llm = (ROOT / "employee_movements/assistant/llm.py").read_text(encoding="utf-8")
    assert "sanitize_conversation_for_model(prior_chat, prompt)" in agent
    assert "sanitize_conversation_for_model(chat, text)" in llm
    assert "restore_local_tokens(call.get(\"args\") or {}, local_token_map)" in agent
    assert "restore_local_tokens(parsed, local_token_map)" in llm
    assert "do not append function responses" in agent and "make a second Gemini request" in agent


def test_persisted_chat_redacts_credentials_before_insert():
    routes = (ROOT / "employee_movements/assistant/routes.py").read_text(encoding="utf-8")
    privacy = (ROOT / "employee_movements/assistant/privacy.py").read_text(encoding="utf-8")
    save = routes[routes.index("def _save_chat_message"):routes.index("def _trim_chat")]
    assert "redact_secrets_for_storage(text)" in save
    assert "safe_text[:MAX_HISTORY_TEXT_CHARS]" in save
    assert "_SECRET_ASSIGNMENT_RE" in privacy
    assert "_UNDDELIMITED_SECRET_RE" in privacy
    assert "_GOOGLE_API_KEY_RE" in privacy
    assert "_BEARER_RE" in privacy


def test_ci_test_discovery_includes_both_test_suites():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'testpaths = ["tests", "contract_tests"]' in pyproject
    assert "run: python -m pytest -q tests" in workflow
    assert "run: python -m pytest -q contract_tests" in workflow
    assert (ROOT / "contract_tests/__init__.py").exists()


def test_external_workspace_context_is_an_allowlist_not_dynamic_page_text():
    agent = (ROOT / "employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    block = agent[agent.index("model_context = {"):agent.index("system = SYSTEM", agent.index("model_context = {"))]
    assert '"page": safe_page' in block
    assert '"selected": {' in block
    assert '"path": context.get("path")' not in block
    assert '"title": context.get("title")' not in block
    assert '"heading": context.get("heading")' not in block
    assert '"hash": context.get("hash")' not in block
    assert 'page = PAGE_NAMES.get(path, "التطبيق")' in agent


def test_gemini_http_error_logs_do_not_include_response_body():
    llm = (ROOT / "employee_movements/assistant/llm.py").read_text(encoding="utf-8")
    http_error = llm[llm.index("except urllib.error.HTTPError"):llm.index("except (urllib.error.URLError", llm.index("except urllib.error.HTTPError"))]
    assert "exc.read()" not in http_error
    assert "body or exc" not in http_error
    assert "Gemini intent request failed with HTTP status %s" in http_error


def test_unused_workspace_context_helper_is_safe_if_reintroduced():
    agent = (ROOT / "employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    helper = agent[agent.index("def _tool_context_text"):agent.index("def tool_execute", agent.index("def _tool_context_text"))]
    assert '"current_page": page' in helper
    assert '"path": ctx.get("path")' not in helper
    assert '"heading": ctx.get("heading")' not in helper
    assert '"hash": ctx.get("hash")' not in helper
    assert '"scope_governorate_id": ctx.get("scope_governorate_id")' not in helper


def test_new_person_names_can_be_redacted_before_local_record_creation():
    privacy = (ROOT / "employee_movements/assistant/privacy.py").read_text(encoding="utf-8")
    assert "_PERSON_LABEL_RE" in privacy
    assert "_explicit_person_values(secret_cleaned)" in privacy
    assert "including not-yet-created people" in privacy


def test_agent_cannot_receive_or_forward_model_supplied_passwords():
    agent = (ROOT / "employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    preparation = (ROOT / "employee_movements/assistant/action_preparation.py").read_text(encoding="utf-8")
    llm = (ROOT / "employee_movements/assistant/llm.py").read_text(encoding="utf-8")
    manager = (ROOT / "employee_movements/assistant/manager.py").read_text(encoding="utf-8")
    planning = (ROOT / "employee_movements/assistant/manager_plan_users.py").read_text(encoding="utf-8")
    tool_schemas = (ROOT / "employee_movements/assistant/tool_schemas.py").read_text(encoding="utf-8")
    prepare_schema = tool_schemas[tool_schemas.index('"name": "prepare_action"'):tool_schemas.index('"name": "navigate_to"')]
    assert '"password"' not in prepare_schema
    assert 'normalized.pop("password", None)' in preparation
    assert "return _prepare_action_impl(args, ctx)" in agent
    assert "'password': {'type': ['string', 'null']}" not in llm
    assert "'job_code', 'password', 'roles'" not in llm
    assert "password = a.get('password')" not in manager
    assert 'سيُولّد النظام كلمة مرور مؤقتة' in planning


def test_reset_password_suffix_is_redacted_before_external_calls_and_storage():
    privacy = (ROOT / "employee_movements/assistant/privacy.py").read_text(encoding="utf-8")
    assert "_RESET_PASSWORD_TAIL_RE" in privacy
    assert "_RESET_PASSWORD_TAIL_RE.sub" in privacy
    assert "غيّر كلمة المرور" in privacy or "غير|تغيير" in privacy


def test_prior_assistant_turns_are_sanitized_defensively():
    privacy = (ROOT / "employee_movements/assistant/privacy.py").read_text(encoding="utf-8")
    assert 'item.get("role") in {"user", "assistant"}' in privacy
    assert 'clone.get("role") in {"user", "assistant"}' in privacy


def test_both_gemini_clients_avoid_logging_provider_error_payloads():
    agent = (ROOT / "employee_movements/assistant/agent.py").read_text(encoding="utf-8")
    llm = (ROOT / "employee_movements/assistant/llm.py").read_text(encoding="utf-8")
    assert 'logger.warning("Gemini agent request failed with HTTP status %s", exc.code)' in agent
    assert 'logger.warning("Gemini agent request failed (%s)", type(exc).__name__)' in agent
    assert "logger.warning('Gemini intent request failed with HTTP status %s', exc.code)" in llm
    assert "body or exc" not in agent and "exc.read()" not in agent


def test_historical_chat_redaction_migration_is_idempotently_registered_at_startup():
    bootstrap = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")
    assert "migration:assistant-chat-credential-redaction-v68.22.58" in bootstrap
    assert "def _redact_historical_assistant_credentials()" in bootstrap
    init = bootstrap[bootstrap.index("def init_database(app):"):]
    assert "_redact_historical_assistant_credentials()" in init
    migration = bootstrap[bootstrap.index("def _redact_historical_assistant_credentials()"):bootstrap.index("def _ensure_role")]
    assert "AssistantMessage.query" in migration
    assert "redact_secrets_for_storage" in migration
    assert "_migration_done(migration_key)" in migration
