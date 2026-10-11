## v68.22.12
- Supervisor-side edits to first-level entry accounts now require the acting supervisor to cover every governorate represented by the assigned branches; invalid assignments roll back rather than saving without a supervisor link.
- Added explicit rollback on validation failures in this edit path to avoid leaving partial pending changes in the session.
- Static checks only; Flask runtime/database tests remain unverified in this environment. Production database unchanged; not deployed.

## v68.22.11
- Added explicit worksheet row and column bounds to Excel preview and confirmation, complementing the existing upload-byte and ZIP expansion limits to reduce oversized-workbook resource exhaustion risk.
- Added a source-contract regression test ensuring dimensions are checked before data-row iteration.
- Static checks only; Flask runtime/database tests remain unverified in this environment. Production database unchanged; not deployed.

## v68.22.10
- First-level entry employee appointment branch must be among the branches explicitly assigned to that entry account, for both application administrators and supervisors.
- First-level entry assignments now require an active supervisor whose governorate scope covers all governorates assigned to the entry account; invalid assignments roll back instead of silently saving an unlinked entry account.
- Added source-contract regression checks for both assignment integrity rules.
- Static checks only; Flask runtime/database tests remain unverified in this environment. Production database unchanged; not deployed.

## v68.22.9
- Prevent hard deletion of users linked to employee records, movement audit fields, entry assignments, approval delegations, or mission edit requests; require deactivation to preserve historical relationships.
- Added a source-contract regression test for user deletion safeguards.

## v68.22.8
- Prevent moving a branch to another governorate while employees, user branch assignments, entry-assignment links, or source/destination movements still reference it. This avoids silently changing historical and operational scope for linked records.
- Added a source-contract test covering each relationship guard.
- Static checks only; runtime/database tests require Flask and were not run here. Production database unchanged; not deployed.

## v68.22.7
- Prevent permanent branch deletion when historical movements reference the branch as their source, as well as as their destination. This preserves historical integrity and directs administrators to deactivate referenced branches instead.
- Added a source-contract test for both movement reference directions.
- Static checks only; runtime/database tests require Flask and were not run here. Production database unchanged; not deployed.

## v68.22.6
- Excel import preview failures now remove temporary upload/review artifacts and clear session tokens, preventing stale files from accumulating after malformed uploads or parser errors.
- Added a source-contract check for preview-failure cleanup.
- Prior security and scope fixes retained; runtime/database tests remain unverified in this environment.

# Changelog

## v68.22.5
- Hardened Excel import upload handling by validating XLSX ZIP structure, entry count, total expanded size, encryption flags, and extreme compression ratios before passing the file to openpyxl. Invalid uploads are removed from temporary storage.
- Added a static contract test for the archive validation guard.
- Static checks only; runtime Flask/database tests remain unverified in this environment.

## v68.22.4
- Production configuration now fails fast if `COOKIE_SECURE` is not enabled, instead of merely warning; this prevents a production deployment from silently issuing session cookies without the Secure attribute. Production must use HTTPS and set `COOKIE_SECURE=1`.
- Added configuration regression contracts for both rejected insecure production configuration and accepted secure configuration.
- Static checks only in this environment; Flask runtime tests and deployment were not performed; production database unchanged.

## v68.22.3
- Added explicit Flask multipart parser limits (`MAX_FORM_MEMORY_SIZE` and `MAX_FORM_PARTS`) alongside the existing request-body limit to reduce resource-exhaustion risk from oversized/excessive form fields.
- Added a source-contract test for these request limits.
- Static verification only; no live Flask/database tests or deployment performed.

## v68.22.2
- Added a repeatable static security check for all POST routes across the Flask blueprints. It verifies that all state-changing routes except the explicitly public login/logout endpoints use the authenticated request guard, and flags changes to the global CSRF exemption list or token comparison for review.
- The audit found 54 POST routes; all passed the current authentication/CSRF source-contract check. This is a static source check, not a runtime penetration test.
- No business behavior or production data changed; no deployment performed. Runtime tests remain unavailable in this environment because Flask is not installed.

## v68.22.1
- Expanded the regression-contract suite for Excel imports: preserve administrator-only import authorization, reject unsupported import kinds, recheck database references at apply time, and retain transaction rollback on failure. This batch is a focused security/maintainability audit; it does not loosen roles or change import behavior.
- Static checks only; pytest/runtime database tests and deployment were not performed; production database unchanged.

