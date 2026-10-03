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

legacy = re.compile(r'(?:\bds-[\w-]+|\bv5[0-9]-[\w-]+|[\w-]+-v5[0-9])')
forbidden = ('directActionModal','directActionOpen','directActionClose','directActionSearch','ui-direct-modal','ui-direct-panel')
errors=[]
for p,s in texts:
    if legacy.search(s): errors.append(f'legacy token: {p}')
    for token in forbidden:
        if token in s: errors.append(f'forbidden component {token}: {p}')

css_files=list(CSS_DIR.glob('*.css'))
if css_files != [CSS_DIR/'app.css']:
    errors.append(f'expected one CSS entrypoint, found: {[p.name for p in css_files]}')
css=(CSS_DIR/'app.css').read_text(encoding='utf-8')
if css.count('{') != css.count('}'):
    errors.append('CSS braces are unbalanced')
if css.count('(') != css.count(')'):
    errors.append('CSS parentheses are unbalanced')

print(f'templates={len(list(TEMPLATES.rglob("*.html")))} css_files={len(css_files)} js_files={len(list(JS_DIR.glob("*.js")))}')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print('UI_INTEGRITY=OK')
