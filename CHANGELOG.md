## v68.15.35 — Home workflows and global mission filtering

- The home employee search now excludes employees assigned to inactive branches/governorates, including direct employee selection through query parameters, while remaining global across all active governorates and independent of the selected work governorate.
- Mission list employee filtering is usable across all governorates without first selecting a branch; employee options now identify their governorate. Destination and employee filters exclude inactive branches/governorates.
- Assignment destination permissions are now checked by the same centralized scope guard in both movement preflight and final POST, so first-level users cannot post to an out-of-scope destination while authorized supervisors, Manager, and Admin retain cross-governorate assignment access.
- Added source-contract regression checks. Static Python compilation and UI integrity checks pass; Flask request/database tests could not run because Flask is not installed in this environment. No GitHub, Blitz, environment, or database changes were made.

## v68.15.32 — Branch role access and inactive-parent guard

- Corrected branch-route decorators so branch-management routes can reach their existing governorate-scope checks for supervisors; they remain unavailable to Manager Application Support, preserving the rule that global mission access does not grant global structure administration.
- Prevented reactivating a branch while its parent governorate is inactive, with a clear Arabic message.
- Added source-contract regression checks. Static validation only; Flask runtime/database tests remain unavailable in this environment.

## v68.15.31 — Prevent duplicate branch codes within a governorate

- Branch creation and editing now reject a branch code already used in the same governorate, case-insensitively and ignoring surrounding whitespace in stored codes.
- The check excludes the branch being edited, so retaining its existing code remains valid.
- Added a source-contract regression test. This does not migrate or alter existing duplicate records.
- Validation is static only; Flask runtime/database integration tests were not run in this environment.

## v68.15.30 — Protect governorate deletion from delegation references

- Governorate deletion now checks active and historical approval-delegation rows before attempting deletion.
- If a delegation references the governorate, deletion is refused with the existing safe guidance to deactivate instead.
- Added a source-contract test for the governorate deletion guard.
- Validation is static only; Flask runtime/database integration tests were not run in this environment.

## v68.15.29 — Safe employee-edit branch input

- Reject missing or malformed `branch_id` values with a normal Arabic validation message instead of an unhandled `KeyError`/`ValueError` response.
- Added a source-contract regression test for malformed branch IDs.
- This patch was statically checked; full Flask request tests remain unrun in this environment because Flask is unavailable.

## v68.15.28 — Active-role card access and safe structure deletion

- Employee-card cross-governorate bypass now checks the active role, not all roles stored on a multi-role account, so switching away from Admin cannot retain global card access.
- Branch deletion now detects organizational first-entry branch links and asks the administrator to deactivate rather than reaching a foreign-key failure.
- Governorate, branch, and lookup creation now write their audit event in the same database transaction as the new record.
- Added source-contract tests for the active-role boundary, branch-link deletion guard, and atomic catalog audit writes.
- Static checks only; Flask/database runtime tests were not run because Flask is unavailable in this review environment. No GitHub, Blitz, environment, or database changes were made.

## v68.15.27 — Duplicate identity checks and fail-closed employee scope

- Normalize employee email addresses to lowercase on create/edit and check email duplicates case-insensitively.
- Prevent duplicate HR (`job_code`) values case-insensitively across active and historical employee records, excluding the same employee when editing/restoring.
- Make the resigned/hidden employee listing always filter by the current operational branch scope; an empty scope now returns no records instead of falling back to a global query.
- Added source-contract checks for duplicate identity checks and the empty-scope security boundary.
- Static checks only; Flask/database runtime tests were not run because Flask is unavailable in this review environment. No GitHub, Blitz, environment, or database changes were made.

## v68.15.26 — Reactivated employee lifecycle consistency

- The resigned/administratively hidden list now excludes active employees who have been rehired, while retaining their historical resignation date on the employee record.
- The reactivation endpoint now rejects repeat reactivation of an already-active employee rather than allowing the same historical record to be processed again.
- Added source-contract checks for employee date validation, atomic creation/audit, missing-record handling, and reactivation/list consistency.
- Python compile, UI integrity, and targeted source assertions pass. Full pytest/runtime remains blocked because Flask is not installed in this review environment. No GitHub, Blitz, environment, or database changes were made.

## v68.15.25 — Employee lifecycle form and audit safety

