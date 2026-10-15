from pathlib import Path

ROOT = Path(__file__).parents[1]
CSS = (ROOT / 'employee_movements/static/css/app.css').read_text(encoding='utf-8')
BASE = (ROOT / 'employee_movements/templates/base.html').read_text(encoding='utf-8')


def test_cyan_visual_tokens_are_the_authoritative_shared_palette():
    # Design tokens now have one canonical root; do not depend on an old version comment.
    start = CSS.index(':root {')
    end = CSS.index('}', start)
    tokens = CSS[start:end]
    assert CSS.count('\n:root {') == 1
    assert '--ui-brand: #147cad' in tokens
    assert '--ui-brand-2: #268fca' in tokens
    assert '--ui-brand-strong: #126c9b' in tokens
    assert '--ui-page: #f6faff' in tokens
    assert '--ui-line: #dce8f2' in tokens
    assert '--ui-space-4: 16px' in tokens
    assert '--ui-type-base: 15.5px' in tokens
    assert '--ui-control-md: 44px' in tokens


def test_card_components_are_not_individually_centered_to_a_fixed_content_width():
    # Cards in grids must stretch to their grid tracks, rather than shrink and be centered.
    shell_start = CSS.index('.ui-shell > .premium-main.with-shell > *')
    original_shell_rule = CSS[shell_start:CSS.index('}', shell_start)]
    assert '.ui-card' not in original_shell_rule
    assert '.home-workspace-card' not in original_shell_rule
    assert '.home-section' not in original_shell_rule


def test_shared_design_covers_shell_admin_forms_tables_and_mobile():
    required = [
        '.premium-sidebar .premium-nav a.active',
        '.premium-topbar',
        '.admin-ai-hero',
        '.smart-home-head',
        'input:not([type="checkbox"]):not([type="radio"]), select, textarea',
        '.ui-table-wrap td',
        '@media (max-width: 600px)',
        '@media (prefers-reduced-motion: reduce)',
    ]
    for selector in required:
        assert selector in CSS


def test_admin_contextual_assistant_buttons_do_not_use_browser_default_styling():
    rule = CSS[CSS.index('.admin-ai-signal-actions .admin-basyouni-link {'):CSS.index('}', CSS.index('.admin-ai-signal-actions .admin-basyouni-link {'))]
    assert 'appearance: none' in rule
    assert 'border-radius: 9px' in rule
    assert 'font: inherit' in rule
    assert ':focus-visible' in CSS


def test_cache_busting_is_synchronized_for_the_shared_stylesheet_and_scripts():
    version = (ROOT / 'VERSION.md').read_text(encoding='utf-8').strip()
    assert BASE.count(f'v={version}') == 21
    for stale_version in ('68.22.57', '68.22.56', '68.22.55', '68.22.54', '68.22.52', '68.22.51', '68.22.50'):
        if stale_version != version:
            assert f'v={stale_version}' not in BASE
