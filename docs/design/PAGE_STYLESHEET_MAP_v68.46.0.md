# Page / Stylesheet Map — v68.46.0

| Page / route | `data-page` | Page CSS loaded by `base.html` | Shared CSS layers |
|---|---|---|---|
| Administration center `/structure` | `administration` | `pages/management.css` | `app.css`, `design-system-cyan.css`, `pages/admin-reports-assistant.css`, `pages/assistant-dock.css`, `navigation-color-system.css` |
| Users and permissions `/users` | `users` | `pages/management.css` | Same management shell layers as administration |
| Delegations `/delegations` | `delegations` | `pages/management.css` | Same management shell layers as administration |
| Governorates `/governorates` | `governorates` | `pages/workspace-pages.css` | `app.css`, `design-system-cyan.css`, `pages/assistant-dock.css`, `navigation-color-system.css` |
| Branches `/branches` | `branches` | `pages/workspace-pages.css` | `app.css`, `design-system-cyan.css`, `pages/assistant-dock.css`, `navigation-color-system.css` |

The navigation-color layer is loaded last to maintain the approved stronger navy/sky-blue sidebar and semantic navigation icon palette. The administration-only CSS is deliberately not loaded for the governorates catalogue page.
