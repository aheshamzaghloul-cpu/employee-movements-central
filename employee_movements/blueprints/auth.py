"""Login, logout, role switching and password change."""

import secrets
import hmac
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..access import actual_roles, log, me, req, safe_next_url, user_branch_ids, user_gov_ids
from ..assignments import sync_role_accounts
from ..constants import LOGIN_ROLES
from ..extensions import db
from ..models import Branch, Governorate, User
from ..ratelimit import RateLimiter
from ..validation import valid_password

bp = Blueprint('auth', __name__)

LOGIN_WINDOW_SECONDS = 15 * 60
_login_limiter = None


def login_limiter():
    """Lazily build the limiter so the limit comes from the application config."""
    global _login_limiter
    if _login_limiter is None:
        _login_limiter = RateLimiter(current_app.config['LOGIN_RATE_LIMIT'], LOGIN_WINDOW_SECONDS)
    return _login_limiter


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method != 'POST':
        return render_template('login.html')
    username = request.form.get('username', '').strip()
    limiter_key = f'{request.remote_addr}|{username.lower()}'
    if login_limiter().is_blocked(limiter_key):
        flash('محاولات دخول كثيرة. حاول مرة أخرى بعد 15 دقيقة.')
        return render_template('login.html'), 429
    user = User.query.filter_by(username=username).first()
    password_ok = bool(user) and check_password_hash(user.password_hash, request.form.get('password', ''))
    if not user or not user.is_active or not password_ok:
        login_limiter().allow(limiter_key)
        flash('بيانات الدخول غير صحيحة.')
        return render_template('login.html')
    login_limiter().reset(limiter_key)
    session.clear()
    session['uid'] = user.id
    session['csrf'] = secrets.token_urlsafe(24)
    # الحساب متعدد الأدوار يبدأ بدور واحد محدد؛ لا نسمح بمزيج صلاحيات بين الأدوار.
    real_roles = actual_roles(user)
    for preferred in LOGIN_ROLES:
        if preferred in real_roles:
            session['active_role'] = preferred
            break
    user.last_login = datetime.utcnow()
    log('LOGIN', 'User', user.id)
    db.session.commit()
    return redirect(url_for('dashboard.home'))



@bp.get('/review-access')
def review_access():
    """Temporary diagnostic for the dedicated review account."""
    if not current_app.config.get('REVIEW_ACCESS_ENABLED'):
        current_app.logger.warning('Review access: disabled by configuration.')
        return 'Review access is disabled. Check REVIEW_ACCESS_ENABLED=1.', 503

    token = request.args.get('token', '')
    expected = current_app.config.get('REVIEW_ACCESS_TOKEN', '')

    if not expected or len(expected) < 32 or not hmac.compare_digest(token, expected):
        current_app.logger.warning('Review access: token rejected.')
        return 'Review token rejected. Check the token in Blitz.', 403

    username = current_app.config.get('REVIEW_USERNAME', 'full_review_test')
    user = User.query.filter_by(username=username).first()

    if not user:
        current_app.logger.warning('Review access: configured account not found.')
        return 'Review account not found in the connected database.', 404

    if not user.is_active:
        current_app.logger.warning('Review access: configured account is inactive.')
        return 'Review account exists but is inactive.', 403

    session.clear()
    session['uid'] = user.id
    session['csrf'] = secrets.token_urlsafe(24)
    session['review_mode'] = True

    real_roles = actual_roles(user)
    for preferred in LOGIN_ROLES:
        if preferred in real_roles:
            session['active_role'] = preferred
            break

    user.last_login = datetime.utcnow()
    log('REVIEW_LOGIN', 'User', user.id, 'Temporary review access')
    db.session.commit()
    current_app.logger.warning('Review access succeeded.')
    return redirect(url_for('dashboard.home'))


@bp.get('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


@bp.post('/switch-role')
@req
def switch_role():
    u = me()
    real_roles = actual_roles(u)
    selected = request.form.get('active_role', '').strip()
    if len(real_roles) <= 1:
        session.pop('active_role', None)
    elif selected in real_roles and selected in LOGIN_ROLES:
        old_role = session.get('active_role')
        session['active_role'] = selected
        if old_role != selected:
            # تغيير الدور عملية انتقال أمنية كاملة، وليس مجرد تبديل للقائمة.
            # لا ننقل محافظة أو سياق صفحة أو عملية معلقة من الدور السابق.
            session.pop('operational_governorate_id', None)
            session.pop('operational_scope_uid', None)
            session.pop('operational_scope_role', None)
            session.pop('assistant_pending', None)
            session.pop('assistant_manager_pending', None)
            session.pop('assistant_context_employee_id', None)
            session.pop('assistant_workspace_context', None)
            log('SWITCH_ROLE', 'User', u.id, f'{old_role or "الدور التلقائي"} -> {selected}')
            db.session.commit()
            # لا نعيد المستخدم إلى صفحة قد تنتمي للدور السابق.
            # الإدارة هي نقطة الهبوط الوحيدة لمسؤول التطبيق، بينما التشغيل
            # يبدأ من الرئيسية للمشرف/Manager.
            landing = url_for('structure.structure') if selected == 'مسؤول التطبيق' else url_for('dashboard.home')
            return redirect(landing)
    else:
        flash('الدور المختار غير متاح لهذا الحساب.')
    return redirect(safe_next_url(request.form.get('next'), url_for('dashboard.home')))


@bp.route('/change-password', methods=['GET', 'POST'])
@req
def change_password():
    u = me()
    if request.method == 'POST':
        old = request.form.get('old_password', '')
        new = request.form.get('new_password', '')
        confirm = request.form.get('confirm_password', '')
        if not check_password_hash(u.password_hash, old):
            flash('كلمة المرور الحالية غير صحيحة.')
        elif not valid_password(new):
            flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حروف وأرقام.')
        elif new != confirm:
            flash('تأكيد كلمة المرور غير مطابق.')
        else:
            u.password_hash = generate_password_hash(new)
            u.must_change_password = False
            sync_role_accounts(u)
            log('PASSWORD_CHANGE', 'User', u.id)
            db.session.commit()
            flash('تم تغيير كلمة المرور بنجاح.')
            return redirect('/')
    roles_now = actual_roles(u)
    gov_ids = set(user_gov_ids(u))
    if 'المدخل الأول' in roles_now:
        branch_ids = user_branch_ids(u)
        if branch_ids:
            gov_ids |= {
                b.governorate_id
                for b in Branch.query.filter(Branch.id.in_(branch_ids)).all()
            }
    if 'مسؤول التطبيق' in roles_now or 'Manager Application Support' in roles_now:
        account_govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
    else:
        account_govs = (
            (
                Governorate.query.filter(Governorate.id.in_(gov_ids), Governorate.is_active == True)
                .order_by(Governorate.name)
                .all()
            )
            if gov_ids
            else []
        )
    return render_template('change_password.html', account_govs=account_govs)