- Invalid or malformed dates entered in employee add/edit, resignation, and reactivation forms now produce the existing validation path instead of raising an uncaught `ValueError`.
- Employee creation and its audit event now share one database transaction; a failed audit write cannot leave a newly created employee committed without its audit record.
- Corrected the missing-employee delete path to return 404 before checking object permissions.
- Static checks only; Flask runtime tests were not run because Flask is unavailable in this environment. No GitHub, Blitz, environment, or database changes were made.

## v68.15.24 — Central Manager cross-governorate assignment selection

- Fixed centralized employee and destination authorization so `Manager Application Support`, like a governorate supervisor, can select active employees and destination branches across governorates for assignment (`انتداب`) only.
- Updated the movement employee/branch picker to expose global active branches to the central Manager only when the selected movement type is assignment. Leave and permission remain constrained by operational scope.
- Added source-contract coverage for the Manager assignment exception and retained scoped fallbacks for ordinary employee/branch operations.
- Static/source checks only; Flask runtime tests were not run in this environment. No GitHub, Blitz, environment, or database changes were made.

## v68.15.23 — Excel import transaction and review-session hardening
- Verify that the reviewed Excel token still matches the upload token and requested import type before applying changes; stale or cross-type review sessions are discarded.
- Commit imported records and the corresponding audit event in one database transaction, avoiding a committed import without its audit record.
- Log detailed import exceptions server-side and show safe Arabic messages to users rather than exposing raw exception details.
- Synchronize application/package version identifiers to v68.15.23.
- Python compilation, UI integrity, archive integrity, and targeted static assertions: PASS.
- Full Flask/database runtime tests: NOT RUN because Flask is unavailable in this environment.

## v68.15.22 — Central Manager mission access correction
- Corrected Manager Application Support access so assignment mission review, printing, editing, and exports are not incorrectly limited by the selected work governorate. Leave/permission viewing and editing remain limited to the selected operational scope.
- Included Manager Application Support in the global mission report query and XLSX export actor set.
- Preserved governorate/branch scope for supervisors and first-entry users; this change does not grant cross-governorate employee/branch administration.
- Synchronized VERSION.md and pyproject.toml to v68.15.22.
- Python compile, UI integrity, and static regression assertions: PASS.
- Full Flask runtime tests: NOT RUN because Flask is unavailable and package installation is blocked by network access.

## v68.15.16 — Basyouni Employee Add Intent Boundary

- Fixed a real assistant routing bug where a clear employee-add request such as «عايز أضيف موظف» was correctly detected locally as `employee_add`, then overwritten by a generic Gemini `topic_options` response.
- Explicit employee-add and movement-registration intents now retain priority over generic `help/topic_options/employee_topic` classifications.
- The employee-add action now opens the actual employee form anchor `/employees#employee-add`.

## v68.15.14 — Basyouni Tool Execution Boundary
- Added static contracts proving Gemini tool dispatch can only prepare mutations.
- Confirmed direct manager/movement execution remains behind pending-plan confirmation.
- No business-rule or permission changes.

## v68.15.13 — Basyouni Pending Plan Hardening
- Bind confirmation plans to the current user and active role.
- Expire pending confirmation plans after 10 minutes.
- Centralize pending-plan storage/consumption in `assistant/pending.py`.
- Preserve final permission and current-state checks at execution time.

# Changelog

## v68.15.20 — Assistant Error Containment
- Added server-side exception logging for unexpected assistant-turn failures so the cause can be diagnosed from runtime logs rather than only seeing a generic browser error.
- Roll back failed assistant turns and clear any pending assistant mutation plans after an unexpected exception, preventing stale plans from being confirmed.
- Return a safe Arabic error message instead of allowing an unexpected assistant exception to become an unhandled HTTP 500.
- Added a static contract test for this failure path. This improves diagnostics and containment; it does not by itself prove the original runtime cause is fixed.


## v68.15.19 — Global Manager Oversight
- Corrected the Manager workspace to aggregate all active governorates, regardless of the daily work-governorate selector.
- Made the Manager's mission edit-request queue and review/save authorization cross-governorate, matching the Manager's central position above governorate supervisors.
- Made the monthly closed-mission report global for Manager and Admin.
- Kept ordinary operational pages scoped; this change applies to the central Manager workspace, request handling, and monthly management report.
- Added static contract checks for the cross-governorate Manager behavior.


