from pathlib import Path


def test_page_styles_load_before_shared_design_layers():
    base = Path(__file__).parents[1] / "employee_movements" / "templates" / "base.html"
    source = base.read_text(encoding="utf-8")
    page_style = source.index("css/pages/operational-pages.css")
    design = source.index("css/design-system-cyan.css")
    navigation = source.index("css/navigation-color-system.css")
    components = source.index("css/ui-components.css")
    admin_polish = source.index("css/pages/admin-reports-assistant.css")
    home_polish = source.index("css/pages/home-journey.css")
    assistant_polish = source.index("css/pages/assistant-dock.css")
    secondary_polish = source.index("css/pages/secondary-workspaces.css")
    assert page_style < design < admin_polish < home_polish < assistant_polish < navigation < secondary_polish < components
    assert source.count("v=app_version") == 24


def test_sidebar_and_permission_context_remain_in_base_shell():
    base = Path(__file__).parents[1] / "employee_movements" / "templates" / "base.html"
    source = base.read_text(encoding="utf-8")
    assert 'id="appSidebar"' in source
    assert 'aria-label="القائمة الرئيسية"' in source
    assert "scope_required" in source
    assert "active_role" in source
