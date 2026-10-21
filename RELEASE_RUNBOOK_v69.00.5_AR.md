# مراجعة ما قبل الرفع — v69.00.5 / الجولة 35

## الهدف
مراجعة أمنية واعتمادية ساكنة قبل رفع المصدر إلى GitHub وربطه ببيئة الاستضافة. لا يعني هذا التقرير اعتماد الإصدار للإنتاج.

## إصلاحات هذه الجولة
- تحديث `Pillow==12.3.0` إلى `Pillow==13.0.0`. صدر Pillow 13.0.0 في 16 أكتوبر 2026، وتذكر ملاحظات الإصدار الرسمية إصلاحات أمنية إضافية لقراءة/كتابة الصور، بما فيها مسارات TIFF وJPEG وPDF. كما يصرح المشروع بدعم Python 3.12 وتوفر عجلات CPython 3.12 لأنظمة manylinux.
- تقييد استدعاءات `Image.open` التي تتعامل مع صور مرفوعة أو مرفقات مأمورية إلى الصيغ المسموح بها صراحةً PNG/JPEG/WEBP، دون الاعتماد على رفض الصيغة بعد تشغيل المحلل العام.
- الإبقاء على حدود حجم الملف وعدد البكسلات والتحقق من سلامة الصورة وعمليات التطبيع الحالية.
- إضافة `contract_tests/test_pillow_upload_parser_policy_round35.py` كحارس مصدر لمراجعة رقم الاعتمادية والسماح بالصيغ. لم يُشغّل هذا العقد.
- إزالة التثبيت الثابت لرقم الجولة 34 من عقود بيانات الإصدار؛ تتحقق العقود الآن من أن رقم الجولة صحيح وأن اسم الأرشيف يطابق النسخة والبيان الحاليين.
- توحيد `VERSION.md` و`pyproject.toml` و`employee_movements.__version__` وترويسات CSS عند `69.00.5`.
- استعادة وضع التنفيذ (`755`) لسكريبتَي النسخ الاحتياطي والاستعادة اللذين تشير إليهما أدلة التشغيل.

## مراجعة الاعتماديات
- `gunicorn==26.2.0` باقٍ لأن سجل التثبيت الذي أرسله المستخدم لم يعرض `26.2.2`. يسرد سجل Gunicorn الرسمي تغييرات `.2.2` لكن صفحة PyPI التي تمت مراجعتها تسرد ملفات الإصدار `.2.0`؛ لذلك لا يُرفع القيد إلى إصدار لا يستطيع فهرس البناء تثبيته.
- راجعت مراجع PyPI/المشروع للأطر والإصدارات المسجلة؛ لم يُنفّذ `pip install` أو `pip check` أو `pip-audit`. يظل فحص الثغرات الاعتمادية في CI بوابة إلزامية.
- لم يُعثر ساكنًا على استخدامات لواجهات Pillow المزالة التي شملها فحص المصدر (`Image._show`, `get_child_images`, `Image.fromarray(mode=...)`, `ImageWin.align8to32`, `load_djpeg`, `ImageCmsProfile.product_name/product_info`, و`ExifTags.IFD.Makernote`). هذا فحص نصي/ساكن لا يغني عن اختبار التكامل.

## ما تم التحقق منه دون تشغيل التطبيق
- تحليل صياغة Python وJSON وTOML.
- فحوص سير عمل الرئيسية، وتكامل الواجهة، وأمن مسارات POST، وإمكانية الوصول، ونظافة المستودع، وتداخل CSS.
- مراجعة ساكنة لمراجع القوالب والأصول، والتوافق بين بيانات الإصدار، وملفات البيئة وCompose وDockerfile وWSGI/Gunicorn.
- بحث أنماط الأسرار: لم توجد أسرار تشغيلية فعلية أو ملف `.env` أو قاعدة بيانات محلية داخل الحزمة؛ أما مفاتيح الاختبار الظاهرية فمقصودة في اختبارات الخصوصية.
- التحقق من سلامة أرشيف المصدر النهائي وبصمة SHA-256 بعد إنشائه.

## ما لم يُنفّذ
- لم تُشغّل `pytest` أو عقود الاختبار أو أي اختبار للمشروع.
- لم يُشغّل Flask أو قاعدة البيانات، ولم تُنفّذ معاينة Excel أو تصالح بيانات.
- لم يُنفّذ `pip install` أو `pip check` أو `pip-audit`، ولم يُبنَ Docker.
- لم يحدث دفع إلى GitHub أو نشر إلى Blitz.

## بوابة الإصدار
`NOT CLEARED FOR PRODUCTION` إلى أن ينجح تثبيت الاعتماديات، وفحص `pip-audit`، وCI، وبناء صورة Docker، وفحوص التشغيل والتكامل على بيئة تجريبية.

## مراجع الاعتمادية الرسمية
- Pillow 13.0.0: https://pypi.org/project/Pillow/13.0.0/
- Pillow 13.0.0 release notes: https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html
- Pillow Python support: https://pillow.readthedocs.io/en/stable/installation/python-support.html
- Gunicorn PyPI 26.2.0: https://pypi.org/project/gunicorn/26.2.0/
- Gunicorn changelog: https://gunicorn.org/news/
- Werkzeug 3.1.9 security fix: https://github.com/pallets/werkzeug/security/advisories/GHSA-g6x2-hccm-hh4m
- Gemini deprecations: https://ai.google.dev/gemini-api/docs/deprecations/