## v68.15.18 — Manager Workspace
- Added a dedicated «المدير» navigation entry for Manager Application Support and the application administrator.
- Added a central workspace for pending closed-mission edit requests, monthly mission summaries, mission reports, and governorate-level movement summaries.
- Manager report data follows the selected work-governorate scope; the application administrator retains global oversight.
- Added the manager workspace to operational scope handling so manager requests and reports do not bypass governorate selection.
- Static Python/Jinja/UI integrity checks passed. Full Flask runtime tests were not run in this environment because Flask is not installed.

## v68.15.17
- Comprehensive Basyouni boundary hardening: preserve high-confidence local employee-add intent, fix movement scope imports, prevent persisted assistant replies/live record content from being sent to Gemini, and redact selected record IDs from model-visible workspace context.


## v68.15.12 — Basyouni Execute Current-State Audit
- Audited sensitive execute branches for stale-plan usage.
- Added contracts requiring current DB reloads before mutation for governance, branch, employee, user, movement, entry-assignment, and delegation operations.
- Added contracts ensuring role and movement operations re-check current state before mutation.
- No business-rule or permission expansion.

## v68.15.11 — Basyouni Execute Transaction Boundary
- Wrapped `assistant.manager.execute()` in a single transaction boundary.
- Failed execution results now rollback pending SQLAlchemy mutations before returning.
- Unexpected execution exceptions rollback the current transaction before propagating.
- Kept the existing inner business logic and single final commit point unchanged.
- Added regression contracts for rollback ownership and commit-point uniqueness.

## v68.15.10 — Basyouni Manager Resolver Boundary

- Centralized active governorate-supervisor name resolution in `assistant/manager_resolvers.py`.
- Moved supervisor-role filtering into the database query instead of loading active users and filtering roles in Python.
- Reused the resolver for first-entry assignment, delegation creation, and delegation revocation paths.
- Preserved the existing confirmation/execute split: `plan()` resolves and previews; `execute()` rechecks the application-manager role before mutation.
- Added architecture contracts for centralized supervisor resolution and plan/execute boundaries.
- Compile/static checks pass; runtime pytest remains blocked by missing Flask in the review environment.

## v68.15.9 — Basyouni Permission Boundary Audit

- Centralized assistant movement employee and destination scope checks.
- Fixed duplicated assistant route logic that could treat governorate supervisors as globally scoped for leave/permission selection.
- Preserved wider supervisor scope for assignments only.
- Added regression contract coverage.
- Compile/static checks pass; runtime pytest remains blocked by missing Flask in the review environment.

## v68.15.8 — Assistant Render Query Optimization

- Removed unbounded employee movement history loading from `assistant/render.py`; employee history is capped at 20 rows and latest movement fields are resolved directly with bounded queries.
- Replaced Python-side per-employee duplicate filtering in today movement/assignment reports with database-side latest-row selection.
- Batched candidate record loading instead of repeated `session.get()` calls.
- Eager-loaded entry assignment employee/supervisor relationships for branch information rendering.
- Added performance contracts covering bounded employee history and database-side latest-movement selection.
- Compile/static checks passed. Full pytest remains unavailable in the current review environment because Flask is not installed.

# Changelog

## v68.15.7 — Performance Audit Continuation
- نقل فلترة المحافظات إلى استعلامات DB محدودة داخل مساعد التطبيق.
- استبدال فحص تعارض فروع المدخل الأول ببحث وجود مباشر بدل تحميل كل التكليفات النشطة.
- تقليل نطاق تنظيف صلاحيات الدور عند سحب الدور.
- تحسين مسارات عرض موظفي المحافظة/الحركات داخل نطاق الفروع لتطبيق نطاق الفروع في قاعدة البيانات.
- إضافة Contract tests لمنع عودة أنماط تحميل البيانات غير الضرورية.
- لم تتغير قواعد الصلاحيات أو السلوك الوظيفي المقصود.

## v68.15.3 — Performance Core: Movement Overlap Query

- Reworked `movement_overlaps()` to filter conflicts in the database instead of loading all active movements with `.all()`.
- Preserved existing conflict-message ordering and movement-overlap semantics.
- Added `tests/test_movement_overlap_query_contract.py`.
- No schema/index changes introduced; migration infrastructure remains unchanged.

