# Page stylesheet map — v68.48.0

The shared layout loads styles in this order, with route-scoped files selected by `employee_movements/templates/base.html`:

1. `css/app.css` — shared foundation.
2. `css/pages/workspace-pages.css` — shared workspace patterns on eligible paths.
3. `css/design-system-cyan.css` — unified visual tokens/components.
4. `css/pages/admin-reports-assistant.css` — administration/report/manager/audit refinements on applicable paths.
5. `css/pages/assistant-dock.css` — authenticated assistant dock; assistant chat page styling.
6. `css/navigation-color-system.css` — stronger navy sidebar and semantic navigation icon colors.

## Page coverage in this release

| Page pattern | Main template | Primary style coverage |
|---|---|---|
| Reports & missions overview | `reports_missions.html` | `admin-reports-assistant.css`, shared workspace + navigation |
| Report catalogue | `reports.html` | `admin-reports-assistant.css`, shared workspace + navigation |
| Mission reports | `mission_reports.html` | `admin-reports-assistant.css`, shared workspace + navigation |
| Manager workspace | `manager_hub.html` | `admin-reports-assistant.css`, shared workspace + navigation |
| Assistant chat | `assistant.html` | `assistant-dock.css`, shared workspace + navigation |
| Assistant dock | `assistant_dock.html` included by base | `assistant-dock.css`, shared workspace + navigation |

Routing, permissions, scope logic and database behavior are outside this stylesheet map and were not intentionally modified in this release.
