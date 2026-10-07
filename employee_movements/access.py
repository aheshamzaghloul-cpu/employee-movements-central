"""Authentication helpers, role/permission checks and operational-scope resolution."""

import secrets
from datetime import date
from functools import wraps

from flask import abort, has_request_context, redirect, request, session, url_for

from .constants import LOGIN_ROLES, OPERATIONAL_SCOPE_ENDPOINTS, ROLE_DEFAULT_PERMISSIONS, ROLES
from .extensions import db
from .models import (
    ApprovalDelegation,
    Audit,
    Branch,
    Governorate,
    User,
    UserBranch,
    UserGovernorate,
    UserPermission,
    UserRole,
)


def me():
    uid = session.get('uid')
    if not uid:
        return None
    try:
        return db.session.get(User, int(uid))
    except (TypeError, ValueError):
        session.pop('uid', None)
        return None


def actual_roles(u=None):
    u = u or me()
    return {x.role for x in UserRole.query.filter_by(user_id=u.id).all()} if u else set()


def roles(u=None):
    # For the logged-in user, an optional session role is the active UI role.
    # For any other user, always return the real stored roles.
    u = u or me()
    if not u:
        return set()
    real = actual_roles(u) - {'المدخل الأول'}
    # session is only available while handling an HTTP request.
    # Startup/database migrations also call role helpers, so never touch
    # the Flask session outside a request context.
    if has_request_context() and u.id == session.get('uid'):
        active = session.get('active_role')
        if active in real:
            return {active}
        if active:
            session.pop('active_role', None)
        # A multi-role account must always operate in exactly one login role.
        # Prefer an explicit active role; otherwise use the stable role priority
        # instead of returning a mixture of admin + supervisor permissions.
        default_role = next((r for r in LOGIN_ROLES if r in real), None)
        return {default_role} if default_role else real
    return real


def has_role(*r):
    return bool(roles() & set(r))


def req(f):
    @wraps(f)
    def w(*a, **k):
        u = me()
        if not u or not u.is_active:
            session.clear()
            return redirect(url_for('auth.login'))
        if u.must_change_password and request.endpoint != 'auth.change_password':
            return redirect(url_for('auth.change_password'))
        return f(*a, **k)

    return w


def only(*rs):
    def d(f):
        @wraps(f)
        def w(*a, **k):
            if not me() or not has_role(*rs):
                abort(403)
            return f(*a, **k)

        return w

    return d


def log(a, e='', i=None, d=''):
    db.session.add(
        Audit(user_id=me().id if me() else None, action=a, entity=e, entity_id=i, details=d),
    )


def safe_next_url(target, fallback='/'):
    """Return ``target`` only when it is a same-site relative path (prevents open redirects)."""
    target = (target or '').strip()
    if target.startswith('/') and not target.startswith(('//', '/\\')) and '\n' not in target and '\r' not in target:
        return target
    return fallback


def csrf_token():
    if 'csrf' not in session:
        session['csrf'] = secrets.token_urlsafe(24)
    return session['csrf']


def user_roles(u):
    return roles(u)


def delegation_allowed_for_user(u, gid):
    return bool(u and gid and ('مشرف محافظة' in actual_roles(u)) and (gid in user_gov_ids(u)))


def can_for_user(u, permission):
    return bool(
        u and u.is_active and ('مسؤول التطبيق' in roles(u) or permission in user_permissions(u)),
    )


def user_permissions(u):
    """Return permissions allowed by the user's effective login role.

    A stored explicit permission must never turn a supervisor/manager session into
    an administrator session. The active role is a security boundary, not only a
    navigation preference. Administrators retain full system permissions.
    """
    explicit = {x.permission for x in UserPermission.query.filter_by(user_id=u.id).all()}
    selected = None
    if u and has_request_context() and (u.id == session.get('uid')):
        selected = session.get('active_role')

    if selected:
        if selected == 'مسؤول التطبيق':
            return set(PERMISSIONS)
        allowed = set(ROLE_DEFAULT_PERMISSIONS.get(selected, set()))
        return (explicit & allowed) if explicit else allowed

    effective = actual_roles(u) - {'المدخل الأول'}
    if explicit:
        allowed = set()
        for r in effective:
            allowed |= ROLE_DEFAULT_PERMISSIONS.get(r, set())
        return explicit & allowed

    out = set()
    for r in effective:
        out |= ROLE_DEFAULT_PERMISSIONS.get(r, set())
    return out


