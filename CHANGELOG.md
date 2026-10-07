# CHANGELOG

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
