# Reports, Missions and Assistant — Visual Review v68.48.0

## Design changes

- Report overview metrics use semantic, accessible icon tiles with distinct blue, teal, amber and violet category colors.
- Report/mission actions use specific visual categories for leave, assignment, permission, print and ticket-image intake.
- Report filters, attention cards, manager summary cards and audit-table headers use a clearer shared visual hierarchy.
- Assistant page and dock have a stronger navy-to-teal header, a visible assistant mark, clearer context chips, differentiated user/assistant bubbles, suggestion/action cards and a more prominent composer/send control.
- Responsive styles cover desktop (1440px), mobile (390px) and narrow mobile (360px); reduced-motion preferences are respected.

## Preview images

- Reports and missions overview: `preview-v68.48.0/reports-missions-desktop.png`, `reports-missions-mobile.png`, `reports-missions-narrow.png`.
- Report catalogue: `reports-catalog-desktop.png`, `reports-catalog-mobile.png`, `reports-catalog-narrow.png`.
- Mission reports: `mission-reports-desktop.png`, `mission-reports-mobile.png`, `mission-reports-narrow.png`.
- Manager workspace: `manager-desktop.png`, `manager-mobile.png`, `manager-narrow.png`.
- Assistant page: `assistant-desktop.png`, `assistant-mobile.png`, `assistant-narrow.png`.
- Assistant dock: `assistant-dock-desktop.png`, `assistant-dock-mobile.png`.

Full preview summary: `preview-v68.48.0/preview-summary.json`.

## Integrity notes

- Added semantic icon markup without changing route destinations or permission guards.
- Preserved report-scope guard, governorate selectors, CSV export, print routes and mission edit-request routes.
- Preserved assistant POST endpoints, confirmation and clear actions, CSRF input, and workspace context.
- Preview content is synthetic. It is not populated from the production database.
