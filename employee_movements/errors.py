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
    413: ('الملف كبير جدًا', 'حجم الملف يتجاوز الحد المسموح (2 ميجابايت).'),
    500: ('حدث خطأ غير متوقع', 'تم تسجيل المشكلة. حاول مرة أخرى بعد قليل.'),
}


def _render(code):
    title, message = MESSAGES.get(code, MESSAGES[500])
    return render_template('error.html', code=code, title=title, message=message), code


def register_error_handlers(app):
    def http_error(err):
        return _render(err.code or 500)

    def unexpected_error(err):
        db.session.rollback()
        logger.exception('Unhandled error on %s %s', request.method, request.path)
        return _render(500)

    app.register_error_handler(HTTPException, http_error)
    app.register_error_handler(Exception, unexpected_error)
