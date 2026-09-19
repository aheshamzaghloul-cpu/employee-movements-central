# v34.9 — SIMPLE HIERARCHY

- Simplified hierarchy: governorate → supervisor → first-level user → branch → employee.
- Added explicit first-level-user ↔ governorate-supervisor linkage with automatic backfill when unambiguous.
- Adding a first-level user from a governorate/supervisor card links the supervisor automatically.
- Adding a branch from a first-level user card links the branch automatically.
- Employees remain linked to their branch only; supervisor and approver are resolved from the hierarchy automatically.
- Movement approver logic respects the responsible governorate supervisor and active delegation.
- User edit screen shows the administrative supervisor link; application administrator can change it.
