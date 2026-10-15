from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'employee_movements' / 'templates'
STATIC = ROOT / 'employee_movements' / 'static'
CSS_DIR = STATIC / 'css'
JS_DIR = STATIC / 'js'

texts=[]
for p in list(TEMPLATES.rglob('*.html')) + list(CSS_DIR.glob('*.css')) + list(JS_DIR.glob('*.js')):
    texts.append((p, p.read_text(encoding='utf-8')))

# `ds-*` is the current scoped design-system namespace used by home/directory page CSS.
# Flag only stale version-stamped class names, not the active `ds-*` components.
legacy = re.compile(r'(?:\bv5[0-9]-[\w-]+|[\w-]+-v5[0-9])')
forbidden = ('directActionModal','directActionOpen','directActionClose','directActionSearch','ui-direct-modal','ui-direct-panel')
errors=[]
for p,s in texts:
    if legacy.search(s): errors.append(f'legacy token: {p}')
    for token in forbidden:
        if token in s: errors.append(f'forbidden component {token}: {p}')

css_entrypoints=list(CSS_DIR.glob('*.css'))
expected_entrypoints = {CSS_DIR/'app.css', CSS_DIR/'design-system-cyan.css', CSS_DIR/'navigation-color-system.css'}
if set(css_entrypoints) != expected_entrypoints:
    errors.append(f'expected app.css, design-system-cyan.css, and navigation-color-system.css, found: {[p.name for p in css_entrypoints]}')
css_files=list(CSS_DIR.rglob('*.css'))
for css_path in css_files:
    css=(css_path).read_text(encoding='utf-8')
    if css.count('{') != css.count('}'):
        errors.append(f'CSS braces are unbalanced: {css_path.relative_to(ROOT)}')
    if css.count('(') != css.count(')'):
        errors.append(f'CSS parentheses are unbalanced: {css_path.relative_to(ROOT)}')

print(f'templates={len(list(TEMPLATES.rglob("*.html")))} css_files={len(css_files)} js_files={len(list(JS_DIR.glob("*.js")))}')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print('UI_INTEGRITY=OK')
