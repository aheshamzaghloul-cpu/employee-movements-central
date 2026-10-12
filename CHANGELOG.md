# v68.22.44

- ربط متغيرات الألوان القديمة المستخدمة في المكونات بمتغيرات نظام التصميم الحالي، لتقليل اختلاف الألوان الناتج عن fallback مستقل.
- توحيد لون التركيز وعناصر التحكم مع اللون الأساسي الحالي، دون تغيير منطق الصفحات أو الصلاحيات.
- إضافة تقرير تدقيق للمكونات المشتركة وحدود الاختبار.

# v68.22.43

- مراجعة تفصيلية لواجهة التفويض: توحيد بطاقات إنشاء التفويض وملخص الحالات وسجل التفويضات.
- تحسين أحجام حقول التاريخ والاختيارات وأدوات البحث وأزرار تصفية السجل.
- تحسين التفاف الأسماء الطويلة وأسباب الإلغاء، وتخطيط الصفحة على الأجهزة اللوحية والهواتف.
- إضافة حالات تركيز واضحة واحترام تفضيل تقليل الحركة.
- لا تغيير في منطق التفويض أو الصلاحيات أو قاعدة البيانات أو إجراءات الإلغاء.

# v68.22.42

- استكمال تدقيق واجهة إدارة المستخدمين: تحسين بطاقات الهوية والأدوار والنطاقات والتكليفات.
- تحسين التفاف النصوص الطويلة وعناصر الأدوار، وتخطيط إجراءات البطاقة على الشاشات الصغيرة.
- تحسين أدوات البحث أعلى جدول الحسابات، ووضوح عناصر كلمة المرور وإجراءات الصفوف.
- تحسين تخطيط مراحل تعديل المستخدم والتركيز بلوحة المفاتيح، مع احترام تفضيل تقليل الحركة.
- توحيد رقم الإصدار بين VERSION.md ونسخة التطبيق ومرجع CSS.
- لا تغيير في منطق الصلاحيات أو قاعدة البيانات أو إجراءات المستخدمين.

# v68.22.40

- استكمال تنسيق مكونات ملف الموظف التي كانت بلا قواعد CSS مباشرة: التواصل، والسياق التنظيمي، وملخص الحركة.
- إضافة حالة مرئية موحدة لزر التنقل الشفاف ui-btn-ghost.
- تحسين التفاف أرقام الهواتف والبريد وأسماء الفروع، وتخطيط التواصل على الهاتف.
- لا تغيير في منطق Flask أو الصلاحيات أو قاعدة البيانات.

## v68.22.39 — تدقيق تصميم دليل الموظفين

- إضافة قواعد CSS صريحة لعناصر دليل الموظفين التي كانت مستخدمة في قالب employees.html دون تعريف مباشر واضح.
- توحيد بطاقات المحافظات والفروع وصفوف الموظفين وحالة الحركة والإجراءات الإضافية.
- تحسين البحث والتصفية بصريًا، ونموذج إضافة الموظف، وحالات النتائج الفارغة.
- تحسين التخطيط للشاشات المتوسطة والصغيرة وإضافة دعم تقليل الحركة.
- لا تغييرات في منطق Flask أو قاعدة البيانات أو الصلاحيات أو تدفق البحث.

## v68.22.33 — مطابقة الموظفين بكود الفرع أولًا

- إضافة عمود كود الفرع إلى مطابقة أعمدة استيراد الموظفين تلقائيًا.
- اعتماد كود الفرع النشط والفريد كمرجع أساسي حتى لو اختلفت كتابة اسم الفرع أو المحافظة في ملف Excel.
- عند تكرار كود الفرع، لا يتم التخمين؛ تُستخدم المحافظة/الاسم لفك الالتباس، وإلا يظهر خطأ واضح.
- استمرار دعم الملفات القديمة التي لا تحتوي على كود فرع عبر مطابقة المحافظة والاسم بعد التطبيع.
- ربط الموظف بالمحافظة المسجلة فعليًا على الفرع المحسوم بالكود.

## v68.22.32 — إصلاح استيراد الموظفين مع بيانات اتصال اختيارية
- جعل البريد الإلكتروني وهاتف الشركة والهاتف الشخصي حقول اتصال اختيارية في معالج استيراد الموظفين، مع الاستمرار في التحقق من البريد إذا أُدخل.
- أبقى المحافظة والفرع واسم الموظف والوظيفة والكود الوظيفي وتاريخ التعيين حقولًا أساسية.
- منع تكرار الكود الوظيفي أو البريد داخل الملف قبل الاعتماد، مع توضيح الخطأ ورقم الصف.
- جعل إعادة التحقق عند الحفظ تسمح ببريد فارغ، مع استمرار فحص تعارض الكود الوظيفي والبريد الموجودين في قاعدة البيانات.
- لا تغييرات على قاعدة البيانات أو بيانات الإنتاج، ولم يتم النشر. يلزم اختبار استيراد فعلي داخل التطبيق بعد رفع الحزمة.

