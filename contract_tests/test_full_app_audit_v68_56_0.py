"""Regression contracts for full-application audit fixes in v68.56.0."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MISSIONS = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
CONSTANTS = (ROOT / "employee_movements" / "constants.py").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
GUNICORN = (ROOT / "gunicorn.conf.py").read_text(encoding="utf-8")
MODEL_SOURCE = (ROOT / "employee_movements" / "models.py").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "employee_movements" / "bootstrap.py").read_text(encoding="utf-8")
ENV_EXAMPLE = ROOT / ".env.example"
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _block(source: str, start: str, end: str) -> str:
    start_index = source.index(start)
    end_index = source.index(end, start_index + len(start))
    return source[start_index:end_index]


def test_closed_mission_ticket_attachment_has_manager_exception_but_keeps_source_scope():
    route = _block(
        MISSIONS,
        "def mission_ticket_image_save(movement_id):",
        "def _mission_center_return_url",
    )
    assert "if movement_is_closed(m):" in route
    assert "'Manager Application Support' not in roles()" in route
    assert "not branch_ok(m.employee.branch_id)" in route
    assert "elif not can_manage_movement(m):" in route


def test_ticket_image_database_errors_do_not_log_exception_tracebacks_or_blob_values():
    route = _block(
        MISSIONS,
        "def mission_ticket_image_save(movement_id):",
        "def _mission_center_return_url",
    )
    assert "current_app.logger.error(" in route
    assert "type(exc).__name__" in route
    assert "current_app.logger.exception" not in route


def test_closed_mission_requests_are_operational_scope_endpoints():
    for endpoint in (
        "missions.mission_edit_request_create",
        "missions.mission_edit_requests",
        "missions.mission_edit_request_review",
        "missions.mission_edit_request_save",
        "missions.mission_ticket_image_save",
    ):
        assert f"'{endpoint}'" in CONSTANTS
    create = _block(
        MISSIONS,
        "def mission_edit_request_create(",
        "@bp.get('/reports/assignments/edit-requests')",
    )
    queue = _block(
        MISSIONS,
        "def mission_edit_requests():",
        "@bp.get('/reports/assignments/edit-requests/<int:request_id>')",
    )
    review = _block(
        MISSIONS,
        "def mission_edit_request_review(",
        "@bp.post('/reports/assignments/edit-requests/<int:request_id>')",
    )
    save = _block(
        MISSIONS,
        "def mission_edit_request_save(",
        "@bp.get('/reports/assignments/export.xlsx')",
    )
    assert "not branch_ok(m.employee.branch_id)" in create
    assert "if not scope_governorate_id():" in queue
    assert "scoped_branch_ids = set(bids())" in queue
    assert "not branch_ok(r.movement.employee.branch_id)" in review
    assert "not scope_governorate_id()" in save
    assert "not branch_ok(m.employee.branch_id)" in save


def test_gunicorn_preload_drops_inherited_sqlalchemy_pool_after_fork():
    assert "--config gunicorn.conf.py --preload" in DOCKERFILE
    assert "EXPOSE 8000" in DOCKERFILE
    assert "def post_worker_init(worker):" in GUNICORN
    assert "db.engine.dispose(close=False)" in GUNICORN


def test_movement_model_does_not_repeat_modified_at_column():
    model = MODEL_SOURCE.split("class Movement(", 1)[1].split("\nclass ", 1)[0]
    assert model.count("modified_at = db.Column") == 1


def test_ci_runs_static_workflow_and_ui_security_contract_checks():
    assert "python scripts/check_home_workflow_contracts.py" in CI
    assert "python scripts/check_ui_integrity.py" in CI
    assert "python scripts/check_post_route_security.py" in CI


def test_legacy_status_and_first_entry_role_migrations_are_versioned_one_time_migrations():
    normalize = _block(BOOTSTRAP, "def _normalize_legacy_movements():", "def _link_entry_accounts_to_employees():")
    retire = _block(BOOTSTRAP, "def _remove_legacy_entry_login_roles():", "def _cleanup_expired_mission_ticket_image_drafts():")
    assert "migration:normalize-legacy-movement-states-v68.56.0" in normalize
    assert "if _migration_done(migration_key):" in normalize
    assert "_mark_migration(migration_key)" in normalize
    assert "migration:retire-first-entry-login-role-v68.56.0" in retire
    assert "if _migration_done(migration_key):" in retire
    assert "_mark_migration(migration_key)" in retire
    assert "EntryAssignment/EntryAssignmentBranch rows are intentionally" in retire


def test_deployment_guides_have_a_real_secret_free_env_example():
    assert ENV_EXAMPLE.is_file()
    example = ENV_EXAMPLE.read_text(encoding="utf-8")
    for key in ("POSTGRES_PASSWORD=", "SECRET_KEY=", "ADMIN_PASSWORD=", "COOKIE_SECURE=1", "DOMAIN="):
        assert key in example
    assert "REPLACE_WITH" in example
    assert "GEMINI_MODEL=gemini-3.8-flash" in example


def test_accessible_names_exist_for_search_assistant_and_rehire_controls():
    dock = (ROOT / "employee_movements" / "templates" / "assistant_dock.html").read_text(encoding="utf-8")
    profile = (ROOT / "employee_movements" / "templates" / "employee.html").read_text(encoding="utf-8")
    embed = (ROOT / "employee_movements" / "templates" / "assistant_embed.html").read_text(encoding="utf-8")
    assistant = (ROOT / "employee_movements" / "templates" / "assistant.html").read_text(encoding="utf-8")
    resigned = (ROOT / "employee_movements" / "templates" / "employee_resigned.html").read_text(encoding="utf-8")
    assert 'aria-label="اكتب طلبك للمساعد الذكي"' in dock
    assert 'aria-label="البحث في سجل حركات الموظف"' in profile
    assert 'aria-label="رسالة للمساعد الذكي"' in embed
    assert 'aria-label="رسالة للمساعد الذكي"' in assistant
    assert 'aria-label="تاريخ إعادة التعيين"' in resigned


def test_report_filters_movement_governorate_entry_replacement_and_delegation_reason_are_labeled():
    templates = ROOT / "employee_movements" / "templates"
    report = (templates / "employee_type_report.html").read_text(encoding="utf-8")
    movements_page = (templates / "movements.html").read_text(encoding="utf-8")
    home = (templates / "home.html").read_text(encoding="utf-8")
    delegations = (templates / "delegations.html").read_text(encoding="utf-8")
    assert '<label for="reportStatus">الحالة</label><select id="reportStatus"' in report
    assert '<label for="reportDateFrom">من يوم</label><input id="reportDateFrom"' in report
    assert '<label for="reportDateTo">إلى يوم</label><input id="reportDateTo"' in report
    assert 'id="movementCreateGovernorate" class="movement-hierarchy-select" aria-label="اختر محافظة الموظف"' in movements_page
    assert 'name="new_entry_employee_id" required aria-label="اختر البديل لمسؤول إدخال الفروع"' in home
    assert 'name="reason" required minlength="3" placeholder="سبب الإلغاء" aria-label="سبب إلغاء التفويض"' in delegations