## v68.22.0
- Consolidated security review follow-up: Manager Application Support now sees only destination branches and governorates within the current operational scope on the ordinary movement edit page, matching the existing server-side POST scope guard. Application administrator retains cross-governorate options.
- Added source-contract tests for destination picker filtering and POST enforcement.
- Static checks only; full Flask/database runtime tests and deployment not performed; production database unchanged.

## v68.21.28
- Added focused source-contract tests for mission close/reopen, assignment close/reopen, and movement deletion authorization boundaries.
- Confirmed lifecycle routes check movement management permission and source-movement scope; reopening remains restricted to Manager Application Support or application administrator and checks overlapping movements.
- Static checks only; full Flask/database runtime tests and deployment not performed; production database unchanged.

## v68.21.27
- Extended Manager Application Support operational-scope enforcement to direct mission edits and ordinary movement edits. Destination options are filtered to the selected operational branch scope and POST handlers reject out-of-scope branch IDs; application administrator keeps cross-governorate access.
- Static verification only; no production database changes or deployment.

## v68.21.26
- Enforced destination-branch authorization in the mission edit-request POST service, rather than relying only on filtered dropdown choices. Manager submissions are limited to branches in the current operational scope; application administrators retain cross-governorate access.
- Added a focused source-contract test for the server-side destination-scope guard.
- Static checks only; full Flask/database runtime tests and deployment were not performed; production database unchanged.

## v68.21.25
- Corrected mission edit-request queue scoping: only the application administrator receives the all-governoriety queue; Manager Application Support uses the selected operational branch scope.
- Restricted destination branch/governorate choices on the manager review page to the active operational scope, and enforced source-mission scope on both review and save routes. The POST path retains its own checks.
- Added focused source-contract tests for queue, review-page and save-route scope enforcement.
- Static checks only; full Flask/database runtime tests and deployment not performed. Production database unchanged.

## v68.21.24
- Added rollback-on-error protection around mission lifecycle mutations (close, reopen, direct edit, and reviewed edit request execution). A failure while saving the movement, movement history, or audit row now rolls back the unit of work and re-raises the original error.
- Added a focused source-contract test for all four lifecycle operations.
- Validation: Python compile, UI integrity, homepage workflow contracts, JavaScript syntax, manifest JSON, and ZIP integrity. Full Flask/database runtime tests and deployment were not performed.

## v68.21.23
- Hardened mission edit-request creation against simultaneous duplicate submissions: database uniqueness conflicts now roll back the failed SQLAlchemy transaction and return the same duplicate-request outcome as the normal pre-check, rather than surfacing as an unhandled server error. Unexpected exceptions still roll back and propagate.
- Added a contract test for integrity-conflict handling and rollback.
- Validation performed: compile checks, focused mission contracts, UI integrity, homepage workflow contracts, JavaScript syntax, manifest JSON, and ZIP integrity. Full Flask runtime/database tests and deployment were not performed.

## v68.21.22 — حماية مراجعة طلبات تعديل المأموريات

- تطبيق محلل التواريخ الآمن على مسار مراجعة طلب تعديل المأمورية أيضًا، ورفض التاريخ غير الصالح برسالة عربية قبل تنفيذ الطلب أو تغيير بيانات الحركة.
- إضافة اختبار تعاقدي يتحقق من أن فحص التاريخ يسبق استدعاء تنفيذ الطلب.
- لم تُشغّل اختبارات Flask/قاعدة بيانات متكاملة ولم يتم النشر.

## v68.21.21 — معالجة تواريخ المأموريات غير الصالحة

- تحويل التواريخ غير الصالحة في تعديل المأمورية وتاريخ الطباعة إلى رسائل تحقق واضحة بدل استثناء غير معالج.
- منع متابعة الحفظ أو إنشاء ملف الطباعة عندما يفشل تحليل التاريخ.
- إضافة اختبار تعاقدي مستقل لمسارات التواريخ.

