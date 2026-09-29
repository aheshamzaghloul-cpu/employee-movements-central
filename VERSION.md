# v36.36 — Operational Scope Isolation Fix

- Separates operational governorate scope from governorates attached to other roles on the same account.
- Clears the operational governorate when switching roles.
- Invalidates stale scope saved for another user/role.
- App Admin and Manager use only branches inside the explicitly selected operational governorate on scope-required pages.
- A supervisor governorate such as Sohag is never inherited as App Admin's automatic operational scope.
