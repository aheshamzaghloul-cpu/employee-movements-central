# Page stylesheet and script map — v68.28.0

| Surface | Styles / script | Scope |
|---|---|---|
| Shared application shell | `static/css/app.css` | Global navigation, header, assistant launcher/panel, tokens, shared components |
| Governorate and branch catalogs | `static/css/pages/workspace-pages.css`, `static/js/catalog_directory.js` | Loaded for catalog paths; search, status/governorate filters, result counts, edit disclosure and add-panel deep links |
| Employee directory | `static/css/pages/employee-directory.css` | `/employees`; grouped branch browsing and directory controls |
| Movement forms | `static/css/pages/movement-forms.css` | Movement registration/editing and mission edit-request forms |
| Administration/users/delegations | `static/css/pages/management.css` | `/structure`, `/users`, `/delegations` |
| Home | `static/css/pages/home.css` | `/` |

The catalog script is marked `defer` because its selectors require the directory elements to exist. The employee directory search remains server-side scoped to permitted branch IDs; branch/governorate terms extend matching only within that existing scope.


## v68.28.0 change note

- The movement registration picker now initializes from the selected operational governorate and reports loading errors.
- The homepage employee-search action scrolls to and focuses the global search field.
- First-level-entry branch rows expand into employee profile links; the Jinja expression for employee code is syntax-checked.
- Basyouni assistant spelling normalization and private aliases are implemented in `assistant/directory.py`, `assistant/routes.py`, and `assistant/privacy.py`.
