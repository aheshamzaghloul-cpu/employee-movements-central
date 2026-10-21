"""Lightweight accessibility guardrails for the shared app shell and styles."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = (ROOT / 'employee_movements/templates/base.html').read_text(encoding='utf-8')
CSS = '\n'.join(p.read_text(encoding='utf-8') for p in (ROOT / 'employee_movements/static/css').rglob('*.css'))
errors = []
if '<html lang="ar" dir="rtl">' not in BASE:
    errors.append('Shared shell must declare Arabic language and RTL direction.')
if 'class="skip-link"' not in BASE or 'href="#main"' not in BASE:
    errors.append('Shared shell must retain a keyboard skip link to main content.')
if ':focus-visible' not in CSS:
    errors.append('Visible keyboard focus (:focus-visible) styles are missing.')
if 'prefers-reduced-motion' not in CSS:
    errors.append('Reduced-motion preference handling is missing.')
if 'aria-label="القائمة الرئيسية"' not in BASE:
    errors.append('Main navigation needs an accessible label.')
if errors:
    print('\n'.join(errors))
    raise SystemExit(1)
print('ACCESSIBILITY_CONTRACTS=OK')
print('Checks: lang/dir, skip link, keyboard focus, reduced motion, navigation label')