## v68.21.20 — اختبارات أمان المسارات المباشرة
- إضافة اختبارات تعاقدية للتحقق من أن سجل تاريخ الحركة يتطلب صلاحية التدقيق ونطاق الحركة معًا.
- إضافة فحص تعاقدي لبوابة CSRF العامة لطلبات POST.
- التحقق من أن إسناد المحافظات والفروع لا يحذف الإسنادات الحالية قبل اجتياز فحوص المدخلات والنطاق.
- هذه الدفعة تضيف تغطية انحدار للمسارات الأمنية؛ لا تدّعي اختبار تشغيل التطبيق، ولم تُعدّل قاعدة الإنتاج أو النشر.

## v68.21.19 — حماية إعادة فتح الانتداب وإسنادات النطاق

- إعادة فحص تعارض الحركة قبل إعادة فتح الانتداب كفترة مفتوحة، قبل مسح بيانات الإغلاق أو تغيير الحالة.
- رفض معرّفات المحافظات غير الصالحة أو غير النشطة قبل حذف إسنادات المحافظات الحالية.
- رفض معرّفات الفروع غير الصالحة أو الخارجة عن نطاق المسؤول قبل حذف إسنادات الفروع الحالية.
- إضافة اختبارات تعاقدية تثبت ترتيب التحقق قبل التغيير.
- لم يتم تشغيل قاعدة بيانات فعلية أو نشر الإصدار.

## v68.21.18 — حماية مسارات إدارة الحسابات من المعرّفات غير الصالحة

- إصلاح مسار تفعيل/تعطيل المستخدم: التحقق من وجود الحساب وإرجاع 404 بدل خطأ داخلي عند إرسال معرّف غير موجود.
- توثيق حدث التفعيل أو التعطيل بوضوح في سجل التدقيق.
- تأمين تحديث نطاق المحافظات: التحقق من وجود المستخدم وتجاهل معرّفات المحافظات غير الرقمية بدل التوقف باستثناء.
- إضافة اختبارات تعاقدية لهذه الحالات.

## v68.21.17 — إعادة التحقق من تعارض المأمورية عند الإغلاق وإعادة الفتح

- إغلاق المأمورية يعيد التحقق من وجود تاريخي البداية والنهاية وصحتهما، ثم يعيد فحص تعارض الفترة قبل تغيير الحالة.
- إعادة فتح المأمورية تعيد فحص التعارض كحركة انتداب مفتوحة قبل تعديل الحالة.
- إضافة اختبارات تعاقدية لترتيب التحقق قبل عمليات تغيير الحالة.
- لم يتم تشغيل قاعدة بيانات فعلية أو نشر الإصدار.

## v68.21.16 — إعادة التحقق عند تطبيق استيراد Excel

- إعادة التحقق من وجود ونشاط المحافظة والفرع عند تطبيق الاستيراد، وليس وقت المعاينة فقط.
- رفض تحديث موظف لم يعد موجودًا أو أصبح محذوفًا، والتحقق من الفرع الجديد قبل تطبيق التغيير المحدد.
- إعادة فحص تعارض كود شئون العاملين والبريد الإلكتروني للموظفين الجدد قبل بدء أي كتابة في قاعدة البيانات.
- إضافة اختبار تعاقدي يتحقق من أن الفحوص تسبق تغييرات الاستيراد.

## v68.21.15 — تشديد تحقق تعديل الموظف

- رفض حفظ تعديل الموظف إذا كان الفرع غير نشط أو محافظته غير نشطة، أو لم يطابق الفرع المحافظة المرسلة.
- نقل فحص تعارض بريد حساب المستخدم المرتبط إلى ما قبل تعديل كائن الموظف، لتفادي تغييرات ORM المعلقة عند رفض النموذج.
- إضافة اختبارات تعاقدية للتحقق من ترتيب الفحوص.

## v68.21.14 — حماية إغلاق الانتداب والتحقق من سجل الحركة

- معالجة تاريخ إغلاق الانتداب غير الصحيح برسالة تحقق بدل خطأ خادم.
- فحص تعارض فترة الانتداب المقترحة قبل حفظ تاريخ الإغلاق، مع استثناء سجل الانتداب نفسه من المقارنة.
- إضافة اختبار تعاقدي يثبت وجود التحقق قبل تغيير حالة الانتداب.

## v68.21.13 — توحيد التحقق من تواريخ الحركات

