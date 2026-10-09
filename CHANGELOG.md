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
