# خريطة التصميم وتغطية الصفحات — v68.42.0

## المرحلة الأولى: الإطار العام والرئيسية وتسجيل الدخول

### ما جرى تعديله
- توحيد رموز التصميم في `employee_movements/static/css/design-system-cyan.css` ضمن كتلة `:root` واحدة، بما يشمل السماوي المائل للأزرق، والأزرق الداكن المحدود، والخلفيات والحدود والظلال وأبعاد المكونات.
- تنظيم القائمة الجانبية في `templates/base.html` ضمن مجموعات التنقل الأساسية، والتقارير/المتابعة، وإدارة النظام.
- تحسين محدد محافظة العمل في الشريط العلوي مع المحافظة على شروط `scope_required` ونطاق المحافظات المتاح؛ خيار المحافظة الحالية يستخدم معرّفها الفعلي.
- تحسين عرض أدوات الشريط العلوي على الهاتف بدل إخفائها بالكامل.
- إزالة تكرار اسم محافظة العمل من سياق الرئيسية؛ الاختيار الفعلي يظل في الشريط العلوي.
- توحيد علامة شاشة الدخول مع علامة التطبيق، وربط حقول الدخول بتسمياتها دلاليًا وإضافة ملاحظة صلاحيات.
- إضافة عقود اختبار للنسخة `68.42.0`.

## توزيع التنسيقات
- `/` — `app.css` + `pages/home.css` + `design-system-cyan.css`.
- `/login` — `app.css` + `design-system-cyan.css`.
- `/employees` — `app.css` + `pages/employee-directory.css` + `design-system-cyan.css`.
- `/movements*` وصفحات تعديل الحركة — `app.css` + `pages/movement-forms.css` عندما يطابق المسار + `design-system-cyan.css`.
- `/structure*`, `/users*`, `/delegations*` — `app.css` + `pages/management.css` + `design-system-cyan.css`.
- `/branches*`, `/governorates*`, `/lookups*`, `/excel-import*`, `/reports*`, `/reports-missions*`, `/manager*`, `/audit*`, `/notifications*`, `/change-password*`, `/replacement*`, `/employee/*`, `/employees/*`, `/missions/*` — `app.css` + `pages/workspace-pages.css` عند مطابقة المسار + `design-system-cyan.css`.
- `design-system-cyan.css` هو آخر ملف CSS في القالب الأساسي ويحتوي على قواعد الهوية المشتركة؛ لكن وجوده لا يثبت وحده أن كل صفحة قد عُوينت بصريًا.
- نماذج الطباعة المستقلة تحتفظ بتنسيقاتها الرسمية.

## التحقق وحدوده
اختبارات العقود وتحليل Jinja وCSS وJavaScript اجتازت الفحص. لم تكتمل لقطة Chromium أو اختبارات Flask الحية في هذه البيئة؛ لذلك يجب مراجعة جميع الصفحات على متصفح متصل بالتطبيق قبل إعلان اكتمال المشروع.