## v68.22.30 — تدقيق نقاط التوقف المتجاوبة
- توثيق تداخل مجموعات media queries الخاصة بالتخطيط لتجنب حذف قواعد قد تكون لازمة دون اختبار بصري.
- تحديث نسخة تحميل CSS.
- لا تغييرات على منطق التطبيق أو الصلاحيات أو قاعدة البيانات.

## v68.22.29 — تصحيح بنية حزمة التسليم
- إعادة تجهيز ملف ZIP من جذر المشروع الصحيح بدل تضمين مجلدات العمل المتداخلة في مسار الاستخراج.
- لا تغييرات على منطق التطبيق أو الصلاحيات أو قاعدة البيانات.
- تحديث رقم الإصدار ووسم ذاكرة CSS المؤقتة.

## v68.22.28 — تنظيف تكرار خلفية HTML
- حذف تصريح `html{background:var(--ui-page)}` المكرر خارج أي media query؛ توجد قاعدة HTML عامة سابقة تحمل الخلفية نفسها.
- لم تتغير قواعد الاستجابة أو أحجام العناصر أو منطق التطبيق؛ التغيير تنظيمي فقط.
- تحديث إصدار CSS cache وتقرير المراجعة.
- لا يُعد هذا إثباتًا للاعتماد البصري؛ يلزم اختبار المتصفح والتشغيل الفعلي.

## v68.22.27 — تدقيق التكرارات الآمن لقواعد SVG
- حذف تصريح CSS واحد مكرر حرفيًا لسلوك `fill` على SVG المعبأة؛ القاعدة السابقة تغطي العنصر الجذر والعناصر الداخلية بالفعل.
- تدقيق تكرارات المحددات في بقية الملف؛ لم تُحذف القواعد التي تتكرر عبر media queries أو تختلف في ترتيبها/سياقها.
- تحديث نسخة cache وإصدار المراجعة. لا تغييرات في منطق العمل أو الصلاحيات أو قاعدة البيانات.
- الفحوصات الثابتة مطلوبة بعد التعديل؛ الاختبار البصري وتشغيل Flask ما زالا غير منفذين.

## v68.22.26 — حماية الأيقونات المعبأة من قواعد SVG العامة
- تضييق قواعد الأيقونات الخطية المشتركة بحيث تستثني SVG التي تحمل `data-icon-fill` على العنصر الجذر، بما يشمل قواعد العناصر الداخلية.
- الهدف منع قواعد الأيقونات الخطية من تحويل الأيقونات المعبأة عمدًا إلى حدود فارغة أو التأثير على مظهرها.
- لم يتغير منطق التطبيق أو الصلاحيات أو قاعدة البيانات.
- فحوصات التشغيل الفعلية والمتصفح ما زالت مطلوبة؛ لم يتم النشر.

## v68.22.25 — تنظيف آمن للتكرارات المؤكدة في CSS
- حذف كتلة أدوات مساعدة مكررة كانت موجودة قبل الكتلة اللاحقة المكافئة، مع الإبقاء على الكتلة اللاحقة التي تحمل نفس القواعد.
- حذف استعلام وسائط فارغ عند 700px لا يحتوي أي قواعد.
- عدم حذف تكرارات أخرى تلقائيًا؛ ما زالت تحتاج مراجعة سياق الصفحة وترتيب التتالي.
- تحديث إصدار CSS cache وبيانات الإصدار وتقرير المراجعة.

## v68.22.24 — إصلاح حتمي لأيقونات الرئيسية وتدقيق CSS
- تثبيت مساحة أيقونتي البحث والطباعة في الرئيسية بأبعاد صريحة لمنع تمددهما إلى دوائر/أشكال سوداء كبيرة.
- فرض نمط outline على SVG داخل حاوية أيقونات الإجراءات الرئيسية، مع الحفاظ على أبعاد أيقونة رابط الطباعة.
- تحديث رقم cache لملف CSS.
- إضافة تقرير تدقيق يوضح حجم التكرار في CSS؛ لم تُحذف قواعد متكررة تلقائيًا لأن ترتيبها وسياق media قد يغيران السلوك.

## v68.22.21 — Shared layout foundation and SVG normalization
- Added a shared content-width and overflow foundation for admin, login, home, employee, movement, and report surfaces.
- Applied line-icon defaults to inline SVGs inside buttons, links, labels, and role=button controls, while allowing explicit data-icon-fill opt-out.
- Added responsive content-width behavior for wide and narrow screens.
- Static validation only; browser visual inspection and Flask runtime/database tests remain pending. Not deployed.

