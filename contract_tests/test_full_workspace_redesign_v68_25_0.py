from pathlib import Path
import re

import tinycss2

ROOT = Path(__file__).parents[1]
BASE = (ROOT / 'employee_movements/templates/base.html').read_text(encoding='utf-8')
CSS = (ROOT / 'employee_movements/static/css/pages/workspace-pages.css').read_text(encoding='utf-8')
APP_CSS = (ROOT / 'employee_movements/static/css/app.css').read_text(encoding='utf-8')


def test_workspace_stylesheet_is_present_versioned_and_scoped_to_remaining_pages():
    assert (ROOT / 'employee_movements/static/css/pages/workspace-pages.css').is_file()
    assert "filename='css/pages/workspace-pages.css'" in BASE
    assert "request.path.startswith('/branches')" in BASE
    assert "request.path.startswith('/reports-missions')" in BASE
    assert "request.path.startswith('/notifications')" in BASE
    current_version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    assert "v=app_version" in BASE
    # The movement editor/review pages retain their purpose-built form stylesheet.
    assert "not request.path.startswith('/reports/assignments/mission-edit')" in BASE
    assert "not request.path.startswith('/reports/assignments/edit-requests')" in BASE


def test_report_workspaces_have_explicit_layouts_instead_of_unstyled_class_hooks():
    for selector in (
        '.smart-report-metrics', '.smart-report-command-grid', '.smart-report-live-grid',
        '.smart-report-metric', '.smart-report-actions', '.smart-report-attention-item',
        '.smart-report-note', '.interactive-notification-metrics',
        '.interactive-notification-item', '.interactive-notification-actions',
    ):
        assert selector in CSS


def test_catalog_import_account_and_employee_detail_pages_are_scoped():
    for selector in (
        'body[data-workspace-path^="/branches"]',
        'body[data-workspace-path^="/governorates"]',
        'body[data-workspace-path^="/lookups"]',
        'body[data-workspace-path^="/excel-import"]',
        'body[data-workspace-path^="/change-password"]',
        'body[data-workspace-path^="/employee/"]',
        'body[data-workspace-path^="/employees/"]',
        'body[data-workspace-path^="/replacement"]',
    ):
        assert selector in CSS


def test_responsive_rules_cover_report_cards_manager_grid_and_notification_actions():
    for bp in ('@media (max-width: 1180px)', '@media (max-width: 850px)', '@media (max-width: 620px)', '@media (prefers-reduced-motion: reduce)'):
        assert bp in CSS
    assert '.smart-report-metrics,.smart-report-live-grid,.smart-report-actions' in CSS
    assert '.interactive-notification-actions a { width: 100%; }' in CSS


def test_new_workspace_css_parses_recursively_without_css_syntax_errors():
    rules = tinycss2.parse_stylesheet(CSS, skip_whitespace=False, skip_comments=False)
    assert not [rule for rule in rules if rule.type == 'error']
    pending = list(rules)
    while pending:
        rule = pending.pop()
        if rule.type == 'at-rule' and rule.content is not None:
            nested = tinycss2.parse_rule_list(rule.content, skip_whitespace=False, skip_comments=False)
            assert not [item for item in nested if item.type == 'error']
            pending.extend(nested)
    assert re.search(r'\{[^{}]*\}', CSS, re.S)


def test_current_release_and_asset_cache_tags_are_synchronized():
    version = (ROOT / 'VERSION.md').read_text(encoding='utf-8').strip()
    init = (ROOT / 'employee_movements/__init__.py').read_text(encoding='utf-8')
    project = (ROOT / 'pyproject.toml').read_text(encoding='utf-8')
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    assert f"__version__ = '{version}'" in init
    assert f'version = "{version}"' in project
    assert BASE.count("v=app_version") == 24
    assert f'v{version}' in APP_CSS.splitlines()[1]
