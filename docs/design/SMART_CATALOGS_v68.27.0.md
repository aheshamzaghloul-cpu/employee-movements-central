# v68.27.0 — Smart assistant and structural directories

## User-visible updates

- The assistant launcher in the top bar now identifies itself as **بسيوني — في خدمتك**, uses a clear wordmark, shows a visual presence cue, and preserves accessible labels and expanded-state behavior. It is ordered first in the RTL header so it sits at the far right when the mobile menu appears.
- Governorates have a responsive card directory with total/active counts, branch counts and employee counts; search and active/inactive filters; edit, enable/disable, and delete actions stay attached to each governorate card.
- Branches have a responsive directory with totals, active/inactive counts, active employee counts by registered branch, text search across branch name/code/governorate, governorate and status filters, and progressive edit forms.
- The employee directory can now search employee name/code/title plus branch and governorate names. It offers explicit controls to expand or collapse all visible branches. The backend query remains constrained to authorized branch IDs; invalid filters are not widened.

## Validation

- `contract_tests`: **186 passed**.
- Python syntax compilation: **154 files passed**.
- Jinja syntax parsing: **44 templates passed**.
- CSS syntax parsing: **6 stylesheets passed**.
- JavaScript syntax check: `assistant_dock.js` and `catalog_directory.js` passed.

## Boundaries

These checks validate source contracts and syntax, not a live authenticated session. Runtime rendering and DB-backed interaction should still be verified in the deployment/test environment. No live database or deployment was changed.
