# نظام إدارة حركات الموظفين — Employee Movements Central

منصة ويب عربية (RTL) مركزية لإدارة **الإجازات والانتدابات والأذون** للموظفين حسب الهيكل التنظيمي (محافظات ← فروع ← مشرفون ← مدخلون أوائل)، مع مأموريات قابلة للطباعة (PDF)، وتقارير، واستيراد Excel، ومساعد ذكي.

**التقنيات:** Flask 3 · Flask-SQLAlchemy · PostgreSQL (أو SQLite للتطوير) · Gunicorn · Docker · Caddy (HTTPS).

## التشغيل السريع (تطوير)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
APP_ENV=development ADMIN_PASSWORD='Admin12345' python wsgi.py     # http://127.0.0.1:8000
```

في وضع `development` يُنشأ مفتاح جلسة مؤقت وقاعدة SQLite محلية (`local.db`) تلقائيًا.

## التشغيل بالحاويات (إنتاج)

```bash
cp .env.example .env     # املأ القيم السرية والنطاق
docker compose up -d --build
```

التفاصيل والنسخ الاحتياطي: [docs/DEPLOYMENT_AR.md](docs/DEPLOYMENT_AR.md).

## الإعدادات (متغيرات البيئة)

| المتغير | الوصف |
|---|---|
| `APP_ENV` | `production` (الافتراضي) يرفض الإقلاع بإعدادات غير آمنة، أو `development` / `testing` |
| `SECRET_KEY` | **إلزامي في الإنتاج**، 32 حرفًا على الأقل |
| `DATABASE_URL` | رابط PostgreSQL؛ تُقبل الصيغ `postgres://` و`postgresql://` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | حساب المسؤول الأولي (يُنشأ عند أول تشغيل فقط) |
| `COOKIE_SECURE` | `1` عند العمل عبر HTTPS |
| `GEMINI_API_KEY` / `GEMINI_MODEL` / `GEMINI_TIMEOUT` | اختياري؛ بدونه يعمل المساعد بالفهم المحلي فقط. Gemini لا يستقبل كتالوج الموظفين أو الفروع؛ التطبيق يحل الكيانات محليًا. |
| `LOGIN_RATE_LIMIT` / `ASSISTANT_RATE_LIMIT` | حدود الاستخدام (انظر `.env.example`) |

## الاختبارات والفحص

```bash
ruff check .
pytest
```

## بنية المشروع

```
employee_movements/
  __init__.py        مصنع التطبيق create_app()
  config.py          الإعدادات والتحقق عند الإقلاع
  models.py          نماذج قاعدة البيانات
  access.py          الأدوار والصلاحيات ونطاق العمل
  assignments.py     خدمات الانتداب والمشرفين والمدخلين
  validation.py      التحقق من المدخلات والحركات
  hooks.py           CSRF وترويسات الأمان وسياق القوالب
  bootstrap.py       إنشاء الجداول والترحيلات الآمنة المتكررة
  blueprints/        وحدات الواجهة (auth, dashboard, users, movements, reports, ...)
  assistant/         المساعد الذكي (intents, llm, render, routes)
  templates/  static/
tests/   docs/   scripts/
```

مزيد من التفاصيل: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/DESIGN_SYSTEM_AR.md](docs/DESIGN_SYSTEM_AR.md) · [CHANGELOG.md](CHANGELOG.md).

## الأدوار

مسؤول التطبيق · مشرف محافظة · Manager Application Support (أدوار دخول)، و«المدخل الأول» تصنيف تنظيمي مرتبط بسجل موظف وليس حساب دخول.
