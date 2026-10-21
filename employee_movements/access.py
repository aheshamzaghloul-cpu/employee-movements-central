"""Authentication helpers, role/permission checks and operational-scope resolution."""

import secrets
from datetime import date
from functools import wraps

from flask import abort, has_request_context, redirect, request, session, url_for

from .constants import GLOBAL_READ_SCOPE_ENDPOINTS, LOGIN_ROLES, OPERATIONAL_SCOPE_ENDPOINTS, PERMISSIONS, ROLE_DEFAULT_PERMISSIONS
from .extensions import db
from .navigation import safe_local_return_to
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
        # Password resets and security-sensitive account changes revoke older signed-cookie sessions.
        # Sessions created before this field existed fail closed and must sign in again.
        try:
            session_auth_version = int(session.get('auth_version', -1))
            current_auth_version = int(u.auth_version or 0)
        except (TypeError, ValueError):
            session_auth_version = -1
            current_auth_version = int(u.auth_version or 0)
        if session_auth_version != current_auth_version:
            session.clear()
            return redirect(url_for('auth.login'))
        # Only the three official login roles can enter the application. Legacy
        # first-entry accounts are migrated away; this guard also fails closed if
        # an orphan/no-role account remains in an older database.
        if not (actual_roles(u) & set(LOGIN_ROLES)):
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
    """Return only a safe same-origin path for post-login/role-switch navigation."""
    return safe_local_return_to(target, fallback)


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


# Internal marker stored in UserPermission to distinguish an intentionally empty
# custom permission set from legacy users who still inherit role defaults.
CUSTOM_PERMISSION_SET_MARKER = '__CUSTOM_PERMISSION_SET__'


def user_permissions(u):
    """Return permissions allowed by the user's effective login role.

    A stored explicit permission must never turn a supervisor/manager session into
    an administrator session. The active role is a security boundary, not only a
    navigation preference. Administrators retain full system permissions.

    Legacy accounts with no permission rows inherit role defaults. Accounts whose
    permission editor has been saved carry a marker, so an intentionally empty
    custom permission set stays empty instead of silently restoring defaults.
    """
    rows = UserPermission.query.filter_by(user_id=u.id).all() if u else []
    custom_mode = any(x.permission == CUSTOM_PERMISSION_SET_MARKER for x in rows)
    explicit = {x.permission for x in rows if x.permission != CUSTOM_PERMISSION_SET_MARKER}
    selected = None
    if u and has_request_context() and (u.id == session.get('uid')):
        candidate_role = session.get('active_role')
        # Never trust a stale session role directly here. In particular, an
        # invalid 'مسؤول التطبيق' value must not grant the admin permission set.
        if candidate_role in (actual_roles(u) - {'المدخل الأول'}):
            selected = candidate_role
        elif candidate_role:
            session.pop('active_role', None)

    if selected:
        if selected == 'مسؤول التطبيق':
            return set(PERMISSIONS)
        allowed = set(ROLE_DEFAULT_PERMISSIONS.get(selected, set()))
        # Operational access is intentionally consistent across the three
        # formal roles. The permission editor cannot silently remove shared
        # daily-work capabilities; admin-only capabilities remain outside the
        # allowed set for Supervisor and Manager regardless of stored rows.
        if selected in {'مشرف محافظة', 'Manager Application Support'}:
            return allowed
        return (explicit & allowed) if (custom_mode or explicit) else allowed

    if u and has_request_context() and u.id == session.get('uid'):
        effective = roles(u)
    else:
        effective = actual_roles(u) - {'المدخل الأول'} if u else set()
    if custom_mode or explicit:
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
    if not u or not getattr(u, 'is_active', False):
        return False
    active_roles = roles(u)
    # Shared read access is a product rule for every official login role, not a
    # per-role toggle. This never grants write, account-admin, or audit rights.
    if permission == 'view_reports' and active_roles & set(LOGIN_ROLES):
        return True
    return bool('مسؤول التطبيق' in active_roles or permission in user_permissions(u))


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
    """Return whether this request must use the selected work-governorate.

    Global read screens deliberately ignore the active operational selector. For
    mixed GET/POST endpoints, only safe HTTP methods are exempt; writes continue
    to use the selected scope and are checked again by their route-level guards.
    """
    if not has_request_context():
        return False
    endpoint = request.endpoint
    if endpoint in GLOBAL_READ_SCOPE_ENDPOINTS and request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return False
    return endpoint in OPERATIONAL_SCOPE_ENDPOINTS


