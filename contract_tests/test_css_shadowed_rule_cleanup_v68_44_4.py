from pathlib import Path

from scripts.audit_css_shadowing import CSS_ROOT, audit_tree


def test_shared_and_page_stylesheets_are_covered_by_shadowing_audit():
    css_files = {path.relative_to(CSS_ROOT).as_posix() for path in CSS_ROOT.rglob("*.css")}
    assert {"app.css", "design-system-cyan.css", "pages/home.css", "pages/employee-directory.css", "pages/movement-forms.css"} <= css_files


def test_no_fully_shadowed_same_selector_rules_remain():
    """Guard against reintroducing exact-context rules wholly overridden later."""
    assert audit_tree() == []


def test_reported_clean_release_version_is_synchronized():
    root = Path(__file__).resolve().parents[1]
    version = (root / "VERSION.md").read_text(encoding="utf-8").strip()
    base = (root / "employee_movements/templates/base.html").read_text(encoding="utf-8")
    assert version == "68.49.0"
    assert base.count(f"v={version}") == 21
    assert f'data-app-version="{version}"' in base
