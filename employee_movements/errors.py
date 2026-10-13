"""Friendly Arabic error pages."""

import logging

from flask import render_template, request
from werkzeug.exceptions import HTTPException

from .extensions import db

logger = logging.getLogger(__name__)

MESSAGES = {
    400: ('طلب غير صالح', 'تعذّر تنفيذ الطلب. أعد تحميل الصفحة وحاول مرة أخرى.'),
    403: ('غير مصرّح', 'لا تملك صلاحية الوصول إلى هذه الصفحة بدورك الحالي.'),
    404: ('الصفحة غير موجودة', 'الرابط الذي طلبته غير موجود أو تم نقله.'),
    405: ('الطريقة غير مسموحة', 'هذا الإجراء غير متاح على هذا الرابط.'),
    413: ('الملف كبير جدًا', 'حجم الطلب يتجاوز الحد المسموح.'),
    500: ('حدث خطأ غير متوقع', 'تم تسجيل المشكلة. حاول مرة أخرى بعد قليل.'),
}


def _render(code):
    title, message = MESSAGES.get(code, MESSAGES[500])
    if code == 413:
        if request.endpoint == 'excel_import.excel_import_preview':
            limit = int(request.max_content_length or 16 * 1024 * 1024)
            title = 'ملف Excel كبير جدًا'
            message = f'حجم ملف Excel يتجاوز الحد المسموح ({max(1, limit // (1024 * 1024))} ميجابايت).'
        else:
            limit = int(request.max_content_length or 2 * 1024 * 1024)
            message = f'حجم الطلب يتجاوز الحد المسموح ({max(1, limit // (1024 * 1024))} ميجابايت).'
    return render_template('error.html', code=code, title=title, message=message), code


def register_error_handlers(app):
    def http_error(err):
        return _render(err.code or 500)

    def unexpected_error(err):
        db.session.rollback()
        # Avoid logging exception text/tracebacks: database exceptions may include row values.
        logger.error('Unhandled error on %s %s (%s)', request.method, request.path, type(err).__name__)
        return _render(500)

    app.register_error_handler(HTTPException, http_error)
    app.register_error_handler(Exception, unexpected_error)