## v68.15.2 — Mission Print Permission Core

- Added centralized `can_print_mission()` authorization guard.
- Unified mission print/PDF route authorization without changing mutation permissions.
- Removed an unused duplicate mission employee-scope helper.

# v68.15.0 — Permission & Scope Core

- إضافة حارس `governorate_ok()` مركزي في `access.py`.
- توحيد فحوص نطاق المحافظة في عمليات إدارة الفروع داخل `catalog.py`.
- إضافة `tests/test_permission_scope_core_contract.py`.
- الحفاظ على سلوك اختيار محافظة العمل والنطاق التشغيلي كما هو.

## v68.14.0 — Core cleanup: model attribute consistency
## [68.14.1]

- Strengthened model/attribute consistency regression coverage across all Python, HTML, and JavaScript project files.
- Verified canonical `Movement.destination` relationship usage and preserved `destination_branch_id` as the database column/form field.
- Corrected invalid `Movement.destination_branch` relationship references to the canonical `Movement.destination` relationship.
- Preserved the `destination_branch_id` database column and form field names.
- Added a static regression contract preventing the relationship-name mismatch from returning.
- No business-rule, authorization, database-schema, or UI behavior changes intended.

## v68.13.3 — Mission document services

## v68.13.3 — Mission Lifecycle Service
- Extracted mission close/reopen/edit and edit-request execution state changes into `services/mission_lifecycle.py`.
- Preserved authorization, validation, audit events, and transaction boundaries.

- Extracted mission PDF rendering and detailed Excel export into `services/mission_documents.py`.
- Preserved routes, filters, authorization checks, lifecycle rules, and output formats.
- Static validation only; runtime integration tests require the application dependencies.

## v68.13.1 — Refactor Phase 2: shared date filter parsing
- Centralized optional ISO date parsing for reports and mission filters.
- Removed three duplicated nested date-parser implementations.
- No permission, scope, workflow, or database behavior intentionally changed.

# CHANGELOG

## v68.13.0 — Code Hygiene Phase 1
- Centralized duplicated assistant employee-visibility logic in `assistant/visibility.py`.
- Preserved existing scope and role semantics; no functional permission expansion.
- Synchronized package/version metadata.


## v68.12.0 — Mission Center Lifecycle & Edit Requests
- Added date-range mission center filtering and mission-state filtering (تحت التحرير/مغلقة).
- Added supervisor post-close edit requests with reason and full mission snapshot.
- Added Manager/Application Admin request inbox and controlled execution.
- Manager/Admin can save the corrected mission as مغلقة or تحت التحرير; request execution is audited.
- Added monthly mission detail export-ready aggregation template.

## v68.11.9 — Assignment-Only Global Reach & Monthly Mission Aggregation
- Supervisor global employee reach is limited to assignment/mission registration and viewing.
- Leave and permission viewing remains within the supervisor operational scope.
- Mission center employee filter no longer exposes out-of-scope employees to Manager.
- Added Manager/Admin monthly aggregation of closed missions by employee and branch, with calendar days overlapping the selected month.
- No incentive formula is invented or applied; the aggregation is a factual preparation surface.
- Runtime Flask/PostgreSQL was not executed in the current environment.
# v68.11.8 — Assignment-Only Global Supervisor Selection

- Supervisor global employee selection is limited to انتداب/مأمورية only.
- Leave and permission registration/editing remain within operational scope.
- Server-side preflight/create and movement edit guards enforce the distinction.
- Closed assignments remain editable/reopenable only by Manager Application Support or مسؤول التطبيق; printing remains view/print-only.

# v68.11.8 — Global Supervisor Movement Operations

- مشرف المحافظة يستطيع تسجيل حركة لأي موظف نشط من أي محافظة، مع بقاء نطاق الحساب منفصلًا عن بيانات الموظف.
- وجهة الانتداب/المأمورية يمكن أن تكون أي فرع نشط في أي محافظة للمشرف.
- المأمورية/الانتداب المغلق لا يمكن تعديله أو إعادة فتحه من المشرف؛ التعديل بعد الإغلاق وإعادة الفتح متاحان للـManager ومسؤول التطبيق فقط.
- الطباعة والمشاهدة لا تُعامل كتعديل؛ المشرف يستطيع طباعة المأموريات من أي محافظة.
- Basyouni يستخدم نفس قاعدة النطاق عند تسجيل الحركة.
- الحفاظ على نطاق Manager والمدخل الأول كما هو.
- منع تعديل مأمورية مغلقة إلى حالة «مفتوحة بلا تاريخ نهاية» دون إجراء إعادة فتح صريح.


