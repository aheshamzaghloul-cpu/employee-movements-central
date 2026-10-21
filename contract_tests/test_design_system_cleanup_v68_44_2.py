from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
CSS_ROOT = ROOT / "employee_movements/static/css"
APP = (CSS_ROOT / "app.css").read_text(encoding="utf-8")
THEME = (CSS_ROOT / "design-system-cyan.css").read_text(encoding="utf-8")
DOCK = (CSS_ROOT / "pages/assistant-dock.css").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")

def test_global_design_tokens_have_one_source_of_truth():
    assert len(re.findall(r"(?m)^:root\s*\{", APP)) == 1
    assert not re.search(r"(?m)^:root\s*\{", THEME)
    assert "--ui-brand: #147cad" in APP
    assert "--ui-brand-soft: #e8f5ff" in APP
    assert "--ui-content: 1580px" in APP
    assert "--ui-accent: #147cad" in APP

def test_legacy_turquoise_accents_are_removed_from_active_css():
    active = "\n".join(p.read_text(encoding="utf-8") for p in CSS_ROOT.rglob("*.css"))
    for stale in ("#087f8c", "rgba(8,127,140", "#49b8c2", "#0a8d99", "#066b77", "#078793", "#087783", "#087e95", "#e1f5f6", "#e6f8f9", "#0795a4", "#168aa3", "#0a9aa6", "#0b8b95", "#078894", "#0a737e", "#0b858f", "#066b76", "#cbe8eb", "#e4f7f8"):
        assert stale not in active.lower(), stale

def test_assistant_launcher_uses_the_scoped_visible_label_stylesheet():
    assert ".assistant-dock-trigger {" in DOCK
    assert "min-width: 132px !important" in DOCK
    assert ".assistant-dock-label" in DOCK
    assert "min-width:148px" not in APP and "min-width: 148px" not in APP
    assert "assistant-dock.css" in BASE

def test_cache_busters_and_application_version_match():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    assert version == CURRENT_VERSION
    assert BASE.count("v=app_version") == 24
    assert 'data-app-version="{{app_version}}"' in BASE