## v68.22.17 — Unified cross-page visual contract
- Added an authoritative shared visual layer for shell, typography surfaces, buttons, controls, tables, and responsive layouts.
- Normalized design tokens and corrected field behavior for textarea, checkbox, radio, and file inputs.
- Bumped CSS cache version in base template.
- Static checks only; visual browser review and full Flask runtime tests remain pending.

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


## v68.22.14 — توحيد تمهيدي لقواعد الخط الأساسية

- توحيد قاعدة body الأساسية مع الحجم والخط المستخدمين في طبقة التصميم المعتمدة (Cairo، 14px، line-height 1.65).
- إزالة التصريح المتأخر المكرر لخصائص body بعد توحيدها، مع الإبقاء على خلفية الصفحة النهائية.
- الاحتفاظ بإصلاح نطاق استيراد Excel لمسؤول التطبيق من الإصدار السابق.
- هذه خطوة تنظيف محدودة وليست إعادة بناء كاملة لملف CSS؛ لا تزال هناك قواعد متراكمة تحتاج إلى مراجعة آمنة لكل مكوّن.
- فحوص المصدر والعقود ناجحة؛ اختبارات Flask التشغيلية لم تُشغّل لغياب Flask عن بيئة المراجعة. لم يتم النشر أو تعديل قاعدة الإنتاج.


## v68.22.15 — توحيد رموز الخلفية وإزالة تعارض الخط العام
- توحيد خلفية الصفحة بين `--ui-bg` و`--ui-page` حتى لا تختلف صفحات الواجهة القديمة والحديثة في لون الخلفية الأساسي.
- إزالة تعريفات `body` العامة المتكررة والمتعارضة، والإبقاء على تعريف أساسي واحد للخط والحجم وتباعد الأسطر.
- لم تُحذف قواعد المكونات المتخصصة أو قواعد `!important` بصورة آلية؛ يلزم فحص بصري وتشغيلي قبل إزالة هذه الطبقات بأمان.
- اختبارات التشغيل الكامل ما زالت غير متاحة في بيئة لا تحتوي على Flask ولا تستطيع تثبيت المتطلبات من الشبكة.


## v68.22.16 — توحيد قواعد حقول الإدخال
- إزالة ثلاث مجموعات عامة متنافسة لتنسيق `input` و`select` و`textarea` كانت تختلف في الحدود والارتفاعات والألوان وخصائص `!important`.
- إضافة قاعدة مشتركة واحدة تعتمد على رموز التصميم للألوان والحدود والتركيز، مع الحفاظ على استثناءات checkbox وradio.
- هذا توحيد لطبقة الحقول فقط؛ لم تُحذف قواعد المكونات المتخصصة، ولم يُدّعَ اكتمال توحيد كل الصفحات.
- يلزم اختبار بصري وتشغيلي للصفحات والنماذج؛ لا نشر ولا تعديل لقاعدة الإنتاج.


## v68.22.18 — تحسين الاستجابة للنماذج والجداول
- ضبط تخطيطات النماذج والفلاتر للشاشات المتوسطة حتى لا تُضغط الحقول العربية في أعمدة ضيقة.
- تحويل مجموعات النماذج التشغيلية إلى عمود واحد على الشاشات الصغيرة، مع التفاف أزرار الإجراءات.
- تعزيز تمرير الجداول داخل حاوياتها على الهواتف دون توسيع الصفحة أفقيًا.
- توحيد مؤشر التركيز المرئي للتنقل بلوحة المفاتيح.
- التغيير لا يحذف قواعد CSS القديمة؛ يحتاج اختبارًا بصريًا بالمتصفح، ولم يتم النشر أو تعديل قاعدة الإنتاج.


## v68.22.19 — Import branch matching and icon rendering
- Employee Excel import now resolves a registered active branch by either its name or its registered code, while retaining the governorate key and active-branch/admin scope checks.
- Applied a targeted outline-SVG style to common home/action icon containers to prevent browser default black fills from rendering outline icons as solid black shapes.
- Static/runtime limits: Flask integration and browser screenshot verification were not available in this environment; this release is not deployed.

## v68.22.20 — Cross-page UI consistency
- Added shared design tokens and consistent surfaces for administration, login, reports, employee search, and movement workflows.
- Unified line-icon SVG rendering across navigation, action buttons, cards, login, and print shortcut to prevent default solid-black icon fills.
- Improved responsive administration grids and compact mobile layout.
- Bumped CSS cache version.
- Excel import remains unverified against live production records; no deployment or database changes were made.


