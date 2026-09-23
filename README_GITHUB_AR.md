# نظام حركات الموظفين المركزي — v35.18

نسخة نظيفة ومجهزة للرفع إلى GitHub لمشروع نظام حركات الموظفين المركزي.

## المكونات
- Flask
- Flask-SQLAlchemy
- PostgreSQL
- Gunicorn
- Docker
- Caddy

## مهم قبل الرفع
- يفضل أن يكون مستودع GitHub **Private**.
- لا ترفع أي ملف `.env` أو كلمات مرور أو مفاتيح سرية.
- ملف `.env.example` و`.env.production.example` مجرد قوالب إعداد ولا تحتوي على أسرار تشغيل حقيقية.
- لا توجد قاعدة بيانات محلية ضمن هذه النسخة.

## هيكل المشروع
- `app.py` — التطبيق الرئيسي.
- `templates/` — صفحات HTML.
- `static/` — ملفات CSS وJavaScript.
- `scripts/` — النسخ الاحتياطي والاستعادة.
- `Dockerfile` — تشغيل التطبيق بالحاوية.
- `docker-compose.yml` — تشغيل محلي/بيئة حاويات.
- `requirements.txt` — مكتبات Python.
- `DEPLOYMENT_AR.md` — إرشادات النشر.

## رفع المشروع إلى GitHub
من داخل مجلد المشروع:

```bash
git init
git add .
git commit -m "Employee Movements Central v35.18"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

استبدل `USERNAME/REPOSITORY` بعنوان مستودعك فقط.
