# v49.25 — إصلاح UndefinedError في صفحة الإدارة

## الإصلاح
تم إصلاح خطأ Jinja التالي الذي كان يمنع فتح «الإدارة»:

`jinja2.exceptions.UndefinedError: 'actual_roles' is undefined`

السبب أن `actual_roles()` موجودة في `app.py` وتستخدم داخل القوالب، لكنها لم تكن مسجلة ضمن globals الخاصة بـ Jinja.

تم تسجيلها صراحةً:

`app.jinja_env.globals['actual_roles'] = actual_roles`

## التحقق
- Python compileall: ناجح.
- فحص Jinja لجميع القوالب: ناجح (35 قالبًا).
- استيراد التطبيق: ناجح.
- التحقق من تسجيل `actual_roles` في Jinja: ناجح.

## ملاحظة
لم يتم تغيير منطق الأدوار أو بيانات النظام؛ الإصلاح خاص بإتاحة الدالة للقالب.
