# خريطة أوراق التصميم — v68.24.0

- `static/css/app.css`: إطار التطبيق المشترك، الرأس والقائمة الجانبية ورموز التصميم والقواعد العامة والاستجابة. خضع لتدقيق مراجع محافظ قبل إزالة المحددات القديمة غير المستخدمة.
- `static/css/pages/home.css`: الصفحة الرئيسية، يُحمّل فقط عند `request.path == '/'`.
- `static/css/pages/employee-directory.css`: دليل الموظفين، يُحمّل فقط عند `request.path == '/employees'`.
- `static/css/pages/movement-forms.css`: تسجيل/عرض الحركات وتعديل الحركة وتعديل المأمورية ومراجعة طلبات تعديلها؛ يُحمّل لمسارات `/movements*` و`/reports/assignments/mission-edit*` و`/reports/assignments/edit-requests*`.
- `static/css/pages/management.css`: الإدارة وبنية العمل والمستخدمون وتحرير المستخدمين والتفويضات؛ يُحمّل لمسارات `/structure*` و`/users*` و`/delegations*`.

تُحمّل أوراق الصفحات بعد `app.css` حتى تستخدم رموز التصميم العامة وتخصص محتواها دون نسخ الإطار المشترك. تفاصيل طريقة تدقيق التنظيف وحدود التحقق موضحة في `MANAGEMENT_REDESIGN_v68.24.0.md`.
