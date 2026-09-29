# v36.37 — Enterprise Design Foundation

## What changed
- Reworked the global visual layer into a unified enterprise/SaaS design system.
- Redesigned the application header, role switcher, account/logout actions and sticky navigation.
- Redesigned the operational-scope banner without changing scope logic.
- Redesigned the home dashboard shell, search area, status widgets, cards, filters and empty scope state.
- Refined form controls, tables, buttons, badges, spacing, shadows and responsive behavior.
- Refined the floating AI assistant shell so it visually belongs to the same product.
- Removed the page-local home style block so the home page now inherits the central design system.

## Business logic preserved
- v36.36 scope isolation is preserved.
- Selecting an operational governorate does not itself search/list employees.
- Home employee search remains global.
- App Administrator/Manager operational scope behavior remains unchanged.
- No database schema or route changes were intentionally introduced.

## Validation
- Python syntax compilation: passed.
- Jinja template parsing: passed for all templates.
- Runtime Flask smoke test was not executed because the execution environment does not have Flask installed.
