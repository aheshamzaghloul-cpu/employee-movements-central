"""Request hooks: security headers, CSRF protection and template context."""

import hmac
import json
import logging
import re
import time
from urllib.parse import urlsplit
from io import BytesIO
from tempfile import SpooledTemporaryFile

from flask import Request, abort, current_app, g, jsonify, request, session
from werkzeug.datastructures import ImmutableMultiDict
from werkzeug.formparser import FormDataParser

from . import __version__
from .access import (
    actual_roles,
    branch_ok,
    can,
    can_manage_employee,
    can_manage_movement,
    can_view_movement,
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

logger = logging.getLogger(__name__)


class ScreenshotInMemoryRequest(Request):
    """Keep bounded ServiceDesk ticket-image uploads in memory, never temp files."""

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        if self.endpoint in {'missions.mission_from_screenshot_scan', 'missions.mission_ticket_image_save'}:
            # apply_request_size_limit() caps the full multipart request at 3 MiB
            # before CSRF parsing accesses request.form. Thus this memory buffer
            # remains bounded and Werkzeug never spools this image to disk.
            return BytesIO()
        # Preserve Werkzeug's normal bounded spooling behavior for all other
        # uploads without relying on its deprecated _get_file_stream parent.
        return SpooledTemporaryFile(max_size=500 * 1024, mode='w+b')

    def _parse_form_data(self, stream):
        """Use an explicit parser so memory-only screenshot uploads survive Werkzeug 4."""
        parser = FormDataParser(
            stream_factory=self._get_file_stream,
            max_form_memory_size=self.max_form_memory_size,
            max_content_length=self.max_content_length,
            max_form_parts=getattr(self, 'max_form_parts', None),
            cls=ImmutableMultiDict,
            silent=True,
        )
        _, form, files = parser.parse(
            stream=stream,
            mimetype=self.mimetype,
            content_length=self.content_length,
            options=self.mimetype_params,
        )
        return form, files


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
        'branch_ok': branch_ok,
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
        'can_view_movement': can_view_movement,
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
    if current_app.config.get('CSP_REPORT_ONLY'):
        # Transitional, intentionally report-only: captures violations so inline
        # scripts/styles and event handlers can be migrated without breaking users.
        resp.headers.setdefault('Content-Security-Policy-Report-Only', CSP_REPORT_ONLY_POLICY)
    if request.is_secure:
        resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    if request.endpoint == 'security_csp_report':
        resp.headers['Cache-Control'] = 'no-store'
    # Personnel, movement, user, audit and administrative pages must never be
    # retained by browser or intermediary caches after an authenticated visit.
    # Keep static assets cacheable; apply this to all other responses carrying
    # an authenticated session, not only the historical report endpoint list.
    private_authenticated_response = bool(session.get('uid')) and request.endpoint != 'static'
    if request.endpoint in PRIVATE_REPORT_ENDPOINTS or private_authenticated_response:
        resp.headers['Cache-Control'] = 'private, no-store, max-age=0'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
    started = getattr(g, '_request_started_at', None)
    if started is not None:
        duration_ms = (time.perf_counter() - started) * 1000
        threshold = max(0, int(current_app.config.get('SLOW_REQUEST_LOG_MS', 1500)))
        if resp.status_code >= 500 or (threshold and duration_ms >= threshold):
            current_app.logger.warning(
                'request_telemetry endpoint=%s method=%s status=%s duration_ms=%.1f',
                request.endpoint or 'unmatched', request.method, resp.status_code, duration_ms,
            )
    return resp


CSRF_EXEMPT_ENDPOINTS = frozenset()

# These authenticated report/document endpoints can contain personnel data.
# Do not let browsers or intermediary shared caches retain their response bodies.
PRIVATE_REPORT_ENDPOINTS = frozenset({
    'reports.manager_hub',
    'reports.audit',
    'reports.reports_missions',
    'reports.reports',
    'reports.employee_type_report',
    'reports.employee_type_report_xlsx',
    'reports.employee_type_report_csv',
    'reports.report_csv',
    'missions.mission_print_list',
    'missions.mission_print_all',
    'missions.mission_export_xlsx',
    'missions.mission_pdf',
    'missions.mission_print_date',
    'missions.mission_print_date_save',
    'missions.mission_print',
    'missions.mission_edit_requests',
    'missions.mission_edit_request_review',
    'missions.mission_monthly_aggregation',
})

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

# Candidate policy used only in report-only mode until inline handlers/styles are migrated.
CSP_REPORT_ONLY_POLICY = '; '.join((
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "font-src 'self'",
    "img-src 'self' data:",
    "frame-ancestors 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "report-uri /csp-report",
))


def _safe_csp_report_value(value, *, url=False):
    """Sanitize a small report field before it reaches logs."""
    if not isinstance(value, (str, int, float)):
        return ''
    text = str(value).replace('\r', ' ').replace('\n', ' ').replace('\x00', '')[:300]
    if url and text:
        try:
            parsed = urlsplit(text)
            if parsed.scheme in {'data', 'blob'}:
                text = f'{parsed.scheme}:'
            elif parsed.scheme and parsed.netloc:
                text = f'{parsed.scheme}://{parsed.netloc}{parsed.path[:140]}'
            elif text.startswith('/'):
                text = text.split('?', 1)[0].split('#', 1)[0][:140]
            elif parsed.scheme:
                text = f'{parsed.scheme}:'
            else:
                text = '[non-url]'
        except ValueError:
            text = '[invalid-url]'
    return re.sub(r'[\x00-\x1f\x7f]', '', text)[:180]


def receive_csp_report():
    """Accept browser CSP violation reports without CSRF or logging full page URLs."""
    if request.mimetype not in {'application/csp-report', 'application/reports+json', 'application/json'}:
        return jsonify(error='unsupported media type'), 415
    limiter_registry = current_app.extensions.setdefault('csp_report_limiters', {})
    limiter = limiter_registry.get('global')
    if limiter is None:
        from .ratelimit import RateLimiter
        limiter = RateLimiter(120, 60, redis_url=current_app.config.get('REDIS_URL'), key_prefix=f"employee-movements:{current_app.config.get('APP_ENV', 'production')}:csp-report")
        limiter_registry['global'] = limiter
    client_key = 'global'
    if not limiter.allow(client_key):
        return '', 429

    try:
        payload = json.loads(request.get_data(cache=False, as_text=True) or 'null')
    except (ValueError, TypeError):
        payload = None
    if not isinstance(payload, (dict, list)):
        return '', 204
    entries = payload if isinstance(payload, list) else [payload]
    for entry in entries[:10]:
        if not isinstance(entry, dict):
            continue
        report = entry.get('csp-report') if isinstance(entry.get('csp-report'), dict) else entry.get('body')
        if not isinstance(report, dict):
            report = entry
        directive = _safe_csp_report_value(report.get('effective-directive') or report.get('violated-directive'))
        blocked = _safe_csp_report_value(report.get('blocked-uri'), url=True)
        source = _safe_csp_report_value(report.get('source-file'), url=True)
        status = _safe_csp_report_value(report.get('status-code'))
        logger.info('CSP violation reported: directive=%s blocked=%s source=%s status=%s', directive, blocked, source, status)
    return '', 204


def apply_request_size_limit():
    """Set a bounded body size before any hook parses form data."""
    default_limit = current_app.config.get('MAX_CONTENT_LENGTH', 2 * 1024 * 1024)
    if request.endpoint == 'security_csp_report':
        limit = 32 * 1024
    elif request.endpoint == 'excel_import.excel_import_preview':
        limit = current_app.config.get('EXCEL_UPLOAD_MAX_CONTENT_LENGTH', 16 * 1024 * 1024)
    elif request.endpoint in {'missions.mission_from_screenshot_scan', 'missions.mission_ticket_image_save'}:
        # Allow multipart framing around a ticket image capped at 2 MiB in each route.
        limit = current_app.config.get('SCREENSHOT_UPLOAD_MAX_CONTENT_LENGTH', 3 * 1024 * 1024)
    else:
        limit = default_limit
    # Flask 3.1 / Werkzeug 3.1 supports a per-request maximum, which allows the
    # upload route to be larger without relaxing limits for normal form posts.
    request.max_content_length = limit
    return None


def csrf_check():
    """Reject state-changing requests that do not carry the session CSRF token."""
    if request.method != 'POST' or request.endpoint in CSRF_EXEMPT_ENDPOINTS or request.endpoint == 'security_csp_report':
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

    # This must run before csrf_check, because request.form parsing may consume
    # the multipart body and enforce the configured size limit.
    # Browser-generated CSP reports are deliberately the only additional
    # unauthenticated POST endpoint. They are size-capped, rate-limited, and
    # sanitized; they never mutate business data.
    app.add_url_rule('/csp-report', endpoint='security_csp_report', view_func=receive_csp_report, methods=['POST'])
    def mark_request_start():
        g._request_started_at = time.perf_counter()

    def strip_legacy_assistant_cookie_state():
        """Remove plaintext plans/context from cookies created by older releases."""
        legacy_pending = ('assistant_manager_pending', 'assistant_pending')
        legacy_context = ('assistant_workspace_context', 'assistant_context_employee_id')
        found_pending = any(key in session for key in legacy_pending)
        for key in (*legacy_pending, *legacy_context):
            session.pop(key, None)
        if found_pending:
            # Harmless one-bit marker lets the next assistant confirmation fail
            # closed with a clear message instead of silently using old data.
            session['_assistant_legacy_pending_discarded'] = True
        return None

    app.before_request(mark_request_start)
    app.before_request(apply_request_size_limit)
    app.before_request(strip_legacy_assistant_cookie_state)
    app.before_request(csrf_check)
    app.after_request(security_headers)
    app.context_processor(inject_context)
    app.add_template_filter(nl2br, 'nl2br')
    app.jinja_env.globals['actual_roles'] = actual_roles
