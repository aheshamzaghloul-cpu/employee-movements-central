"""Keep unused-import checking enabled in both local and hosted validation."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ruff_unused_import_rule_is_not_globally_suppressed():
    config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'select = ["E9", "F"]' in config
    assert "ignore = []" in config
    assert "ruff check ." in workflow


def test_release_metadata_matches_the_single_current_version():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    package = (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    base = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert f'version = "{version}"' in project
    assert f"__version__ = '{version}'" in package
    assert 'data-app-version="{{app_version}}"' in base
    assert base.count("v=app_version") == 24
    assert "expected_version = Path('VERSION.md').read_text(encoding='utf-8').strip()" in workflow
