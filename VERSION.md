# v32.5-FINAL-AUTO-APPROVER

- Dropdown-first selection controls for multi-choice fields.
- Designated approver is mandatory and can be changed before approval, including after submission, with audit history.
- User accounts include job code for Application Administrator, Governorate Supervisor, and First-level Entry roles.
- Employee registration no longer asks for employee code; job code remains required.
- Lighter professional blue-gray application background.
- Required-field validation reinforced server-side and client-side.
- Existing employee_code column remains only for legacy compatibility; new employee records do not populate it.


## v32.5-FINAL-AUTO-APPROVER
- تعيين المعتمد تلقائيًا حسب تبعية الموظف لمحافظة الفرع.
- المدخل الأول يوجّه تلقائيًا إلى مشرف المحافظة المسؤول.
- منع اختيار/تغيير المعتمد يدويًا في واجهات تسجيل وتعديل الحركة.
- الاحتفاظ باسم المعتمد ظاهرًا أثناء المراجعة وبعد التقديم والاعتماد.
- منع اعتماد المشرف لحركته بنفسه؛ يستخدم مسؤول التطبيق كبديل عند الحاجة.
