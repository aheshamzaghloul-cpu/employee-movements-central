from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()


def read(path):
    return (ROOT / path).read_text(encoding='utf-8')


def test_release_version_is_unified():
    assert read('VERSION.md').strip() == CURRENT_VERSION
    assert f'version = "{CURRENT_VERSION}"' in read('pyproject.toml')
    assert f"__version__ = '{CURRENT_VERSION}'" in read('employee_movements/__init__.py')
    assert 'data-app-version="{{app_version}}"' in read('employee_movements/templates/base.html')


def test_redis_limiter_is_optional_and_shared_when_configured():
    limiter = read('employee_movements/ratelimit.py')
    assert 'redis_url=None' in limiter
    assert "redis.call('ZADD', key, now, member)" in limiter
    assert "redis.call('ZREMRANGEBYSCORE'" in limiter
    assert 'per-process fallback' in limiter
    assert 'test_redis_backend_uses_hashed_keys_and_atomic_scripts' in read('tests/test_ratelimit.py')
    assert "'REDIS_URL': os.getenv('REDIS_URL', '').strip()" in read('employee_movements/config.py')


def test_csp_report_only_is_non_enforcing_and_sanitized():
    hooks = read('employee_movements/hooks.py')
    assert "'Content-Security-Policy-Report-Only'" in hooks
    assert 'report-uri /csp-report' in hooks
    assert "request.endpoint == 'security_csp_report'" in hooks
    assert "limit = 32 * 1024" in hooks
    assert "logger.info('CSP violation reported:" in hooks
    assert "'Content-Security-Policy'" in hooks


def test_ci_runs_real_postgresql_before_docker_build():
    ci = read('.github/workflows/ci.yml')
    assert 'image: postgres:17' in ci
    assert 'POSTGRES_TEST_URL:' in ci
    assert 'python -m pytest -q tests' in ci
    assert 'docker build --pull' in ci
    assert ci.index('needs: test') < len(ci)
    assert 'POSTGRES_TEST_URL' in read('tests/test_postgresql_bootstrap_smoke.py')


def test_backup_restore_verify_custom_archive_and_legacy_path():
    backup = read('scripts/backup.sh')
    restore = read('scripts/restore.sh')
    assert '--format=custom' in backup
    assert 'pg_restore --list' in backup
    assert 'sha256sum' in backup
    assert '--single-transaction' in restore
    assert 'sha256sum --check --status' in restore
    assert '*.sql.gz' in restore
    assert 'ON_ERROR_STOP=1' in restore


def test_accessibility_and_operations_documented():
    assert Path(ROOT / 'docs/RELEASE_RUNBOOK_v68.65.0_AR.md').exists()
    assert 'prefers-reduced-motion' in read('employee_movements/static/css/design-system-cyan.css')
    assert 'ACCESSIBILITY_CONTRACTS=OK' in read('scripts/check_accessibility_contracts.py')
    assert 'SLOW_REQUEST_LOG_MS' in read('employee_movements/config.py')
    assert 'test_csp_report_does_not_log_query_strings' in read('tests/test_csp_reporting.py')