- جعل `validate_movement_fields` يتحقق من صلاحية التواريخ الميلادية قبل الحفظ في جميع المسارات التي تستخدمه، بما فيها فحص ما قبل الحفظ.
- مقارنة كائنات التاريخ الفعلية للتحقق من أن تاريخ البداية لا يتجاوز تاريخ النهاية، بدل الاعتماد على مقارنة النصوص.
- إضافة اختبار تعاقدي لهذا السلوك.

## v68.21.12 — رفض التواريخ غير الصالحة بأمان

- جعل فحص تعارض الحركات يعيد رسالة تحقق واضحة عند ورود تاريخ غير صالح بدل رفع `ValueError` قد يتحول إلى خطأ خادم.
- إضافة اختبار تعاقدي لتثبيت السلوك.

## v68.21.11 — منع تعارض الإذن مع الانتداب المفتوح

- إصلاح تحقق تعارض الحركات بحيث يُرفض تسجيل إذن في يوم يقع ضمن انتداب مفتوح بدأ بالفعل.
- إضافة اختبار عقدي للتحقق من استمرار هذا الشرط.

## v68.21.11 — حماية تعديل الحركة من التاريخ غير الصحيح
- إضافة معالجة صريحة لأخطاء تحليل التواريخ في مسار تعديل الحركة، قبل تعديل سجل قاعدة البيانات.
- تبقى عملية التحقق من تعارض الحركات سابقة للحفظ.

## v68.21.9 — حماية إعادة فتح المأمورية
- قُيّدت إعادة فتح المأمورية المغلقة في مسار التقارير لمسؤول التطبيق وManager Application Support، مع بقاء فحوص صلاحية الحركة ونطاقها مطلوبة.
- أُضيف اختبار عقد مصدر يراجع وجود حاجز الدور في مسار إعادة الفتح.

## v68.21.8 — movement authorization and history scope

- Require `manage_movements` as well as movement-scope authorization before the movement submit endpoint changes a record.
- Require both `view_audit` and movement visibility before returning movement history, preventing audit permission from bypassing operational scope.
- Updated package version metadata.

## v68.21.7 — closed assignment lifecycle authorization

- Restrict editing a closed assignment to application administrators and Manager Application Support.
- Restrict reopening a closed assignment to the same authorized roles.
- Keep supervisor edit/reopen paths blocked at the server, not only hidden in the UI.

## v68.21.6 — bundled authorization and search-scope fixes
- Fixed administrator permission lookup to import the permission catalog explicitly.
- Kept Home employee search global and read-only while retaining movement-picker scope rules.
- Hardened operational-scope recovery when a stale session contains a malformed governorate value.

# v68.21.4 — Explicit custom permission sets

- Fix: preserve an intentionally empty user permission set with an internal marker, rather than silently restoring role defaults.
- Backward compatibility: legacy users without permission rows continue inheriting role defaults.
- Added regression tests for legacy defaults, empty custom permissions, and partial custom permissions.

## v68.21.3 — حماية تسجيل الخروج

- تحويل تسجيل الخروج من GET إلى POST لمنع تغييرات حالة الجلسة عبر الروابط أو الطلبات العابرة للمواقع.
- إضافة رمز CSRF إلى نموذج الخروج واختبار تعاقدي للطريقة والرمز والجلسة.
- لم تتغير صلاحيات الأدوار أو بيانات قاعدة البيانات.

# Changelog

## v68.21.3 — مراجعة اتساق الإصدار والحزمة

- توحيد رقم الإصدار بين `pyproject.toml` و`employee_movements.__version__` ورابط CSS وبيان المراجعة.
- تصحيح بنية حزمة التسليم بحيث تكون ملفات المشروع في جذر ZIP مباشرة، لا داخل مجلد إضافي.
- لم تتغير قواعد الأعمال أو الصلاحيات أو قاعدة البيانات أو CSS في هذه الجولة.
- اختبارات التشغيل والمتصفح لم تُنفذ بعد؛ هذه حزمة مرشح مراجعة وليست اعتمادًا إنتاجيًا.


## v68.19.2 — Assistant launcher conflict cleanup

- Removed competing legacy assistant launcher rules that alternated between charcoal and teal backgrounds, leaving one authoritative teal launcher style. This is a concrete CSS conflict; whether it is the exact black-circle issue still requires visual confirmation in the live browser.
- Updated app/package/static asset versions to 68.19.2 for cache invalidation. No business logic, authorization rules, or production data were intentionally changed.
- Validation status: Python compilation and JavaScript syntax checks to be run on this candidate; full Flask tests and browser verification remain environment-dependent.