def scope_governorate_id():
    """Resolve the selected work governorate without inventing an admin/manager default.

    A supervisor with exactly one active assigned/delegated governorate gets that
    governorate automatically. Supervisors with multiple governorates must select
    one explicitly; Admin and Manager always make an explicit work-scope choice.
    """
    if not has_request_context():
        return None
    u = me()
    if not u:
        return None

    rs = roles(u)
    scoped_roles = {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'}
    current_scope_role = next(iter(rs & scoped_roles), None)
    allowed_ids = {g.id for g in scope_governorates_for_user(u)}

    # The shell selector uses a dedicated query key so choosing a work scope
    # never overwrites a page's own governorate filter (especially the global
    # mission directory). Keep manager_governorate_id as a backwards-compatible
    # legacy key; governorate_id now belongs to the page's filter controls.
    raw = request.args.get('work_governorate_id') or request.args.get('manager_governorate_id') or ''
    if raw.isdigit():
        gid = int(raw)
        if gid in allowed_ids and Governorate.query.filter_by(id=gid, is_active=True).first():
            session['operational_governorate_id'] = gid
            session['operational_scope_uid'] = u.id
            session['operational_scope_role'] = current_scope_role

    selected = session.get('operational_governorate_id')
    scope_uid = session.get('operational_scope_uid')
    scope_role = session.get('operational_scope_role')
    if scope_uid != u.id or scope_role != current_scope_role:
        session.pop('operational_governorate_id', None)
        session.pop('operational_scope_uid', None)
        session.pop('operational_scope_role', None)
        selected = None

    # An assignment can be revoked while the session is still alive. A saved
    # governorate is valid only while it remains inside the current user's scope.
    if selected is not None:
        selected_text = str(selected).strip()
        if not selected_text.isdigit():
            selected = None
        else:
            selected_int = int(selected_text)
            valid = (
                selected_int in allowed_ids
                and Governorate.query.filter_by(id=selected_int, is_active=True).first() is not None
            )
            if valid:
                selected = selected_int
            else:
                selected = None
        if selected is None:
            session.pop('operational_governorate_id', None)
            session.pop('operational_scope_uid', None)
            session.pop('operational_scope_role', None)

    # The only implicit work-scope selection is the unambiguous supervisor case.
    # Admin and Manager remain unselected until they deliberately choose a scope.
    if selected is None and current_scope_role == 'مشرف محافظة' and len(allowed_ids) == 1:
        selected = next(iter(allowed_ids))
        session['operational_governorate_id'] = selected
        session['operational_scope_uid'] = u.id
        session['operational_scope_role'] = current_scope_role

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


def readable_branch_ids():
    """Return every active branch for shared read-only employee/movement views.

    This deliberately does not consult the selected work-governorate. Callers
    must still use `can_manage_employee` / `can_manage_movement` for writes.
    """
    if not can('view_reports'):
        return []
    return [
        branch.id
        for branch in Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True)
        .order_by(Branch.id.asc())
        .all()
    ]


def governorate_ok(i):
    """Return whether a governorate is inside the user's effective operational scope."""
    try:
        return i is not None and int(i) in set(gids())
    except (TypeError, ValueError):
        return False


def branch_ok(i):
    try:
        return i is not None and int(i) in set(bids())
    except (TypeError, ValueError):
        return False


def allowed_create_user(role):
    """Only formal login roles can be assigned to user accounts."""
    return 'مسؤول التطبيق' in roles() and role in LOGIN_ROLES


def allowed_target_user(target):
    """User-account administration is reserved for the application administrator."""
    return bool(target and target.is_active and 'مسؤول التطبيق' in roles())


def can_manage_employee(e):
    """Mutations require the selected work governorate, even from global read pages."""
    if not e or not can('manage_employees'):
        return False
    branch = db.session.get(Branch, e.branch_id) if getattr(e, 'branch_id', None) else None
    if not branch or not getattr(branch, 'is_active', False):
        return False
    governorate = getattr(branch, 'governorate', None)
    if not governorate or not getattr(governorate, 'is_active', False):
        return False
    selected = scope_governorate_id()
    # No mutations from cross-governorate search/profile pages without an
    # explicitly selected and authorized work governorate. Supervisors with a
    # single unambiguous assigned governorate are resolved by scope_governorate_id.
    return bool(selected and governorate.id == int(selected) and branch_ok(branch.id))


