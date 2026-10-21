from pathlib import Path

ROOT = Path(__file__).parents[1]
CURRENT_VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
THEME = (ROOT / "employee_movements/static/css/design-system-cyan.css").read_text(encoding="utf-8")
TOKENS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "employee_movements/static/css/app.css").read_text(encoding="utf-8")


def test_shared_theme_is_loaded_after_every_conditional_page_stylesheet():
    assert "css/design-system-cyan.css" in BASE
    assert BASE.index("css/design-system-cyan.css") > BASE.index("css/pages/workspace-pages.css")
    assert BASE.count("v=app_version") == 24


def test_mission_from_screenshot_loads_workspace_page_styling():
    # This screen is a normal application workflow, not one of the two print-only documents.
    assert "request.path.startswith('/missions/')" in BASE
    assert ".ticket-image-dropzone" in THEME
    assert ".ticket-image-candidate:hover" in THEME


def test_old_component_aliases_resolve_to_the_premium_sky_blue_palette():
    for token, value in {
        "--accent: #147cad": "--accent: #147cad",
        "--accent-strong: #126c9b": "--accent-strong: #126c9b",
        "--ui-accent: #147cad": "--ui-accent: #147cad",
        "--ui-accent-soft: #e8f5ff": "--ui-accent-soft: #e8f5ff",
    }.items():
        assert value in TOKENS, token


def test_legacy_directory_admin_ticket_and_assistant_components_are_rethemed():
    required = [
        ".smart-employees-hero", ".smart-directory-gov-head", ".smart-branch-icon",
        ".users-choice-item:has(input:checked)", ".users-scope-picker",
        ".ticket-image-dropzone", ".ticket-image-candidate:hover",
        ".assistant-dock-trigger:hover", ".assistant-dock[data-open=\"1\"] .assistant-dock-trigger",
    ]
    for selector in required:
        assert selector in THEME, selector


def test_mission_printing_uses_one_official_pdf_flow():
    # Compatibility URLs delegate to the official PDF endpoint; there are no
    # separately-rendered mission papers that can drift from the canonical form.
    movement_routes = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    mission_routes = (ROOT / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    assignment_route = movement_routes.split("def assignment_form(", 1)[1].split("@bp.post('/movements/<int:i>/delete')", 1)[0]
    legacy_print_route = mission_routes.split("def mission_print(movement_id):", 1)[1]
    assert "url_for('missions.mission_pdf', movement_id=m.id)" in assignment_route
    assert "url_for('missions.mission_pdf', movement_id=m.id)" in legacy_print_route
    assert "assignment_form.html" not in movement_routes
    assert "mission_print.html" not in mission_routes
    assert "--ui-brand: #147cad" in APP_CSS


def test_all_interactive_page_templates_share_the_global_shell():
    templates_dir = ROOT / "employee_movements/templates"
    intentionally_standalone_or_partial = {
        "base.html",
        "assistant_dock.html",  # Included partial.
        "assistant_panel.html",  # Included partial.
        "home_global_search.html",  # Included partial.
        "workspace_actions.html",  # Included partial.
        "partials/movement_actions.html",  # Included partial.
    }
    html_files = list(templates_dir.rglob("*.html"))
    for template in html_files:
        rel = template.relative_to(templates_dir).as_posix()
        source = template.read_text(encoding="utf-8")
        if rel in intentionally_standalone_or_partial:
            continue
        assert "extends 'base.html'" in source or 'extends "base.html"' in source, rel
    assert len(html_files) == 45