def can(permission):
    u = me()
    return bool(u and ('مسؤول التطبيق' in roles(u) or permission in user_permissions(u)))


def user_gov_ids(u):
    return {x.governorate_id for x in UserGovernorate.query.filter_by(user_id=u.id).all()}


def delegated_gov_ids(u, on_date=None):
    """Return only delegations whose security prerequisites are still valid.

    A delegation is temporary scope, not a permanent entitlement. It must not
    survive loss of the delegate's account/role, loss of the original
    supervisor's account/role or permanent governorate assignment, or
    deactivation of the governorate itself.
    """
    if not u or not u.is_active or 'مشرف محافظة' not in actual_roles(u):
        return set()
    day = on_date or date.today()
    rows = (
        ApprovalDelegation.query
        .filter_by(delegate_id=u.id, is_active=True)
        .filter(ApprovalDelegation.starts_at <= day, ApprovalDelegation.ends_at >= day)
        .all()
    )
    valid = set()
    for delegation in rows:
        governorate = delegation.governorate
        supervisor = delegation.supervisor
        if not governorate or not governorate.is_active:
            continue
        if not supervisor or not supervisor.is_active:
            continue
        if 'مشرف محافظة' not in actual_roles(supervisor):
            continue
        if delegation.governorate_id not in user_gov_ids(supervisor):
            continue
        valid.add(delegation.governorate_id)
    return valid


def effective_user_gov_ids(u, on_date=None):
    return user_gov_ids(u) | delegated_gov_ids(u, on_date)


def user_branch_ids(u):
    return {x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()}


def is_scope_required_endpoint():
    return bool(has_request_context() and request.endpoint in OPERATIONAL_SCOPE_ENDPOINTS)


