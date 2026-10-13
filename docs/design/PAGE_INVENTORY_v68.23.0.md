# فهرس الصفحات والقوالب — v68.23.0

عدد القوالب المفحوصة: **45**. يتضمن الفهرس أعداد الحقول والنماذج والأزرار والجداول، والقوالب الأب، والملفات التي تستدعي `render_template` مباشرة عندما يمكن اكتشاف ذلك نصيًا.

## توزيع القوالب

- **التقارير والطباعة:** 10
- **الإدارة والصلاحيات:** 9
- **الموظفون:** 7
- **الحركات والنماذج:** 6
- **المساعد الذكي:** 4
- **الرئيسية ومركز العمل:** 4
- **حساب وتوثيق:** 3
- **الإطار والتنقل:** 2

## الفهرس التفصيلي

| القالب | المجموعة | الأب | نماذج | حقول إدخال | قوائم | أزرار | جداول | ملفات العرض المباشر |
|---|---|---|---:|---:|---:|---:|---:|---|
| `assignment_form.html` | الحركات والنماذج | `—` | 0 | 0 | 0 | 2 | 1 | movements.py |
| `assistant.html` | المساعد الذكي | `base.html` | 3 | 5 | 0 | 7 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `assistant_dock.html` | المساعد الذكي | `—` | 1 | 3 | 0 | 3 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `assistant_embed.html` | المساعد الذكي | `base.html` | 3 | 5 | 0 | 12 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `assistant_panel.html` | المساعد الذكي | `—` | 1 | 2 | 0 | 4 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `audit.html` | الإدارة والصلاحيات | `base.html` | 0 | 0 | 0 | 0 | 1 | reports.py |
| `base.html` | الإطار والتنقل | `—` | 3 | 4 | 2 | 12 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `branches.html` | الإدارة والصلاحيات | `base.html` | 4 | 9 | 2 | 4 | 1 | catalog.py |
| `change_password.html` | حساب وتوثيق | `base.html` | 1 | 4 | 0 | 1 | 0 | auth.py |
| `delegations.html` | الحركات والنماذج | `base.html` | 2 | 6 | 3 | 6 | 1 | delegations.py |
| `employee.html` | الموظفون | `base.html` | 0 | 1 | 0 | 4 | 0 | employees.py |
| `employee_deleted.html` | الموظفون | `base.html` | 1 | 1 | 0 | 1 | 1 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `employee_edit.html` | الموظفون | `base.html` | 1 | 8 | 2 | 1 | 0 | employees.py |
| `employee_edit_data.html` | الموظفون | `base.html` | 1 | 1 | 0 | 1 | 1 | employees.py |
| `employee_resigned.html` | الموظفون | `base.html` | 1 | 2 | 0 | 1 | 1 | employees.py |
| `employee_role_convert.html` | الموظفون | `base.html` | 2 | 5 | 1 | 2 | 0 | employees.py |
| `employee_type_report.html` | التقارير والطباعة | `base.html` | 1 | 3 | 4 | 2 | 1 | reports.py |
| `employees.html` | الموظفون | `base.html` | 5 | 12 | 5 | 6 | 0 | employees.py |
| `error.html` | حساب وتوثيق | `base.html` | 0 | 0 | 0 | 0 | 0 | errors.py |
| `excel_import.html` | الإدارة والصلاحيات | `base.html` | 3 | 5 | 1 | 5 | 2 | excel_import.py |
| `governorates.html` | الإدارة والصلاحيات | `base.html` | 4 | 6 | 0 | 4 | 1 | catalog.py |
| `home.html` | الرئيسية ومركز العمل | `base.html` | 6 | 17 | 6 | 14 | 0 | dashboard.py |
| `home_global_search.html` | الرئيسية ومركز العمل | `—` | 1 | 1 | 2 | 1 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `login.html` | حساب وتوثيق | `base.html` | 1 | 3 | 0 | 2 | 0 | auth.py |
| `lookups.html` | الإدارة والصلاحيات | `base.html` | 4 | 6 | 1 | 4 | 1 | catalog.py |
| `manager_hub.html` | الرئيسية ومركز العمل | `base.html` | 0 | 0 | 0 | 0 | 2 | reports.py |
| `mission_edit.html` | التقارير والطباعة | `base.html` | 1 | 4 | 2 | 1 | 0 | missions.py |
| `mission_edit_request_review.html` | التقارير والطباعة | `base.html` | 1 | 4 | 3 | 1 | 0 | missions.py |
| `mission_edit_requests.html` | التقارير والطباعة | `base.html` | 0 | 0 | 0 | 0 | 1 | missions.py |
| `mission_monthly.html` | التقارير والطباعة | `base.html` | 1 | 1 | 0 | 1 | 1 | missions.py |
| `mission_print.html` | التقارير والطباعة | `—` | 0 | 0 | 0 | 1 | 0 | missions.py |
| `mission_print_date.html` | التقارير والطباعة | `base.html` | 1 | 4 | 0 | 1 | 0 | missions.py |
| `mission_reports.html` | التقارير والطباعة | `base.html` | 2 | 4 | 7 | 2 | 1 | missions.py |
| `movement_edit.html` | الحركات والنماذج | `base.html` | 1 | 7 | 4 | 1 | 0 | movements.py |
| `movement_history.html` | الحركات والنماذج | `base.html` | 0 | 0 | 0 | 0 | 1 | movements.py |
| `movements.html` | الحركات والنماذج | `base.html` | 1 | 10 | 9 | 2 | 1 | movements.py |
| `notifications.html` | الرئيسية ومركز العمل | `base.html` | 0 | 0 | 0 | 0 | 0 | notifications.py |
| `movement_actions.html` | الحركات والنماذج | `—` | 3 | 4 | 0 | 3 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |
| `replacement.html` | الإدارة والصلاحيات | `base.html` | 2 | 4 | 4 | 2 | 0 | structure.py |
| `reports.html` | التقارير والطباعة | `base.html` | 1 | 0 | 1 | 1 | 0 | reports.py |
| `reports_missions.html` | التقارير والطباعة | `base.html` | 0 | 0 | 0 | 0 | 0 | reports.py |
| `structure.html` | الإدارة والصلاحيات | `base.html` | 0 | 0 | 0 | 5 | 0 | structure.py |
| `user_edit.html` | الإدارة والصلاحيات | `base.html` | 1 | 9 | 0 | 7 | 0 | users.py |
| `users.html` | الإدارة والصلاحيات | `base.html` | 5 | 15 | 0 | 5 | 1 | users.py |
| `workspace_actions.html` | الإطار والتنقل | `—` | 0 | 0 | 0 | 0 | 0 | استدعاء غير مباشر/جزئي أو لم يطابقه فحص النص |

## حدود الفهرس

هذا الفهرس يصف بنية قوالب المصدر ولا يثبت وحده أن كل صفحة تُفتح في التطبيق أو أنها غير مستخدمة. قبل حذف أي قالب أو سكربت يجب تتبع الروابط الديناميكية وواجهات Flask واختبار المسار في بيئة تشغيل فعلية.