- توحيد رقم الإصدار داخل الحزمة إلى v68.11.6.
- توحيد اختيار محافظة وفرع جهة المأمورية في تعديل الحركة وتعديل المأمورية مع إتاحة جميع المحافظات النشطة.
- منع تعديل أو تثبيت أو عرض نموذج مأمورية لسجل حركة غير نشط/محذوف.
- منع طباعة مأمورية غير نشطة من رابط الطباعة المباشر.

# Changelog

## v68.14.3 — Mission Edit Request Service
- فصل إنشاء طلب تعديل المأمورية وقائمة الطلبات وسياق المراجعة والتحقق والتنفيذ إلى `services/mission_edit_request.py`.
- إبقاء HTTP والصلاحيات والـredirect/flash داخل Blueprint.
- الحفاظ على حالات الطلب، منع التكرار، التحقق من التواريخ والتعارض والحالة النهائية.
- Python compile: PASS
- UI integrity: PASS
- Mission edit-request contract: PASS


## v68.14.4 — Mission Query Service
- استخراج منطق استعلام وفلاتر تقرير المأموريات من `blueprints/missions.py` إلى `services/mission_query.py`.
- إبقاء الـBlueprint مسؤولًا عن HTTP والتحقق من الصلاحيات والعرض.
- الحفاظ على نطاق المستخدم وجميع فلاتر التقرير وعدّاد طلبات التعديل.
- إضافة اختبار Contract يمنع إعادة منطق الاستعلام إلى الـBlueprint.
- Python compile: PASS.

## v68.11.5 — Destination Governorate Selection

- Added explicit all-governorate destination selection for assignment registration.
- Added destination-governorate/branch filters to mission printing without expanding operational scope.

# v68.11.3 — Employee Card Scope Guard

- Keep homepage employee search global as designed.
- Require operational branch scope before opening an employee card directly.
- Keep مسؤول التطبيق globally authorized for employee cards.
- Prevent direct URL access from bypassing governorate/branch scope.


## v68.11.3 — Delegation Operational Boundary Fix

- إصلاح استيراد `branch_ok` في لوحة الصفحة الرئيسية لمنع `NameError` عند مسار فحص نطاق موظف الحركة.
- لا تغيير في حدود التفويض أو ملكية التكليفات التنظيمية.

## v68.11.0 — Delegation Operational Boundary

- Delegated supervisors can see first-level entry assignments inside their temporary governorate scope for operational follow-up.
- Existing entry assignments remain owned by their original supervisor; delegated supervisors receive read-only monitoring for those assignments.
- The Home page hides structural entry-assignment creation in a governorate that is delegated only to the current supervisor.
- Server-side POST protection prevents a delegated supervisor from creating/recreating a first-level entry assignment in a delegated-only governorate.
- Permanent governorate scope continues to allow the original supervisor to manage their own entry assignments normally.
- Movement, employee, report, and mission operations continue to derive their scope from the canonical effective governorate/branch scope.

## v68.11.0 — Delegation Lifecycle Guard

- Effective delegated scope now requires the delegate account to be active and to retain the `مشرف محافظة` role.
- Effective delegated scope now requires the original supervisor to remain active, retain the `مشرف محافظة` role, and remain permanently assigned to the delegated governorate.
- Inactive governorates no longer contribute delegated operational scope.
- Delegation creation explicitly rejects inactive governorates.
- This is a security/lifecycle guard: stale delegation records may remain for audit history, but they cannot grant operational access after their prerequisites disappear.


- توحيد مصدر الحالة الحالية للحركة بين الرئيسية، بطاقة الموظف، قوائم الموظفين، صفحة الحركات وPreflight.
- جعل اختيار الحركة الحالية حتميًا عند وجود أكثر من سجل مرشح.
- منع الانتداب المغلق أو الحركة غير النشطة من الظهور كحالة حالية.
- منع ظهور الانتدابات المغلقة في قائمة «تحتاج متابعة».
- إضافة اختبارات عقدية لدورة ما بعد الحفظ.