def can_manage_movement_employee(e, movement_type=None):
    """Return whether the current user may select an employee for a movement.

    Assignment creation has intentionally wider employee reach for governorate
    supervisors; ordinary employee management remains branch-scoped. Keeping
    this rule here prevents movement blueprints from duplicating role logic.
    """
    if not e or not getattr(e, 'is_active', False):
        return False
    # A movement cannot be registered for an employee whose current branch or
    # parent governorate is inactive, even when the actor has global assignment
    # scope. This is a data-validity rule, not a restriction to the work governorate.
    employee_branch = getattr(e, 'branch', None)
    employee_governorate = getattr(employee_branch, 'governorate', None) if employee_branch else None
    if (
        not employee_branch
        or not getattr(employee_branch, 'is_active', False)
        or not employee_governorate
        or not getattr(employee_governorate, 'is_active', False)
    ):
        return False
    rs = roles()
    # Transactional selection is not a global directory read. It must always be
    # inside the selected work-governorate, even if called from a global page.
    if movement_type:
        employee_governorate_id = employee_branch.governorate_id
        selected = scope_governorate_id()
        if not selected or employee_governorate_id != int(selected) or not branch_ok(e.branch_id):
            return False
    if 'مسؤول التطبيق' in rs:
        return True
    if rs & {'مشرف محافظة', 'Manager Application Support'} and movement_type == 'انتداب':
        return True
    return branch_ok(e.branch_id)


def can_manage_movement_destination(branch, movement_type=None):
    """Return whether a movement destination branch is selectable.

    Assignment destinations intentionally follow the same wider scope as
    assignment employee selection for governorate supervisors.
    """
    if not branch or not getattr(branch, 'is_active', False):
        return False
    # A destination is selectable only when both the branch and its parent
    # governorate are active. Global cross-governorate scope does not bypass this.
    destination_governorate = getattr(branch, 'governorate', None)
    if not destination_governorate or not getattr(destination_governorate, 'is_active', False):
        return False
    rs = roles()
    if 'مسؤول التطبيق' in rs:
        return True
    if rs & {'مشرف محافظة', 'Manager Application Support'} and movement_type == 'انتداب':
        return True
    return branch_ok(branch.id)


def movement_is_closed(m):
    """Return whether a movement/mission is closed, including legacy records."""
    from .movement_state import assignment_is_closed

    return assignment_is_closed(m)


def can_view_movement(m=None):
    """Allow read-only movement visibility across active governorates.

    All official roles may inspect operational records and their history across
    governorates. The selected work governorate is deliberately enforced by
    `can_manage_employee`, `can_manage_movement` and mutation endpoints, not by
    a read-only permission check. This prevents a global report from linking to
    a record that cannot be inspected, while never granting edit rights.
    """
    if not can('view_reports'):
        return False
    if m is None:
        return True
    return bool(getattr(m, 'is_active', False))


def can_print_mission(m=None):
    """Return whether the current user may view/print an assignment mission.

    Printing is a read operation and must not inherit mutation permissions.
    Keeping the mission-specific checks here prevents print routes from
    independently rebuilding the same authorization rule.
    """
    return bool(
        m
        and getattr(m, 'is_active', False)
        and getattr(m, 'movement_type', None) == 'انتداب'
        and can('view_reports')
        and can_view_movement(m)
    )


def can_manage_movement(m=None):
    rs = roles()
    if not can('manage_movements'):
        return False
    # Mutation authorization always requires an explicit authorized work scope,
    # independent of the current page. Global reports remain read-only across all
    # governorates. The source employee (not the destination) must be in scope.
    selected = scope_governorate_id()
    if not selected:
        return False
    if m is not None:
        employee = getattr(m, 'employee', None)
        branch = getattr(employee, 'branch', None) if employee else None
        if (
            not branch
            or not getattr(branch, 'is_active', False)
            or not getattr(branch, 'governorate', None)
            or branch.governorate_id != int(selected)
            or not branch_ok(branch.id)
        ):
            return False
        # Closed assignments can only be changed through a request decided by
        # Manager Application Support; never show a generic edit affordance.
        if getattr(m, 'movement_type', None) == 'انتداب' and movement_is_closed(m):
            return False
    if 'مسؤول التطبيق' in rs:
        return True
    if 'Manager Application Support' in rs and can('manage_movements'):
        # The Manager can execute privileged lifecycle actions, but when using an
        # operational page the source employee must be inside the chosen work scope.
        if m is None:
            return True
        if not getattr(m, 'is_active', False) or not getattr(m, 'employee', None):
            return False
        if getattr(m, 'movement_type', None) == 'انتداب':
            return True
        return branch_ok(m.employee.branch_id)
    if 'مشرف محافظة' in rs and can('manage_movements'):
        # The supervisor may view missions globally, but mutation buttons/actions
        # on a scoped operational page are restricted to the selected governorate.
        if m is not None and getattr(m, 'movement_type', None) != 'انتداب':
            return bool(branch_ok(m.employee.branch_id))
        # Direct mutation of a closed assignment is prohibited for every role;
        # a Manager-approved request is handled through its dedicated service.
        return not movement_is_closed(m)
    # No legacy first-entry login role is accepted; organizational entry
    # assignments do not grant movement mutation permissions.
    return False