## v68.19.1 — Unified interface audit candidate

- Consolidate the latest unified visual layer into a single versioned CSS tail, remove a duplicated interaction-polish CSS block, and invalidate the browser cache with the matching application version.
- Keep the existing role, authorization, and data workflows unchanged in this visual candidate.
- Static validation: Python compilation and JavaScript syntax checks passed in the available environment. Full pytest/runtime/browser validation remains pending because Flask dependencies cannot be installed in this offline environment.
- This is an audit candidate, not a production-verified release.

## v68.16.1 — اتساق السيان وتحسين القراءة
- توحيد الألوان المتبقية في الجداول والنماذج والتفاعلات ومكونات المساعد مع رموز التصميم المشتركة.
- رفع وضوح رؤوس الجداول وبياناتها والتسميات وحقول البحث، مع قواعد أصغر للشاشات الضيقة.
- تحديث رابط CSS بإصدار جديد لتجاوز النسخ المخزنة مؤقتًا.
- لم تُجرَ تغييرات مقصودة على منطق العمل أو الصلاحيات أو قاعدة البيانات.

## v68.16.0 — هوية بصرية موحدة بدرجات السيان
- توحيد متغيرات التصميم الأساسية في مصدر واحد بدل جذور ألوان متعارضة موزعة داخل ملف CSS.
- اعتماد درجات السيان/التركواز للهوية الأساسية والتنقل النشط والأزرار الرئيسية والأيقونات وحالات التركيز.
- توحيد لون الخلفية والحدود والظلال وحالات التفاعل عبر البطاقات والنماذج والجداول ولوحات الإدارة والتقارير والمساعد.
- تحديث مستند نظام التصميم، لون المتصفح، وإصدار التطبيق إلى 68.16.0.
- لم يُقصد تغيير قواعد الأعمال أو الصلاحيات أو مخطط قاعدة البيانات.

## v68.15.56
- إصلاح ترتيب تجميع سياق المحادثة: حجز مساحة الرسالة الحالية أولًا، ثم إضافة أحدث رسائل المستخدم السابقة ضمن الحد المسموح.
- تطبيق السلوك نفسه في محلل النية ووكيل التنفيذ، حتى لا تؤدي الرسائل القديمة إلى اقتطاع الطلب الحالي عند بلوغ 16,000 حرف.
- استمرار استبعاد ردود المساعد التي قد تتضمن بيانات حية للموظفين أو الحركات، مع إبقاء حل الأسماء والصلاحيات محليًا.

## v68.15.55
- توسيع نافذة سياق المساعد من آخر 8 إلى آخر 20 رسالة للمستخدم في محلل النية ووكيل التنفيذ.
- رفع الحد الإجمالي للنص المرسل ضمن السياق إلى 16,000 حرف، مع استمرار استبعاد ردود المساعد المحفوظة التي قد تحتوي بيانات موظفين أو حركات.
- الإبقاء على حل الأسماء والصلاحيات وتنفيذ العمليات داخل التطبيق محليًا. هذا تحسين للاستمرارية وليس ادعاءً بفهم كامل لكل تاريخ المحادثة.

## v68.15.53
- منع المساعد الإداري من إعادة تفعيل فرع إذا كانت المحافظة التابعة له غير نشطة.
- منع نقل الموظف إلى فرع نشط شكليًا إذا كانت محافظته غير نشطة.
- تحديث اختبارات العقود لتتوافق مع فصل محللات المستخدمين وبنية التنفيذ الحالية، دون إضعاف فحوص النطاق.
- إعادة التحقق من عقود المأموريات والتقارير والمساعد والصلاحيات. لم يتم النشر ولم تُعدّل قاعدة البيانات.

## v68.15.52
- مراجعة مسار إنشاء طلبات تعديل المأمورية وتقارير المدير ونطاقها، مع تحديث اختبارات العقود.