## v67.2.0 — Premium Interactive Design System
- إعادة توحيد لغة التصميم البصرية على مستوى التطبيق بالكامل.
- Shell فاخر وهادئ: Sidebar وTopbar وPage Headers وCommand Bar.
- توحيد الحقول والأزرار والجداول والحالات والبطاقات والنوافذ المنبثقة.
- إعادة صقل الرئيسية مع إبقاء بحث الموظف وتسجيل الحركة في مركز التجربة.
- إبقاء حالة الموظفين والمدخلين الأوائل ضمن المتابعة الثانوية دون حذف العمليات الفعلية.
- تحسين صفحات الموظفين وملف الموظف والتقارير والمأموريات والتفويض والإدارة وتسجيل الدخول.
- الإشعارات وبسيوني أصبحا جزءًا من نفس لغة التصميم التفاعلية.
- إزالة «الحركات» من القائمة الجانبية الرئيسية مع الإبقاء على مسارات التشغيل الحالية.
- لا تغيير في منطق البيانات أو الصلاحيات أو مسارات العمل المقصودة.
## v67.2.0 — Scope Integrity Review

- فرض محافظة العمل المختارة على عمليات الموظفين والحركات والتقارير والمأموريات والتصدير والواجهات البرمجية التشغيلية.
- منع تجاوز النطاق عبر رابط مباشر أو طلب POST خارج سياق المحافظة المختارة.
- إصلاح متغير قديم في استبدال المدخل الأول لدى Manager Application Support.
- استمرار البحث العالمي عن الموظف في الرئيسية قبل اختيار المحافظة.
- تنظيف ملفات `__pycache__` من الحزمة.

## v66.0.0 — System Cohesion & UX

- إزالة بطاقة «الحركات» من أدوات الرئيسية لمنع تكرار وظيفة التشغيل داخل الصفحة الرئيسية.
- الإبقاء على صفحة الحركات كصفحة مستقلة للنظام.
- تحديث اختبارات الإصدار والحالة التشغيلية لتطابق السلوك الحالي.
- توحيد رقم الإصدار إلى 66.0.0.

# Changelog

## v68.14.3 — Mission Edit Request Service
- فصل إنشاء طلب تعديل المأمورية وقائمة الطلبات وسياق المراجعة والتحقق والتنفيذ إلى `services/mission_edit_request.py`.
- إبقاء HTTP والصلاحيات والـredirect/flash داخل Blueprint.
- الحفاظ على حالات الطلب، منع التكرار، التحقق من التواريخ والتعارض والحالة النهائية.
- Python compile: PASS
- UI integrity: PASS
- Mission edit-request contract: PASS


## v65.11.4 — Full Agreement Audit & Boundary Fixes
- مراجعة فعلية للنسخة السابقة مقابل قواعد الأدوار والنطاقات وفصل وظائف الإدارة.
- إضافة مشرف المحافظة إلى بوابة نطاق العمل التشغيلية وتثبيت نطاقه في الجلسة مثل باقي الأدوار التشغيلية.
- إبقاء بحث الموظف العالمي في الرئيسية متاحًا قبل اختيار نطاق العمل.
- حصر عمليات «مدخل أول» في الرئيسية، وتحويل المسارات القديمة إلى إحالات توافقية بدل التنفيذ المكرر.
- تصحيح نطاق Manager Application Support في عمليات مدخل أول باستخدام `scope_governorate_id()` بدل مفتاح جلسة قديم.
- تقييد عمليات مدخل أول الخاصة بـ Manager بالنطاق المختار.
- إبقاء استبدال مشرف المحافظة وظيفة مستقلة، وإخراج استبدال المدخل الأول من مسار `/replacement`.
- تحويل بسيوني على سطح المكتب إلى مساحة محادثة جانبية مدمجة لا تغطي المحتوى.
- توحيد الإصدار إلى 65.11.4.
- Python compile: PASS
- Jinja template parse: PASS
- UI integrity: PASS
- Full Flask runtime tests: NOT CLAIMED (بيئة التنفيذ الحالية لا توفر Flask runtime).

