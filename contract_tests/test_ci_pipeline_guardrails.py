"""Keep release CI least-privileged and bounded in duration."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_github_actions_ci_has_read_only_repository_permissions():
    assert "permissions:\n  contents: read" in WORKFLOW
    assert "permissions: write-all" not in WORKFLOW


def test_ci_jobs_have_explicit_timeouts():
    assert "  test:\n    runs-on: ubuntu-latest\n    timeout-minutes: 40" in WORKFLOW
    assert "  docker:\n    runs-on: ubuntu-latest\n    timeout-minutes: 35" in WORKFLOW


def test_mission_pdf_runtime_smoke_is_still_part_of_docker_gate():
    assert "Smoke-test production image with PostgreSQL and local OCR" in WORKFLOW
    assert "python scripts/check_mission_center_runtime.py" in WORKFLOW


def test_runtime_dependencies_are_checked_for_conflicts_and_known_vulnerabilities():
    assert "python -m pip check" in WORKFLOW
    assert "pip-audit -r requirements.txt" in WORKFLOW
    assert "pip-audit==2.10.1" in (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
