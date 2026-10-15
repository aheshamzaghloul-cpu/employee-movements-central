# Page Stylesheet Map — v68.47.1

| Route family | Body selector | Relevant stylesheet order | Purpose |
|---|---|---|---|
| `/employees` | `data-page="employees"` | `app.css`, `employee-directory.css`, `workspace-pages.css`, `design-system-cyan.css`, `assistant-dock.css`, `navigation-color-system.css`, `operational-pages.css` | Employee directory and search results. |
| `/employee/<id>` | `data-workspace-path^="/employee/"` | `app.css`, `workspace-pages.css`, `design-system-cyan.css`, `assistant-dock.css`, `navigation-color-system.css`, `operational-pages.css` | Employee profile, status card, facts, movement history, contact and organization context. |
| `/branches*` | `data-page="branches"` | Existing branch styles plus `operational-pages.css` | Branch catalogue, KPI and record icon accents. |
| `/movements*` | `data-page="movements"` | Existing movement styles plus `operational-pages.css` | Movement workflow, step markers, selected branch/employee and status chips. |
| `/missions/*` | `data-page="mission-import"` | Existing mission forms plus `operational-pages.css` | Ticket image upload/review and suggested matches. |
| `/reports/assignments/mission-edit*` and `/reports/assignments/edit-requests*` | `data-page="reports"` | Existing report/movement styles plus `operational-pages.css` | Mission editing and change-request workflows. |

## Versioning

`VERSION.md`, `pyproject.toml`, `employee_movements.__version__`, `base.html` cache keys, `data-app-version`, and the operational stylesheet version use `68.47.1`. The base template contains 20 versioned asset references; adding the employee-profile route reuses the same conditional stylesheet link and does not add a duplicate asset reference.
