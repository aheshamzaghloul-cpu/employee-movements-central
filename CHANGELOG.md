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
