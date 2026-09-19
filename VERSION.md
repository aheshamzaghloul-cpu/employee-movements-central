# v34.9.8 — First-level appointment branch separation

- The first-level entry is also an employee.
- Added a separate **employee appointment branch** field.
- Appointment branch is independent from the first-level user's managed branches.
- Creating/editing a first-level entry updates the linked employee's appointment branch only.
- Managed branches remain in `UserBranch` and can be multiple.
- Admin can select any active branch; supervisors can select an active branch in their governorate scope.
