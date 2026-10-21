"""Login, logout, role switching and password change."""

import secrets
from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..access import actual_roles, log, me, req, safe_next_url, user_branch_ids, user_gov_ids
from ..assignments import sync_role_accounts
from ..assistant.session_state import clear_assistant_state
from ..constants import LOGIN_ROLES, MAX_PASSWORD_LENGTH
from ..extensions import db
from ..models import Branch, Governorate, User
from ..ratelimit import RateLimiter
from ..validation import valid_password

bp = Blueprint('auth', __name__)

LOGIN_WINDOW_SECONDS = 15 * 60


def login_limiter():
    """Get a per-app limiter; use Redis for shared limits when configured."""
    registry = current_app.extensions.setdefault('employee_movements_rate_limiters', {})
    key = ('login', int(current_app.config['LOGIN_RATE_LIMIT']), LOGIN_WINDOW_SECONDS)
    if key not in registry:
        registry[key] = RateLimiter(
            key[1], key[2], redis_url=current_app.config.get('REDIS_URL'),
            key_prefix=f"employee-movements:{current_app.config.get('APP_ENV', 'production')}:login",
        )
    return registry[key]


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method != 'POST':
        return render_template('login.html')
    raw_username = request.form.get('username', '')
    password = request.form.get('password', '')
    # Reject oversized credentials before lowercasing the username, querying the
    # database, or running an expensive password-hash verification. The request
    # body itself is also capped by the earliest request hook.
    oversized_credentials = len(raw_username) > 80 or len(password) > MAX_PASSWORD_LENGTH
    username = raw_username.strip() if not oversized_credentials else ''
    limiter_username = '[oversized-credentials]' if oversized_credentials else username.lower()
    limiter_key = f'{request.remote_addr}|{limiter_username}'
    limiter = login_limiter()
    if limiter.is_blocked(limiter_key):
        flash('محاولات دخول كثيرة. حاول مرة أخرى بعد 15 دقيقة.')
        return render_template('login.html'), 429
    if oversized_credentials or not username or not password:
        limiter.allow(limiter_key)
        flash('بيانات الدخول غير صحيحة.')
        return render_template('login.html')
    user = User.query.filter_by(username=username).first()
    password_ok = bool(user) and check_password_hash(user.password_hash, password)
    if not user or not user.is_active or not password_ok:
        limiter.allow(limiter_key)
        flash('بيانات الدخول غير صحيحة.')
        return render_template('login.html')
    # «مدخل البيانات الأول» أزيل من أدوار الدخول الرسمية. لا نحذف سجل الموظف أو
    # تكليف الفروع التنظيمي، لكن الحساب القديم الذي لا يحمل أي دور رسمي لا يسجل الدخول.
    real_roles = actual_roles(user)
    if not (real_roles & set(LOGIN_ROLES)):
        login_limiter().allow(limiter_key)
        flash('هذا الحساب لا يحمل دور دخول رسميًا. اطلب من مسؤول التطبيق تعيين أحد الأدوار الرسمية.')
        return render_template('login.html'), 403
    login_limiter().reset(limiter_key)
    if me():
        clear_assistant_state()
        db.session.commit()
    session.clear()
    session['uid'] = user.id
    session['auth_version'] = int(user.auth_version or 0)
    session['csrf'] = secrets.token_urlsafe(24)
    # الحساب متعدد الأدوار يبدأ بدور واحد محدد؛ لا نسمح بمزيج صلاحيات بين الأدوار.
    for preferred in LOGIN_ROLES:
        if preferred in real_roles:
            session['active_role'] = preferred
            break
    user.last_login = datetime.utcnow()
    log('LOGIN', 'User', user.id)
    db.session.commit()
    return redirect(url_for('dashboard.home'))


@bp.post('/logout')
def logout():
    clear_assistant_state()
    db.session.commit()
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
            clear_assistant_state()
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
            invalidate_user_workflows(u.id)
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