## v68.22.22 — Excel key normalization and icon fill fix
- Normalize Arabic-Indic and Persian digits to Western digits for Excel lookup keys; normalize numeric code strings such as `255.0` to `255`.
- Prevent default SVG child fills from turning outline icons into solid black shapes; provide an explicit `data-icon-fill` opt-in for intentionally filled icons.
- Bumped CSS cache version.
- Static checks only: browser rendering and live Excel import against production records remain unverified; not deployed.


## v68.22.23 — توحيد بصري شامل للواجهة

- توحيد رموز الألوان والخلفيات والحدود والظلال ونصف قطر البطاقات وحقول الإدخال في طبقة تصميم مشتركة.
- توحيد مظهر القائمة الجانبية والشريط العلوي وصفحة تسجيل الدخول مع بقية التطبيق.
- تثبيت أسلوب أيقونات SVG الخطية دون فرض تعبئة على الأيقونات المعلّمة صراحةً كممتلئة.
- تحسين الاستجابة على الشاشات الصغيرة واحترام إعداد تقليل الحركة.
- توحيد رقم الإصدار في التطبيق وبيانات الحزمة ورابط CSS. لم تتغير قواعد العمل أو الصلاحيات ولم يُجرَ نشر أو تعديل لقاعدة الإنتاج.
- فحوصات ثابتة فقط؛ لا تزال معاينة المتصفح واختبارات Flask runtime غير متاحة في بيئة المراجعة الحالية.

## v68.22.31 — Responsive Rule Safety Audit
- Audited repeated mobile breakpoints (600px, 700px, 900px) and preserved page-specific rules where declarations differ.
- Removed an empty 700px media block only if present; no functional declarations were changed.
- Added a responsive audit report; browser-based visual QA remains pending.

## v68.22.34 — توحيد تصميم صفحة الإدارة
- إضافة نظام CSS كامل ومحدد لصفحة الإدارة التي كانت تستخدم أصناف admin-ai دون تعريفات تصميم مقابلة.
- توحيد أحجام العناوين والنصوص والبطاقات والأزرار والمسافات والحدود والألوان مع متغيرات التصميم المشتركة.
- ضبط شبكة المؤشرات والأدوات وسجل التدقيق لتستجيب للشاشات المتوسطة والصغيرة.
- تحديث إصدار CSS لمنع المتصفح من استخدام النسخة المخزنة مؤقتًا. لم تتغير مسارات الأعمال أو الصلاحيات.

## v68.22.35 — Employee profile visual completion
- Added a complete responsive visual layer for employee profile header, status, facts, movement summaries/history, contact details, organizational context, and primary action.
- Updated CSS cache-buster. No route, authorization, data model, or workflow logic changed.
- Automated syntax/contract checks run; real browser visual verification remains pending.

## v68.22.36 — Homepage typography and component normalization
- Replaced undersized table and status-chip typography with readable sizes across the application.
- Added a coherent responsive layout for the current smart-home template: direct actions, movement registration, status metrics/list, first-entry directory, quick tools, and governorate scope gate.
- Corrected homepage helper/section text sizes that had been set as small as 9–10px.
- No Flask routes, authorization checks, data models, or movement rules changed. Browser-based visual QA is still pending.

## v68.22.37 — تحسين واجهة تسجيل الحركة
- إضافة تنسيق مفقود لشريط خطوات تسجيل الحركة وملخص المراجعة.
- تحسين التركيز بلوحة المفاتيح والتوافق مع الشاشات الصغيرة.
- لم يتغير منطق الأعمال أو الصلاحيات أو قاعدة البيانات.


## v68.22.38 — تحسين وضوح صفحة التقارير
- رفع أحجام النصوص الصغيرة في عنوان مركز التقارير ووصفه وبطاقات التقارير والإحصاءات.
- توحيد المسافات والأيقونات والحدود وحالات التفاعل في بطاقات التقارير.
- تحسين تخطيط التقارير للأجهزة اللوحية والهواتف ومنع ضغط النصوص الطويلة.
- لا تغييرات في مسارات التطبيق أو قواعد العمل أو الصلاحيات أو قاعدة البيانات.
- الفحص البصري داخل متصفح حي ما زال غير منفذ في بيئة العمل الحالية.


## v68.22.41 — تحسين قابلية استخدام عناصر الإجراءات الصغيرة
- رفع الحد الأدنى لارتفاع أزرار الإجراءات المدمجة على الشاشات الصغيرة لتقليل صعوبة الضغط عليها.
- إضافة مؤشر تركيز واضح ومتسق لعناصر قوائم الإجراءات وأزرار الصفوف عند استخدام لوحة المفاتيح.
- التعديل محصور في طبقة العرض؛ لم تتغير مسارات التطبيق أو قواعد البيانات أو الصلاحيات.
- لم يُجر اختبار بصري داخل متصفح حي ولم يتم النشر.
