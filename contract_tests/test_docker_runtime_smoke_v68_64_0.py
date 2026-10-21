from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()


def read(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def test_ci_runs_production_container_against_postgres_and_checks_readiness():
    workflow = read(".github/workflows/ci.yml")
    assert "Smoke-test production image with PostgreSQL and local OCR" in workflow
    assert "python-version: '3.12'" in workflow
    assert "docker run --detach --name emc-smoke-db" in workflow
    assert "docker run --detach --name emc-smoke-app" in workflow
    assert "curl --silent --show-error --fail http://127.0.0.1:8000/healthz" in workflow
    assert "DOCKER_POSTGRES_HEALTH=OK" in workflow
    assert "DOCKER_LOGIN_PAGE=OK" in workflow
    assert "docker exec emc-smoke-app python scripts/check_ticket_ocr_runtime.py" in workflow
    assert "expected_version = Path('VERSION.md').read_text(encoding='utf-8').strip()" in workflow


def test_local_ocr_runtime_smoke_checks_both_languages_and_schema():
    script = read("scripts/check_ticket_ocr_runtime.py")
    dockerfile = read("Dockerfile")
    assert '"tesseract", "--list-langs"' in script
    assert '{"ara", "eng"}' in script
    assert "extract_ticket_fields(Image.new(\"RGB\", (1200, 800), \"white\"))" in script
    assert '"from_date"' in script and '"to_date"' in script
    assert "tesseract-ocr-ara" in dockerfile
    assert "tesseract-ocr-eng" in dockerfile


def test_current_release_metadata_is_unified():
    version = read("VERSION.md").strip()
    assert version == CURRENT_VERSION
    assert f'version = "{version}"' in read("pyproject.toml")
    assert f"__version__ = '{version}'" in read("employee_movements/__init__.py")
    assert 'data-app-version="{{app_version}}"' in read("employee_movements/templates/base.html")


def test_docker_build_context_excludes_contract_tests_and_review_documents():
    dockerignore = read(".dockerignore")
    assert "contract_tests/" in dockerignore
    assert "*.md" in dockerignore
    assert "!VERSION.md" in dockerignore
    assert "REVIEW_MANIFEST*.json" in dockerignore
    assert ".env.example" in dockerignore
