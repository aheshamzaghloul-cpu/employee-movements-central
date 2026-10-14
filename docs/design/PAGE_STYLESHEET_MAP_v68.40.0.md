# خريطة تغطية التصميم — v68.40.0

## مبدأ التحميل
كل صفحة تفاعلية تمتد من `templates/base.html` تحمل `static/css/design-system-cyan.css` بعد ملف الواجهة الأساسي وأي ملف CSS متخصص. بذلك تكون طبقة التصميم الأخيرة هي المرجع النهائي للألوان، والحقول، والبطاقات، والجداول، وحالات التركيز والتفاعل.

## تغطية الصفحات
- `/` : `app.css` + `pages/home.css` + طبقة التصميم المشتركة.
- `/employees` : `app.css` + `pages/employee-directory.css` + طبقة التصميم المشتركة.
- `/employees/*` و`/employee/*` : `app.css` + `pages/workspace-pages.css` + طبقة التصميم المشتركة.
- `/movements*` : `app.css` + `pages/movement-forms.css` + طبقة التصميم المشتركة.
- `/structure*` و`/users*` و`/delegations*` : `app.css` + `pages/management.css` + طبقة التصميم المشتركة.
- `/branches*` و`/governorates*` و`/lookups*` و`/excel-import*` و`/reports*` و`/reports-missions*` و`/manager*` و`/audit*` و`/notifications*` و`/change-password*` و`/replacement*` : `app.css` + `pages/workspace-pages.css` + طبقة التصميم المشتركة.
- `/missions/*` : تمت إضافتها إلى `pages/workspace-pages.css`، بما في ذلك `/missions/from-screenshot`، مع بقاء ضبط رفع المرفق والمرشحين داخل طبقة التصميم المشتركة.
- `/login` وباقي الصفحات التي لا تحتاج إلى ملف صفحة خاص: `app.css` + طبقة التصميم المشتركة.

## استثناءات مقصودة
`assignment_form.html` و`mission_print.html` مستندان مستقلان للطباعة الرسمية، فلا يحمّلان إطار التطبيق التفاعلي أو الظلال والألوان المخصصة للشاشات. هذا يحمي مخرجات الطباعة من تغيير شكل النموذج الرسمي. الملفات الجزئية مثل `assistant_panel.html` و`workspace_actions.html` تُضمَّن داخل الصفحات ولا تمثل صفحات مستقلة.

## تدقيق البقايا القديمة
أُضيفت متغيرات توافق للأسماء القديمة، وأعيد ضبط عناصر دليل الموظفين، واختيارات الإدارة، ورفع المرفق، والمساعد إلى نفس السماوي المائل للأزرق. اختبار `contract_tests/test_full_app_design_coverage_v68_40_0.py` يؤكد استمرار هذه التغطية.
