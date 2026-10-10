# Version

**v68.16.0 — Unified cyan visual system**

- تحديث الهوية البصرية الموحدة إلى درجات السيان/التركواز الهادئة عبر الألوان الأساسية والمكونات المشتركة.
- توحيد مظهر التنقل والبطاقات والأزرار والنماذج والجداول وحالات التركيز والإجراءات التفاعلية باستخدام رموز التصميم المشتركة.
- تحديث لون المتصفح وتغيير رابط ملف CSS بإصدار جديد لتقليل احتمال عرض تصميم مخزّن مؤقتًا.
- توثيق قواعد التصميم الموحد دون تغيير قواعد الأعمال أو الصلاحيات عمدًا.

**v68.15.56 — Preserve current request in packed context**

- Fix context packing so the current user request is always reserved first; when the character budget is reached, retain the newest prior user turns instead of allowing old context to truncate the current request.
- Apply the same newest-first budget policy to the intent parser and action agent. Continue excluding assistant replies that may contain live employee or movement information.
- Keep entity resolution and authorization local. This improves continuity but is not full conversation summarization.

## v68.15.53 — Assistant scope and execution hardening

Includes the v68.15.52 mission request/report contract review and hardens assistant operations so a branch cannot be reactivated under an inactive governorate and an employee cannot be reassigned to a branch whose governorate is inactive. Updates static contracts to follow the current resolver/module structure. No deployment or database changes were made.

## v68.15.51
- عند طباعة مأمورية مفتوحة، يلزم إدخال «إلى تاريخ» ويُطبع التاريخ داخل الخانة الحالية دون حفظه على سجل الانتداب.
- تصحيح اختبار عقد تصدير المأموريات ليتوافق مع اسم الدالة المستعار المستخدم فعليًا.
- الإبقاء على اسم واحد أعلى اليمين: المنشئ للمفتوحة، والمغلق للمغلقة.

## v68.15.50
- المفتوحة: يظهر اسم منشئ المأمورية في خانة الاسم أعلى اليمين.
- المغلقة: يُستبدل الاسم في الخانة نفسها باسم من أغلق المأمورية.
- إزالة سطر «أُغلقت بمعرفة» الإضافي دون تغيير مواضع أو محتوى النموذج الآخر.
- تحديث الاختبار التعاقدي لمنع تكرار الاسم أو إضافة سطر إغلاق منفصل.


**v68.15.48 — Mission closure attribution on print form**

Records the account that closes a mission, clears the active closure attribution when reopened, and prints the closer's full name on the mission form (separate from the mission creator). Manager resolution that closes a mission records the resolving account too.


## v68.15.48
- حفظ اسم المستخدم الذي أغلق المأمورية وتاريخ الإغلاق، وإعادة ضبطهما عند إعادة فتحها.
- إظهار اسم القائم بإغلاق المأمورية في نموذج الطباعة، دون الخلط بينه وبين منشئ المأمورية.
- تطبيق التتبع نفسه عند إغلاق المأمورية من خلال تنفيذ طلب تعديل بواسطة الإدارة.
- إضافة اختبارات تعاقدية لتوثيق اسم القائم بالإغلاق ومسار الطباعة.



**v68.15.47 — Cross-governorate assignment search clarity**

Fixes a scope mismatch on the movement monitoring page: Manager Application Support now sees cross-governorate assignment/mission rows and global governorate filter choices, while leave and permission records remain restricted to the selected operational branch scope. Adds regression contracts for this distinction.


## v68.15.47
- إظهار محافظة جهة الانتداب بجوار اسم الفرع في ملخص البحث العام، لتجنب الالتباس بين الفروع المتشابهة الأسماء في محافظات مختلفة.
- إضافة اختبار تعاقدي لعرض اسم محافظة الوجهة في نتيجة الانتداب.

## v68.15.46
- توحيد البحث العام عن الموظف مع تقارير المأموريات: استبعاد الموظفين التابعين لمحافظات غير نشطة حتى لو ظل الفرع مفعّلًا بالخطأ.
- إضافة اختبار تعاقدي يمنع ظهور موظفي المحافظات غير النشطة في البحث العام.

## v68.15.45

Fixes a validation mismatch that could reject a cross-governorate assignment after the destination branch had already passed role-aware authorization. The home preflight, home creation, and movement edit routes now pass an explicit validated-destination flag only after their authorization checks; the validator keeps its default branch-scope enforcement for other callers. Movement editing now also checks destination authorization directly. Added regression contract tests.
