import json
from pathlib import Path

from scripts.cleanup_cross_stylesheet_shadow_v68_44_6 import (
    CANONICAL,
    REPORT,
    SOURCES,
    canonical_index,
    plan,
)

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")


def test_all_route_stylesheets_load_before_the_global_canonical_design_system():
    assert BASE.index("css/app.css") < BASE.index("css/design-system-cyan.css")
    assert BASE.index("css/pages/home.css") < BASE.index("css/design-system-cyan.css")
    assert BASE.index("css/pages/employee-directory.css") < BASE.index("css/design-system-cyan.css")
    assert BASE.index("css/pages/movement-forms.css") < BASE.index("css/design-system-cyan.css")
    assert BASE.index("css/pages/management.css") < BASE.index("css/design-system-cyan.css")
    assert BASE.index("css/pages/workspace-pages.css") < BASE.index("css/design-system-cyan.css")
    assert BASE.index("css/design-system-cyan.css") < BASE.index("css/pages/admin-reports-assistant.css")
    assert BASE.index("css/design-system-cyan.css") < BASE.index("css/pages/home-journey.css") < BASE.index("css/pages/assistant-dock.css")


def test_cross_stylesheet_cleanup_has_no_candidates_after_application():
    winners = canonical_index(CANONICAL)
    remaining = 0
    for source in SOURCES:
        _, notes = plan(source, winners)
        remaining += len(notes)
    assert remaining == 0


def test_applied_cross_stylesheet_audit_records_all_removed_declarations():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["count"] == 383
    assert sum(report["by_file"].values()) == 383
    assert report["canonical_file"].endswith("design-system-cyan.css")
    assert {Path(name).name for name in report["by_file"]} == {
        "app.css", "employee-directory.css", "home.css", "management.css", "movement-forms.css", "workspace-pages.css"
    }


def test_visual_comparison_report_is_pixel_identical_across_desktop_and_mobile():
    report_path = ROOT / "docs/design/CSS_VISUAL_DIFF_v68.44.6.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["before_screenshots"] == 78
    assert report["after_screenshots"] == 78
    assert report["changed_images_count"] == 0
    assert report["errors"] == 0
    assert report["overflows"] == 0
    assert report["viewport_widths"] == [1440, 390]


def test_version_and_asset_cache_busters_are_synchronized():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init_py = (ROOT / "employee_movements/__init__.py").read_text(encoding="utf-8")
    assert version == "68.49.0"
    assert 'version = "68.49.0"' in pyproject
    assert "__version__ = '68.49.0'" in init_py
    assert BASE.count("v=68.49.0") == 21
    assert 'data-app-version="68.49.0"' in BASE


def test_cross_stylesheet_tool_protects_context_priority_comments_and_fallbacks():
    tool = (ROOT / "scripts/cleanup_cross_stylesheet_shadow_v68_44_6.py").read_text(encoding="utf-8")
    assert "tuple(rule[\"ctx\"])" in tool
    assert "not sig[\"important\"] or w[\"important\"]" in tool
    assert "duplicate_in_rule" in tool
    assert "never used as global proof" in tool
