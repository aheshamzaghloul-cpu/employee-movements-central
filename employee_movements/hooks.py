"""Request hooks: security headers, CSRF protection and template context."""

import hmac

from flask import abort, request, session

from . import __version__
from .access import (
    actual_roles,
    can,
    can_manage_employee,
    can_manage_movement,
    csrf_token,
    has_role,
    is_scope_required_endpoint,
    me,
    roles,
    scope_governorate_id,
    scope_governorates_for_user,
    user_branch_ids,
    user_gov_ids,
    user_permissions,
    user_roles,
)
from .assignments import (
    assignment_state,
    assignment_supervisor,
    branch_entry,
    current_assignment_for_employee,
    entries_for_supervisor,
    supervisor_for_entry,
)
from .constants import ASSIGNMENT_ALERT_DAYS, ASSIGNMENT_STATES, LOGIN_ROLES, PERMISSIONS
from .extensions import db
from .models import Governorate


def inject_context():
    u = me()
    real_roles = actual_roles(u)
    active_role = session.get('active_role') if u else None
    if active_role not in real_roles:
        active_role = None
    return {
        'app_version': __version__,
        'me': u,
        'roles': roles(),
        'real_roles': real_roles,
        'login_real_roles': real_roles & set(LOGIN_ROLES),
        'active_role': active_role,
        'csrf': csrf_token(),
        'user_roles': user_roles,
        'user_permissions': user_permissions,
        'can': can,
        'has_role': has_role,
        'PERMISSIONS': PERMISSIONS,
        'user_gov_ids': user_gov_ids,
        'user_branch_ids': user_branch_ids,
        'assignment_state': assignment_state,
        'current_assignment_for_employee': current_assignment_for_employee,
        'assignment_supervisor': assignment_supervisor,
        'supervisor_for_entry': supervisor_for_entry,
        'entries_for_supervisor': entries_for_supervisor,
        'branch_entry': branch_entry,
        'can_manage_employee': can_manage_employee,
        'can_manage_movement': can_manage_movement,
        'ASSIGNMENT_STATES': ASSIGNMENT_STATES,
        'ASSIGNMENT_ALERT_DAYS': ASSIGNMENT_ALERT_DAYS,
        'scope_required': bool(
            (
                u
                and (
                    ('مسؤول التطبيق' in roles(u) or 'مشرف محافظة' in roles(u) or 'Manager Application Support' in roles(u))
                    and is_scope_required_endpoint()
                )
            ),
        ),
        'scope_selected': scope_governorate_id() if u and is_scope_required_endpoint() else None,
        'scope_governorates': scope_governorates_for_user(u),
        'scope_governorate': (
            db.session.get(Governorate, scope_governorate_id())
            if u and scope_governorate_id()
            else None
        ),
    }


def security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault(
        'X-Frame-Options',
        'SAMEORIGIN' if request.path.startswith('/assistant') else 'DENY',
    )
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    resp.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    resp.headers.setdefault('Content-Security-Policy', CONTENT_SECURITY_POLICY)
    if request.is_secure:
        resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return resp


CSRF_EXEMPT_ENDPOINTS = frozenset()

CONTENT_SECURITY_POLICY = '; '.join(
    (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "frame-ancestors 'self'",
        "base-uri 'self'",
        "form-action 'self'",
    )
)


def csrf_check():
    """Reject state-changing requests that do not carry the session CSRF token."""
    if request.method != 'POST' or request.endpoint in CSRF_EXEMPT_ENDPOINTS:
        return None
    token = request.form.get('_csrf') or ''
    expected = session.get('csrf') or ''
    if not token or not expected or not hmac.compare_digest(token, expected):
        abort(400, 'CSRF token invalid')
    return None


def register_hooks(app):
    """Attach request hooks, the Jinja context processor and template helpers."""
    from markupsafe import Markup, escape

    def nl2br(value):
        """Escape text, then turn newlines into <br>. Pre-escaped ``Markup`` passes through."""
        if isinstance(value, Markup):
            return Markup(value.replace('\n', Markup('<br>')))
        return Markup(escape(value or '').replace('\n', Markup('<br>')))

    app.before_request(csrf_check)
    app.after_request(security_headers)
    app.context_processor(inject_context)
    app.add_template_filter(nl2br, 'nl2br')
    app.jinja_env.globals['actual_roles'] = actual_roles