def scope_governorate_id():
    if not has_request_context():
        return None
    u = me()
    if not u:
        return None
    rs = roles(u)
    # نطاق العمل تشغيلي مستقل تمامًا عن المحافظات المرتبطة بأدوار الحساب.
    # لا نرث محافظة مشرف (مثل سوهاج) كاختيار تلقائي لمسؤول التطبيق/Manager.
    raw = request.args.get('governorate_id') or request.args.get('manager_governorate_id') or ''
    if raw.isdigit():
        gid = int(raw)
        allowed = {g.id for g in scope_governorates_for_user(u)}
        if gid in allowed and Governorate.query.filter_by(id=gid, is_active=True).first():
            session['operational_governorate_id'] = gid
            session['operational_scope_uid'] = u.id
            session['operational_scope_role'] = next(
                iter(rs & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'}),
                None,
            )
    selected = session.get('operational_governorate_id')
    # إذا كان الاختيار محفوظًا لحساب/دور مختلف، فلا نستخدمه.
    scope_uid = session.get('operational_scope_uid')
    scope_role = session.get('operational_scope_role')
    current_scope_role = next(iter(rs & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'}), None)
    if scope_uid != u.id or scope_role != current_scope_role:
        session.pop('operational_governorate_id', None)
        session.pop('operational_scope_uid', None)
        session.pop('operational_scope_role', None)
        return None
    if selected and (not Governorate.query.filter_by(id=int(selected), is_active=True).first()):
        session.pop('operational_governorate_id', None)
        return None
    return selected


def scope_governorates_for_user(u=None):
    u = u or me()
    if not u:
        return []
    rs = roles(u)
    if 'مسؤول التطبيق' in rs or 'Manager Application Support' in rs:
        return Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()
    if 'مشرف محافظة' in rs:
        assigned = (
            Governorate.query.filter(
                Governorate.id.in_(effective_user_gov_ids(u)),
                Governorate.is_active == True,
            )
            .order_by(Governorate.name.asc())
            .all()
        )
        return assigned
    return (
        Governorate.query.filter(Governorate.id.in_(effective_user_gov_ids(u)), Governorate.is_active == True)
        .order_by(Governorate.name.asc())
        .all()
    )


def gids():
    u = me()
    if not u:
        return []
    rs = roles(u)
    # أثناء الصفحات التشغيلية، الدور التشغيلي المختار يعملان داخل المحافظة المختارة فقط.
    if (
        is_scope_required_endpoint()
        and ('مسؤول التطبيق' in rs or 'مشرف محافظة' in rs or 'Manager Application Support' in rs)
    ):
        selected = scope_governorate_id()
        return [int(selected)] if selected else []
    if 'مسؤول التطبيق' in rs:
        return [g.id for g in Governorate.query.filter_by(is_active=True)]
    if 'Manager Application Support' in rs:
        selected = scope_governorate_id()
        if selected:
            return [int(selected)]
        return []
    if 'مشرف محافظة' in rs:
        assigned = {
            x.governorate_id
            for x in UserGovernorate.query.filter_by(user_id=u.id).join(Governorate).filter(Governorate.is_active == True)
        }
        return sorted(assigned | delegated_gov_ids(u))
    return [
        x.governorate_id
        for x in UserGovernorate.query.filter_by(user_id=u.id).join(Governorate).filter(Governorate.is_active == True)
    ]


def bids():
    u = me()
    if not u:
        return []
    rs = roles(u)
    # في الصفحات التشغيلية، الدور الإداري/التشغيلي المختار يعمل داخل المحافظة المحددة داخل
    # المحافظة المختارة فقط؛ لا يجوز لدور مشرف آخر على نفس الحساب أن
    # يوسع النطاق أو يعيد سوهاج تلقائيًا.
    if (
        is_scope_required_endpoint()
        and ('مسؤول التطبيق' in rs or 'مشرف محافظة' in rs or 'Manager Application Support' in rs)
    ):
        gids_now = gids()
        return (
            [
                b.id
                for b in Branch.query.filter(Branch.governorate_id.in_(gids_now), Branch.is_active == True)
            ]
            if gids_now
            else []
        )
    if 'مسؤول التطبيق' in rs:
        return [b.id for b in Branch.query.filter_by(is_active=True)]
    if 'Manager Application Support' in rs:
        gids_now = gids()
        return (
            [
                b.id
                for b in Branch.query.filter(Branch.governorate_id.in_(gids_now), Branch.is_active == True)
            ]
            if gids_now
            else []
        )
    if 'مشرف محافظة' in rs:
        return [
            b.id
            for b in Branch.query.filter(Branch.governorate_id.in_(gids()), Branch.is_active == True)
        ]
    return [
        x.branch_id
        for x in UserBranch.query.filter_by(user_id=u.id).join(Branch).filter(Branch.is_active == True)
    ]


def branch_ok(i):
    try:
        return i is not None and int(i) in set(bids())
    except (TypeError, ValueError):
        return False


def allowed_create_user(role):
    rs = roles()
    if 'مسؤول التطبيق' in rs:
        return role in ROLES
    return role == 'المدخل الأول' and 'مشرف محافظة' in rs


def allowed_target_user(target):
    current = me()
    rs = roles(current)
    if not target or not target.is_active:
        return False
    if 'مسؤول التطبيق' in rs:
        return True
    if 'مشرف محافظة' not in rs or 'المدخل الأول' not in roles(target):
        return False
    target_govs = {
        b.governorate_id
        for b in Branch.query.join(UserBranch, UserBranch.branch_id == Branch.id).filter(UserBranch.user_id == target.id)
    }
    return bool(set(gids()) & target_govs)


def can_manage_employee(e):
    return bool(e and branch_ok(e.branch_id) and can('manage_employees'))


def can_manage_movement(m=None):
    rs = roles()
    if 'مسؤول التطبيق' in rs:
        return True
    if 'Manager Application Support' in rs and can('manage_movements'):
        return True
    if 'مشرف محافظة' in rs and can('manage_movements'):
        return True
    if 'المدخل الأول' not in rs:
        return False
    # First-level users manage movements within their assigned branches.
    # They are not limited to movements they personally created.
    return bool(m and branch_ok(m.employee.branch_id)) if m else True