## v68.15.51
- التأكد من أن طباعة المأمورية المفتوحة تطلب «إلى تاريخ» وتضعه في خانة التاريخ داخل PDF دون تعديل سجل الانتداب.
- إضافة اختبارات تعاقدية لمسار التاريخ واسم المنشئ/المغلق، وتصحيح اختبار التصدير ليتوافق مع الاسم المستعار الفعلي.

## v68.15.50
- طباعة اسم واحد فقط في خانة الاسم الموجودة أعلى اليمين: منشئ المأمورية عند كونها مفتوحة، ومن أغلقها عند كونها مغلقة.
- إزالة سطر «أُغلقت بمعرفة» الإضافي مع الحفاظ على بقية النموذج كما هي.

# سجل التغييرات

## v68.15.40
- تشديد التحقق من أن فرع الموظف نشط وأن محافظته نشطة قبل تسجيل حركة جديدة.
- التحقق من نشاط محافظة وجهة الانتداب داخل قاعدة الصلاحيات نفسها، وليس في واجهة الاختيار فقط.
- لا يقيّد ذلك الانتداب بين المحافظات النشطة؛ بل يمنع استخدام فروع أو محافظات غير نشطة.
- إضافة اختبارات تعاقدية مركزة للتحقق من هذه القواعد.

# سجل التغييرات

## v68.15.37 — المأموريات عبر جميع المحافظات
- إزالة بوابة اختيار محافظة العمل من صفحات البحث والطباعة الخاصة بالمأموريات.
- الإبقاء على التحقق المركزي من صلاحية طباعة المأمورية عبر `can_print_mission`.
- لم تتغير صلاحيات التعديل أو الإغلاق، ولم تتغير قاعدة البيانات أو إعدادات النشر.
- أضيف اختبار تعاقدي لمنع عودة اشتراط محافظة العمل لمسارات الطباعة الشاملة.

## v68.15.38 — Mission filter integrity
- Mission report branch filters now include only active branches under active governorates.
- Preserved global mission search for authorized roles and the existing separation between print and mutation permissions.
- Added static contract tests for these rules.


## v68.15.39 — Cross-governorate assignment workflow consistency
- Fixed Manager Application Support assignment filter API so assignment employee/branch selection can span active governorates, matching the established global assignment workflow.
- Kept leave and permission selection restricted to the operational scope for non-admin roles.
- Filtered global branch options against active parent governorates to avoid selecting branches under inactive governorates.
- Added a static contract test for Manager assignment picker scope.
- Not deployed; no database or hosting configuration changed.

## v68.15.41 — Home workflows cross-governorate contract audit

- Added `scripts/check_home_workflow_contracts.py`, a dependency-free audit covering Home employee search, assignment destination selection, active branch/governorate validation, cross-governorate mission filters, printing permissions, and closed-mission edit restrictions.
- This package does not change the production database or deployment settings.
- Static source checks do not replace authenticated browser tests against a running Flask app.

## v68.15.42
- Removed the leftover selected-work-governorate gate from the global mission report template.
- Enabled branch filters across all active governorates, even when no governorate filter is selected.
- Added governorate labels to branch filter options to distinguish branches with identical names.
- Added regression checks for global mission report scope and filter usability.


## v68.15.43 — اتساق البحث والتصدير
- إصلاح فلتر التاريخ ليشمل المأموريات المفتوحة التي لا تحتوي على تاريخ نهاية.
- توحيد مصدر نتائج شاشة المأموريات وتصدير Excel، حتى يحترم الملف جميع الفلاتر نفسها ونطاق الصلاحيات نفسه.
- جعل رابط Excel يحتفظ بفلاتر المحافظة والفرع وجهة المأمورية والموظف والحالة والتواريخ والمدة.
- إضافة اختبارات تعاقدية لمنع عودة اختلاف النتائج بين الشاشة والتصدير.
- لم يتم تغيير قاعدة البيانات أو إعدادات النشر.


## v68.15.44 — نطاق المأموريات للـManager
- إصلاح نطاق صفحة متابعة الحركات: إظهار الانتدابات والمأموريات من جميع المحافظات للـManager كما هو متفق عليه.
- إبقاء الإجازات والأذونات ضمن نطاق الفروع التشغيلية المحدد.
- إظهار خيارات المحافظات العالمية في فلتر الصفحة للـManager.
- إضافة اختبارات انحدار تمنع رجوع اختلاف النطاق بين عرض المأموريات وفلاترها.
