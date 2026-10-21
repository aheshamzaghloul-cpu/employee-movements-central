"""Source-only regression guards for the Executive Workspace CSS cleanup."""
from pathlib import Path
import re
import tinycss2

from dedupe_css_selectors import decl_signature
from scripts.audit_css_shadowing import audit_tree

ROOT = Path(__file__).resolve().parents[1]


def test_no_fully_shadowed_exact_selector_rules_remain():
    assert audit_tree() == []


def test_sidebar_muted_label_uses_high_contrast_color():
    css = (ROOT / "employee_movements/static/css/navigation-color-system.css").read_text(encoding="utf-8")
    assert ".premium-sidebar .premium-side-user small { color: #a9c8cb !important; }" in css


def test_css_custom_property_names_keep_case_sensitivity_in_cleanup_signature():
    rule = tinycss2.parse_rule_list(":root { --Brand: #111111; --brand: #222222; }", skip_whitespace=True)[0]
    names = [name for name, _, _ in decl_signature(rule)]
    assert names == ["--Brand", "--brand"]


def test_asset_cache_buster_uses_the_updated_patch_version():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    package = __import__("tomllib").loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    init = (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    match = re.search(r"(?m)^__version__\s*=\s*['\"]([^'\"]+)['\"]", init)
    assert match, "employee_movements.__version__ must be a literal version marker"
    assert version == package["project"]["version"] == match.group(1)