## v65.11.0 — Smart Administration Center
- إعادة بناء تجربة صفحة الإدارة حول وظائفها الحالية بدل اختراع وظائف جديدة.
- إضافة صف مؤشرات تشغيلية قابل للنقر يعتمد على بيانات النظام الموجودة.
- تبسيط رأس الصفحة وتحويله إلى مركز إجراءات عملي.
- الإبقاء على إدارة الحسابات والأدوار، الهيكل، المدخل الأول، Excel، القوائم المرجعية، وسجل التدقيق.
- لا تغيير في منطق الصلاحيات أو قواعد الأعمال.
- Python compile: PASS
- UI integrity: PASS
- Full pytest: NOT CLAIMED (بيئة التنفيذ الحالية لا توفر Flask runtime).
## v68.14.4
- Fixed missing `movement_overlaps` import in mission edit flow.
- Completed mission.py remainder audit; no additional confirmed domain refactor performed.

## v68.15.1 — Permission & Scope Core: Movement Employee Access
- Added `can_manage_movement_employee()` to centralize employee-selection scope for movement creation/preflight.
- Preserved the existing rule: application administrators have global access; governorate supervisors may select employees globally for assignments; other movement types remain branch-scoped.
- Removed duplicated `global_employee_access` role logic from movement routes.
- Added a contract test for the centralized rule.
- Compile check passed. Full runtime pytest is not claimed because Flask is unavailable in the review environment.

## v68.15.4 — Basyouni Query Performance Core
- Narrowed assistant employee search candidates in the database before Python-side visibility/normalization checks.
- Pushed branch-scope filtering for assistant movement search into the database for non-global users.
- Changed employee current-status lookup from `.all()` to `.first()` because only the newest matching movement is consumed.
- Added assistant query-performance contract tests.
- Python compile and contract tests passed. Full runtime pytest is not claimed because Flask is unavailable in the review environment.

## v68.15.6 — Basyouni Performance Audit
- Pushed assistant branch and governorate search filtering/limits into the database instead of loading full active directories into Python.
- Replaced governorate-wide assignment reporting N+1 employee movement lookups with a single movement query.
- Replaced branch-status per-employee current movement scans with one bounded current-movement query.
- Narrowed selected assistant manager name/look-up searches before role/semantic checks.
- Added regression contract tests for the performance-sensitive paths.
- Python compile: PASS. Full Flask runtime pytest is not claimed until Flask is available in the review environment.

## v68.15.5 — Basyouni Assistant Architecture Core
- Extracted bounded movement lookup into `assistant/movement_queries.py`.
- Preserved existing unique/multiple/no-match behavior.
- Limited movement candidate loading to two rows, enough to distinguish unique from multiple.
- Added regression contract test.

## v68.15.21 — Central report scope correction
- Corrected the Manager/Admin report drill-down so `/reports-missions` and general movement reports aggregate all active governorates by default.
- Governorate-specific report links now narrow the central report to the selected active governorate.
- Kept supervisor report queries constrained to their already-authorized governorate/branch scope; query parameters cannot expand access.
- Updated report wording to distinguish central all-governorate reporting from a governorate-specific report.
- Static checks only; runtime Flask tests still require installing the project dependencies in a suitable environment.


## v68.15.33 — Inactive governorate destination safeguards

- Excluded branches under inactive governorates from employee-movement and mission destination pickers, including the Home quick-action picker.
- Enforced the active-parent-governorate rule in movement preflight/create/edit and mission edit/request execution paths, not only in dropdown presentation.
- Kept historical movement/mission records intact; this only prevents choosing an inactive destination for new or edited assignment data.
- Static checks only; Flask runtime tests remain unavailable in this environment.


## v68.15.34 — Home priority workflows
- Reprioritized the home page around global employee search, cross-governorate assignment registration, and direct mission printing.
- Kept global search, assignment selection, and mission printing available even before an operational work governorate is selected; the work-scope selector remains required for scoped operational monitoring.
- Made assignment the default movement action and hid leave/permission choices for an out-of-scope employee, while preserving the server-side permission checks.
- Made the mission-report employee filter include employees from every active governorate for application administrators, governorate supervisors, and Manager Application Support.
- Clarified that the mission list and print workflow covers all governorates.
