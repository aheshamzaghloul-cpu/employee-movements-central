# Page / Stylesheet Map — v68.49.0

| صفحة / مسار | ورقة التصميم المضافة في هذه الدفعة | المكونات التي تم التركيز عليها |
|---|---|---|
| `/change-password` | `pages/secondary-workspaces.css` | كروت الحساب، نموذج كلمة المرور، الحقول المتجاوبة |
| `/notifications` | `pages/secondary-workspaces.css` | مؤشرات الأولوية، بطاقات الإشعار، حالات القراءة |
| `/audit` | `pages/secondary-workspaces.css` | رأس الجدول، الصفوف، احتواء المحتوى الطويل |
| `/lookups` | `pages/secondary-workspaces.css` | بطاقة الإضافة، بطاقتا الأنواع، جداول الإجراءات وأزرارها |
| `/replacement` | `pages/secondary-workspaces.css` | بطاقات الاستبدال، الحقول، الملاحظات |
| `/users/<id>/...` | `pages/secondary-workspaces.css` | أقسام تعديل المستخدم وخيارات الدور والنطاق والصلاحيات |
| أخطاء HTTP / عنوان غير معروف | `app.css` | بطاقة الخطأ، رمز الحالة، الرسالة وزر العودة |

## ترتيب التحميل

`app.css` ثم أوراق الصفحة/مساحة العمل المناسبة ثم `design-system-cyan.css` ثم أوراق السياق الإضافية (مثل `assistant-dock.css` و`navigation-color-system.css`) ثم `secondary-workspaces.css` فقط للمسارات المقصودة. بطاقة الخطأ في `app.css` العام عمدًا لأن مسار الخطأ قد لا يطابق مسارًا معروفًا.

تُضاف قيمة التخزين المؤقت `v=68.49.0` للأصول المعنية. ملف المعاينة `preview-summary.json` يبين أوراق CSS التي جرى تحميلها لكل حالة اختبار.
