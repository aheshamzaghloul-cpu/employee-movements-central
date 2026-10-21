"""Assignment missions (مأموريات): edit, close, print and PDF."""

import secrets
from datetime import datetime, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from ..access import (
    bids,
    branch_ok,
    can,
    can_manage_movement,
    can_manage_movement_destination,
    can_manage_movement_employee,
    can_print_mission,
    can_view_movement,
    log,
    me,
    movement_is_closed,
    readable_branch_ids,
    req,
    roles,
    scope_governorate_id,
)
from ..extensions import db
from ..movement_state import assignment_closed_filter
from ..models import (
    Branch,
    Employee,
    Governorate,
    MissionEditRequest,
    MissionTicketImage,
    MissionTicketImageDraft,
    Movement,
    User,
)
from ..services.mission_documents import (
    mission_export_xlsx as build_mission_export_xlsx,
    mission_state_label,
    mission_template_pdf,
)
from ..services.mission_edit_request import (
    create_mission_edit_request,
    list_pending_mission_edit_requests,
    mission_edit_request_review_context,
    validate_and_execute_mission_edit_request,
)
from ..services.mission_lifecycle import apply_mission_edit, close_mission
from ..services.mission_ticket_resolution import (
    _ticket_mission_basic_branch_alias_matches,
    _ticket_mission_branch_choices,
    _ticket_mission_branches,
    _ticket_mission_employee,
    _ticket_mission_employee_suggestions,
    _ticket_mission_save_branch_alias,
    _ticket_mission_save_job_code_alias,
)
from ..services.ticket_matching import entity_name_similarity, normalize_job_code
from ..services.ticket_mission_rules import should_create_mission
from ..validation import (
    lock_employee_for_movement,
    lock_movement_for_employee,
    movement_overlaps,
    parse_date,
    record_movement_history,
    validate_movement_fields,
)

bp = Blueprint('missions', __name__)


def _safe_mission_date(value):
    """Parse a mission date without letting malformed form input become HTTP 500.

    ``parse_date`` deliberately raises ``ValueError`` so callers can distinguish
    malformed dates from omitted dates. Mission routes translate that into a
    user-facing validation response before any mutation is attempted.
    """
    try:
        return parse_date(value) if value else None
    except (TypeError, ValueError):
        return None


_TICKET_FIELD_LABELS = {
    'basic_branch_name': 'اسم الفرع الأساسي',
    'destination_branch_name': 'الفرع المحول إليه',
    'job_code': 'الكود الوظيفي',
    'destination_is_basic': 'هل الفرع المحول إليه فرعك الأساسي؟',
    'needs_mission': 'هل تحتاج مأمورية؟',
    'from_date': 'من يوم',
    'to_date': 'إلى يوم',
}


_TICKET_IMAGE_DRAFT_TTL = timedelta(minutes=30)


def _cleanup_expired_ticket_image_drafts(*, commit=True):
    cutoff = datetime.utcnow() - _TICKET_IMAGE_DRAFT_TTL
    deleted = MissionTicketImageDraft.query.filter(
        MissionTicketImageDraft.created_at < cutoff,
    ).delete(synchronize_session=False)
    if deleted and commit:
        db.session.commit()
    return deleted


def _ticket_mission_context(*, fields=None, scan_complete=False, error='', warning='', selected_destination_id='', employee_match=None, employee_suggestions=None, branch_suggestions=None, alias_notice='', image_draft_token='', ticket_image_saved=False, expected_employee=None, expected_employee_id='', expected_employee_confirmation_needed=False):
    return render_template(
        'mission_from_screenshot.html',
        fields=fields or {},
        scan_complete=scan_complete,
        error=error,
        warning=warning,
        selected_destination_id=str(selected_destination_id or ''),
        destination_branches=_ticket_mission_branches(),
        employee_match=employee_match,
        employee_suggestions=employee_suggestions or [],
        branch_suggestions=branch_suggestions or [],
        alias_notice=alias_notice,
        image_draft_token=image_draft_token,
        ticket_image_saved=ticket_image_saved,
        expected_employee=expected_employee,
        expected_employee_id=str(expected_employee_id or (expected_employee.id if expected_employee else '')),
        expected_employee_confirmation_needed=bool(expected_employee_confirmation_needed),
        field_labels=_TICKET_FIELD_LABELS,
    )


def _ticket_expected_employee(raw_id):
    """Resolve the optional homepage-selected employee without broadening access."""
    raw_id = str(raw_id or '').strip()
    if not raw_id:
        return None
    if not raw_id.isdigit():
        return None
    employee = db.session.get(Employee, int(raw_id))
    if (
        not employee or not employee.is_active or not employee.branch or not employee.branch.is_active
        or not employee.branch.governorate or not employee.branch.governorate.is_active
        or not can_manage_movement_employee(employee, 'انتداب')
    ):
        return None
    return employee


def _require_ticket_mission_access():
    if not can('manage_movements') or not can_manage_movement():
        abort(403)


@bp.get('/missions/from-screenshot')
@req
def mission_from_screenshot():
    """Screen for reading a ticket and attaching its image to the resulting mission."""
    _require_ticket_mission_access()
    _cleanup_expired_ticket_image_drafts()
    requested_id = (request.args.get('expected_employee_id') or '').strip()
    expected_employee = _ticket_expected_employee(requested_id) if requested_id else None
    if requested_id and not expected_employee:
        return _ticket_mission_context(error='الموظف المختار غير متاح ضمن صلاحياتك الحالية. أعد البحث عنه من الرئيسية.', expected_employee_id='')
    return _ticket_mission_context(expected_employee=expected_employee, expected_employee_id=requested_id)


@bp.post('/missions/from-screenshot/scan')
@req
def mission_from_screenshot_scan():
    """Read a ticket locally, then stage a sanitized image for the review-to-create step."""
    _require_ticket_mission_access()
    expected_employee_id = (request.form.get('expected_employee_id') or '').strip()
    expected_employee = _ticket_expected_employee(expected_employee_id) if expected_employee_id else None
    if expected_employee_id and not expected_employee:
        return _ticket_mission_context(error='الموظف المختار غير متاح ضمن صلاحياتك الحالية. أعد البحث عنه من الرئيسية.')
    def scan_error(message):
        return _ticket_mission_context(error=message, expected_employee=expected_employee, expected_employee_id=expected_employee_id)
    upload = request.files.get('screenshot')
    if not upload or not upload.filename:
        return scan_error('اختر صورة التيكيت أولًا.')
    try:
        from io import BytesIO
        import warnings
        from PIL import Image, UnidentifiedImageError
        from ..services.ticket_screenshot_ocr import MAX_IMAGE_PIXELS, SUPPORTED_FORMATS, extract_ticket_fields

        image_bytes = upload.stream.read(2 * 1024 * 1024 + 1)
        if not image_bytes:
            return scan_error('الملف فارغ. اختر صورة تيكيت صالحة.')
        if len(image_bytes) > 2 * 1024 * 1024:
            return scan_error('حجم الصورة أكبر من 2 ميجابايت. قصّ الصورة حول النموذج ثم أعد المحاولة.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            try:
                probe = Image.open(BytesIO(image_bytes))
                image_format = (probe.format or '').upper()
                if image_format not in SUPPORTED_FORMATS:
                    return scan_error('الصيغ المدعومة هي PNG وJPG وWEBP فقط.')
                if probe.width * probe.height > MAX_IMAGE_PIXELS:
                    return scan_error('أبعاد الصورة أكبر من الحد المسموح.')
                probe.verify()
                with Image.open(BytesIO(image_bytes)) as image:
                    fields = extract_ticket_fields(image)
                from ..services.ticket_image_storage import normalize_ticket_image
                stored_image_bytes, stored_image_mime, stored_image_sha256 = normalize_ticket_image(image_bytes)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                return scan_error('تعذر فتح الصورة. تأكد أنها لقطة شاشة سليمة بصيغة PNG أو JPG أو WEBP.')
    except RuntimeError as exc:
        return scan_error(str(exc))
    except ValueError as exc:
        return scan_error(str(exc))
    except ImportError:
        return scan_error('قارئ الصور المحلي غير مهيأ على الخادم. يلزم تثبيت مكونات OCR المحلية قبل استخدام هذه الميزة.')

    # Keep the literal OCR result separate from the normalized official code so
    # a user can explicitly choose to remember a corrected spelling after review.
    fields['source_job_code'] = fields.get('job_code', '')
    branches = _ticket_mission_branches()
    selected_destination_id, branch_suggestions, branch_warning = _ticket_mission_branch_choices(
        fields.get('destination_branch_name', ''), branches
    )

    employee_match = None
    employee_suggestions = []
    employee_error = ''
    code_normalization_notice = ''
    selected_employee_code_notice = ''
    expected_employee_confirmation_needed = False
    if expected_employee:
        recognized_code = str(fields.get('job_code') or '').strip()
        fields['recognized_job_code'] = recognized_code
        if recognized_code and normalize_job_code(recognized_code) != normalize_job_code(expected_employee.job_code or ''):
            selected_employee_code_notice = 'الكود الذي قرأته الصورة لا يطابق الموظف الذي اخترته في الرئيسية. راجع الصورة وهوية الموظف والفرع الأساسي؛ يلزم تأكيد صريح قبل التسجيل.'
            expected_employee_confirmation_needed = True
        elif not recognized_code:
            selected_employee_code_notice = 'لم يُقرأ الكود بوضوح من الصورة. تم تحديد الموظف من اختيارك في الرئيسية؛ راجع الصورة وهوية الموظف قبل التسجيل.'
            expected_employee_confirmation_needed = True
        fields['job_code'] = expected_employee.job_code or ''
        employee_match = expected_employee
    elif fields.get('job_code'):
        employee_match, employee_error = _ticket_mission_employee(fields['job_code'])
        if employee_match:
            employee_error = ''
            raw_code = fields.get('job_code', '')
            if normalize_job_code(raw_code) != normalize_job_code(employee_match.job_code or ''):
                fields['job_code'] = employee_match.job_code or raw_code
                code_normalization_notice = 'تمت مطابقة الكود مع موظف واحد، وعُرض الكود الرسمي من سجل الموظف.'
        else:
            employee_suggestions = _ticket_mission_employee_suggestions(
                fields['job_code'], fields.get('basic_branch_name', '')
            )
    warning_parts = [branch_warning, code_normalization_notice, selected_employee_code_notice]
    missing = [label for key, label in _TICKET_FIELD_LABELS.items() if not fields.get(key)]
    if employee_error:
        warning_parts.append(employee_error)
    if employee_suggestions:
        warning_parts.append('ظهرت أسماء موظفين محتملة بسبب تقارب الكود؛ اختر المرشح الصحيح يدويًا. لن نعتمد كودًا متقاربًا تلقائيًا.')
    if missing:
        warning_parts.append('راجع الحقول التي لم تُقرأ بوضوح: ' + '، '.join(missing) + '.')
    warning = ' '.join(part for part in warning_parts if part)

    # Staging is database-backed (not a local temp file or browser cookie) so it
    # survives worker changes and ephemeral-container restarts during review.
    _cleanup_expired_ticket_image_drafts(commit=False)
    # Keep multiple tabs usable, but cap active drafts per user to avoid unbounded
    # abandoned uploads. Expired drafts are cleaned on route use and app startup.
    stale_user_drafts = (
        MissionTicketImageDraft.query
        .filter_by(uploaded_by=me().id)
        .order_by(MissionTicketImageDraft.created_at.desc())
        .offset(4)
        .all()
    )
    for stale_draft in stale_user_drafts:
        db.session.delete(stale_draft)
    image_draft_token = secrets.token_urlsafe(32)
    image_draft = MissionTicketImageDraft(
        token=image_draft_token,
        uploaded_by=me().id,
        image_data=stored_image_bytes,
        mime_type=stored_image_mime,
        sha256=stored_image_sha256,
        created_at=datetime.utcnow(),
    )
    db.session.add(image_draft)
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        # Do not log a traceback here: SQLAlchemy exceptions may include binary
        # image parameters or other ticket contents in their rendered SQL context.
        current_app.logger.error('Unable to stage a ServiceDesk ticket image (error=%s).', type(exc).__name__)
        return _ticket_mission_context(
            fields=fields,
            scan_complete=True,
            error='تمت قراءة الحقول، لكن تعذر حفظ صورة التيكيت مؤقتًا. أعد رفع الصورة قبل تسجيل المأمورية.',
            warning=warning,
            selected_destination_id=selected_destination_id,
            employee_match=employee_match,
            employee_suggestions=employee_suggestions,
            branch_suggestions=branch_suggestions,
            expected_employee=expected_employee,
            expected_employee_id=expected_employee_id,
            expected_employee_confirmation_needed=expected_employee_confirmation_needed,
        )

    return _ticket_mission_context(
        fields=fields,
        scan_complete=True,
        warning=warning,
        selected_destination_id=selected_destination_id,
        employee_match=employee_match,
        employee_suggestions=employee_suggestions,
        branch_suggestions=branch_suggestions,
        image_draft_token=image_draft_token,
        ticket_image_saved=True,
        expected_employee=expected_employee,
        expected_employee_id=expected_employee_id,
        expected_employee_confirmation_needed=expected_employee_confirmation_needed,
    )


@bp.post('/missions/from-screenshot/create')
@req
def mission_from_screenshot_create():
    """Create a mission only when the destination is non-basic and a mission is requested."""
    _require_ticket_mission_access()
    form = request.form
    fields = {key: (form.get(key) or '').strip() for key in _TICKET_FIELD_LABELS}
    expected_employee_id = (form.get('expected_employee_id') or '').strip()
    expected_employee = _ticket_expected_employee(expected_employee_id) if expected_employee_id else None
    if expected_employee_id and not expected_employee:
        return _ticket_mission_context(fields=fields, scan_complete=True, error='الموظف المختار لم يعد متاحًا ضمن صلاحياتك. أعد تحديده من الرئيسية.', image_draft_token=(form.get('ticket_image_draft_token') or '').strip())
    source_job_code = (form.get('source_job_code') if 'source_job_code' in form else fields.get('job_code') or '').strip()[:100]
    fields['source_job_code'] = source_job_code
    # Keep non-sensitive review choices on validation errors as well. The image
    # itself remains in the short-lived database draft, never in form/session data.
    for option_name in (
        'confirm_selected_employee_code_mismatch',
        'remember_job_code_alias',
        'remember_basic_branch_alias',
        'remember_branch_alias',
    ):
        fields[option_name] = 'yes' if (form.get(option_name) or '').strip().lower() == 'yes' else ''
    expected_employee_confirmation_needed = bool(
        expected_employee and (
            not source_job_code
            or normalize_job_code(source_job_code) != normalize_job_code(expected_employee.job_code or '')
        )
    )
    destination_id_raw = (form.get('destination_branch_id') or '').strip()
    employee_match = None
    destination_id = int(destination_id_raw) if destination_id_raw.isdigit() else None
    expects_ticket_image = (form.get('ticket_image_required') or '').strip().lower() == 'yes'
    image_draft_token = (form.get('ticket_image_draft_token') or '').strip()
    ticket_image_draft = None
    if image_draft_token and len(image_draft_token) <= 64:
        # The draft is a single-use bridge between OCR review and mission create.
        # Lock it before validating/consuming it so parallel confirmation POSTs
        # cannot both create a mission from the same ticket image.
        ticket_image_draft = (
            MissionTicketImageDraft.query
            .filter_by(token=image_draft_token, uploaded_by=me().id)
            .with_for_update()
            .first()
        )
    if ticket_image_draft and ticket_image_draft.created_at < datetime.utcnow() - _TICKET_IMAGE_DRAFT_TTL:
        db.session.delete(ticket_image_draft)
        db.session.commit()
        ticket_image_draft = None
        image_draft_token = ''

    def reject(message):
        matched, match_error = ((expected_employee, '') if expected_employee else (_ticket_mission_employee(fields.get('job_code')) if fields.get('job_code') else (None, '')))
        employee_suggestions = []
        if not matched and fields.get('job_code'):
            employee_suggestions = _ticket_mission_employee_suggestions(
                fields.get('job_code'), fields.get('basic_branch_name', ''),
            )
        branch_suggestions = []
        if fields.get('destination_branch_name'):
            _, branch_suggestions, _ = _ticket_mission_branch_choices(
                fields.get('destination_branch_name'), _ticket_mission_branches(),
            )
        return _ticket_mission_context(
            fields=fields,
            scan_complete=expects_ticket_image,
            error=message or match_error,
            selected_destination_id=destination_id or '',
            employee_match=matched,
            employee_suggestions=employee_suggestions,
            branch_suggestions=branch_suggestions,
            image_draft_token=ticket_image_draft.token if ticket_image_draft else '',
            ticket_image_saved=bool(ticket_image_draft),
            expected_employee=expected_employee,
            expected_employee_id=expected_employee_id,
            expected_employee_confirmation_needed=expected_employee_confirmation_needed,
        )

    if expects_ticket_image and not ticket_image_draft:
        return reject('انتهت صلاحية صورة التيكيت أو لم تعد متاحة. أعد رفع الصورة وقراءتها قبل تسجيل المأمورية؛ لم يتم إنشاء أي حركة بعد.')

    if not should_create_mission(fields.get('destination_is_basic'), fields.get('needs_mission')):
        if fields.get('needs_mission') != 'yes':
            return reject('لم تُنشأ مأمورية: يجب أن تكون إجابة «هل تحتاج مأمورية؟» هي «نعم». لم يتم تسجيل أي حركة.')
        return reject('لم تُنشأ مأمورية: يجب أن تكون إجابة «هل الفرع المحول إليه فرعك الأساسي؟» هي «لا، ليس فرعي الأساسي». لم يتم تسجيل أي حركة.')
    if not fields.get('basic_branch_name'):
        return reject('اسم الفرع الأساسي مطلوب. راجع قراءته من الصورة.')
    if expected_employee:
        if expected_employee.job_code and normalize_job_code(fields.get('job_code') or '') != normalize_job_code(expected_employee.job_code):
            return reject('تم تغيير الكود الرسمي للموظف المختار. أعد تحديد الموظف من الرئيسية؛ لم تُسجّل المأمورية.')
        if expected_employee_confirmation_needed and (form.get('confirm_selected_employee_code_mismatch') or '').strip().lower() != 'yes':
            return reject('الكود في الصورة غير واضح أو مختلف عن الموظف المحدد. راجع الصورة والفرع الأساسي، ثم أكد صراحة أن الصورة تخص الموظف المختار قبل التسجيل.')
        employee, employee_error = expected_employee, ''
    else:
        if not fields.get('job_code'):
            return reject('الكود الوظيفي مطلوب لتحديد الموظف الصحيح.')
        employee, employee_error = _ticket_mission_employee(fields['job_code'])
        if employee_error or not employee:
            return reject(employee_error or 'تعذر تحديد الموظف.')
    # Lock/refresh the source employee before final ticket matching and overlap
    # validation so concurrent registrations cannot both pass against stale state.
    employee = lock_employee_for_movement(employee.id)
    if not employee or not employee.is_active or not can_manage_movement_employee(employee, 'انتداب'):
        return reject('الموظف لم يعد نشطًا أو لم يعد ضمن نطاق العمل المسموح. لم تُسجّل المأمورية.')
    if normalize_job_code(fields.get('job_code') or '') != normalize_job_code(employee.job_code or ''):
        return reject('تغير الكود الوظيفي المسجل أثناء المراجعة. أعد مطابقة الموظف قبل التسجيل.')
    if expected_employee and expected_employee.id != employee.id:
        return reject('تغير الموظف المحدد أثناء المراجعة. أعد تحديد الموظف قبل التسجيل.')
    if not destination_id:
        return reject('اختر الفرع المحول إليه من قائمة الفروع النشطة.')
    destination = db.session.get(Branch, destination_id)
    if (
        not destination
        or not destination.is_active
        or not destination.governorate
        or not destination.governorate.is_active
        or not can_manage_movement_destination(destination, 'انتداب')
    ):
        abort(403)
    actual_basic_branch = employee.branch
    branch_name_score = entity_name_similarity(
        fields['basic_branch_name'],
        ' '.join(part for part in (
            actual_basic_branch.name if actual_basic_branch else '',
            actual_basic_branch.governorate.name if actual_basic_branch and actual_basic_branch.governorate else '',
        ) if part),
    ) if actual_basic_branch else 0.0
    basic_branch_alias_match = _ticket_mission_basic_branch_alias_matches(
        fields['basic_branch_name'], actual_basic_branch,
    )
    if not actual_basic_branch or (not basic_branch_alias_match and branch_name_score < 0.52):
        registered_basic_branch = (
            ' · '.join(part for part in (
                actual_basic_branch.name if actual_basic_branch else '',
                actual_basic_branch.governorate.name if actual_basic_branch and actual_basic_branch.governorate else '',
            ) if part) or 'غير محدد'
        )
        return reject(
            f'اسم الفرع الأساسي في الصورة لا يطابق سجل الموظف بما يكفي. الفرع المسجل لهذا الموظف هو «{registered_basic_branch}». '
            'صحح الكود الوظيفي أو راجع اسم الفرع قبل التسجيل.'
        )
    if destination.id == employee.branch_id:
        return reject('الفرع المختار هو الفرع الأساسي المسجل للموظف، بينما الإجابة تقول «لا، ليس فرعي الأساسي». اختر الفرع المحول إليه الصحيح.')

    raw_from = fields.get('from_date', '')
    raw_to = fields.get('to_date', '')
    from_date = _safe_mission_date(raw_from)
    to_date = _safe_mission_date(raw_to)
    if not from_date or not to_date:
        return reject('يجب قراءة تاريخي «من يوم» و«إلى يوم» بصيغة صحيحة قبل التسجيل.')
    if to_date < from_date:
        return reject('تاريخ «إلى يوم» لا يجوز أن يسبق «من يوم».')
    validation = validate_movement_fields(
        'انتداب', None, destination.id, raw_from, raw_to, None,
        destination_scope_checked=True,
    )
    if validation:
        return reject(validation)
    overlap = movement_overlaps(employee.id, 'انتداب', raw_from, raw_to, None)
    if overlap:
        return reject(overlap)

    movement = Movement(
        employee_id=employee.id,
        movement_type='انتداب',
        leave_type=None,
        destination_branch_id=destination.id,
        from_date=from_date,
        to_date=to_date,
        permission_date=None,
        status='مسجلة',
        notes=None,
        is_active=True,
        created_by=me().id,
        created_at=datetime.utcnow(),
        assignment_state='ساري',
        mission_state='تحت التحرير',
    )
    db.session.add(movement)
    db.session.flush()
    if ticket_image_draft:
        db.session.add(MissionTicketImage(
            movement_id=movement.id,
            image_data=ticket_image_draft.image_data,
            mime_type=ticket_image_draft.mime_type,
            sha256=ticket_image_draft.sha256,
            uploaded_by=me().id,
            uploaded_at=datetime.utcnow(),
        ))
        db.session.delete(ticket_image_draft)
    record_movement_history(movement, None, 'مسجلة', 'ADD', 'تسجيل مأمورية من صورة تيكيت ServiceDesk بعد مراجعة الحقول السبعة')
    log('ADD', 'Movement', movement.id, 'إنشاء مأمورية من صورة تيكيت بعد مراجعة الحقول السبعة')
    alias_notice = ''
    alias_notices = []
    actual_basic_branch = employee.branch
    if form.get('remember_basic_branch_alias') == 'yes' and actual_basic_branch:
        _, basic_branch_alias_notice = _ticket_mission_save_branch_alias(
            fields.get('basic_branch_name', ''), actual_basic_branch, me().id
        )
        if basic_branch_alias_notice:
            alias_notices.append(basic_branch_alias_notice)
    if form.get('remember_branch_alias') == 'yes':
        _, branch_alias_notice = _ticket_mission_save_branch_alias(
            fields.get('destination_branch_name', ''), destination, me().id
        )
        if branch_alias_notice:
            alias_notices.append(branch_alias_notice)
    if form.get('remember_job_code_alias') == 'yes' and source_job_code and not expected_employee_confirmation_needed:
        _, job_code_alias_notice = _ticket_mission_save_job_code_alias(
            source_job_code, employee, me().id,
        )
        if job_code_alias_notice:
            alias_notices.append(job_code_alias_notice)
    db.session.commit()
    flash(f'تم تسجيل المأمورية للموظف «{employee.full_name}» إلى فرع «{destination.name}» بنجاح.' + (' تم حفظ صورة التيكيت وستظهر صفحةً ثانيةً في ملف PDF.' if ticket_image_draft else ''))
    for alias_notice in alias_notices:
        flash(alias_notice, 'info')
    return redirect('/reports/assignments/print-missions')
def _render_mission_edit_form(m, form_values=None, return_to=None):
    """Render mission edits with attempted values after a correctable validation error."""
    branches = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True)
        .order_by(Branch.name.asc()).all()
    )
    destination_governorates = (
        Governorate.query.filter(Governorate.is_active == True)
        .order_by(Governorate.name.asc()).all()
    )
    return render_template(
        'mission_edit.html',
        m=m,
        form_values=dict(form_values or {}),
        mission_display_state=mission_state_label(m),
        ticket_image_present=MissionTicketImage.query.filter_by(movement_id=m.id).first() is not None,
        branches=branches,
        destination_governorates=destination_governorates,
        return_to=_mission_center_return_url(return_to),
    )


@bp.get('/reports/assignments/mission-edit/<int:movement_id>')
@req
def mission_edit(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can('view_reports') or not can_manage_movement(m):
        abort(403)
    if mission_state_label(m) == 'مغلقة' and not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):
        flash('المأمورية مغلقة. أرسل طلب تعديل من مركز المأموريات ليعالجه الـManager.')
        return redirect(_mission_center_return_url())
    # The source employee is constrained by can_manage_movement(m); destination
    # choices remain global across active branches, matching the assignment rule.
    return _render_mission_edit_form(m)


@bp.post('/reports/assignments/mission-edit/<int:movement_id>')
@req
def mission_edit_save(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    if mission_state_label(m) == 'مغلقة':
        flash('لا تعدّل المأمورية المغلقة مباشرة. أرسل طلب تعديل ليعالجه الـManager.')
        return redirect(_mission_center_return_url(request.form.get('return_to')))
    locked_employee = lock_employee_for_movement(m.employee_id)
    if not locked_employee:
        abort(404)
    refreshed = lock_movement_for_employee(movement_id, locked_employee.id)
    if not refreshed or not refreshed.is_active or refreshed.movement_type != 'انتداب':
        abort(403)
    m = refreshed
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    if mission_state_label(m) == 'مغلقة':
        flash('لا تعدّل المأمورية المغلقة مباشرة. أرسل طلب تعديل ليعالجه الـManager.')
        return redirect(_mission_center_return_url(request.form.get('return_to')))
    dest_id = request.form.get('destination_branch_id', '').strip()
    destination = db.session.get(Branch, int(dest_id)) if dest_id.isdigit() else None
    raw_fd = request.form.get('from_date', '')
    raw_td = request.form.get('to_date', '')
    fd = _safe_mission_date(raw_fd)
    td = _safe_mission_date(raw_td)
    if (raw_fd and fd is None) or (raw_td and td is None):
        flash('تاريخ البداية أو النهاية غير صحيح. اختر تاريخًا صالحًا ثم حاول مرة أخرى.', 'warning')
        return _render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))
    if (
        not destination
        or not destination.is_active
        or not destination.governorate
        or not destination.governorate.is_active
        or not can_manage_movement_destination(destination, 'انتداب')
    ):
        flash('اختر جهة مأمورية صحيحة من الفروع النشطة والمسموح بها.', 'warning')
        return _render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))
    if not fd:
        flash('يجب إدخال تاريخ بداية صحيح.', 'warning')
        return _render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))
    # الانتداب المفتوح يظل بدون تاريخ نهاية في السجل. تاريخ (إلى) يمكن إدخاله
    # لاحقًا عند الإغلاق، أو إدخاله مؤقتًا لغرض طباعة المأمورية فقط.
    if td and td < fd:
        flash('تاريخ النهاية لا يجوز أن يسبق بداية الانتداب.', 'warning')
        return _render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))
    if mission_state_label(m) == 'مغلقة' and not td:
        flash('المأمورية المغلقة يجب أن تحتفظ بتاريخ نهاية. استخدم إعادة الفتح أولًا إذا أردت جعلها مفتوحة.')
        return _render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))
    overlap_end = td if td else None
    overlap = movement_overlaps(m.employee_id, 'انتداب', fd, overlap_end, None, m.id)
    if overlap:
        flash(overlap, 'warning')
        return _render_mission_edit_form(m, request.form.to_dict(), request.form.get('return_to'))
    # Authorization and input validation stay in the HTTP layer; the state change
    # and audit trail live in the mission lifecycle service.
    apply_mission_edit(m, destination, fd, td)
    flash('تم تعديل بيانات المأمورية بنجاح.')
    return redirect(_mission_center_return_url())


@bp.post('/reports/assignments/mission-ticket-image/<int:movement_id>')
@req
def mission_ticket_image_save(movement_id):
    """Attach or replace the ticket image on an existing mission, without creating a duplicate movement."""
    m = db.session.get(Movement, movement_id)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    if not can('manage_movements'):
        abort(403)
    # can_manage_movement() deliberately rejects closed missions to prohibit direct
    # edits. A ticket-image attachment is a separate evidence-repair operation: it
    # may be performed on a closed mission by the Manager only, and only while the
    # mission's source employee remains inside the Manager's selected work scope.
    if movement_is_closed(m):
        if (
            'Manager Application Support' not in roles()
            or not m.employee
            or not branch_ok(m.employee.branch_id)
        ):
            abort(403)
    elif not can_manage_movement(m):
        abort(403)
    if mission_state_label(m) != 'تحت التحرير' and 'Manager Application Support' not in roles():
        abort(403)

    upload = request.files.get('ticket_image')
    if not upload or not upload.filename:
        flash('اختر صورة تيكيت أولًا.')
        return redirect(url_for(
            'missions.mission_edit', movement_id=m.id,
            return_to=_mission_center_return_url(request.form.get('return_to')),
        ))

    try:
        from ..services.ticket_image_storage import MAX_TICKET_IMAGE_BYTES, normalize_ticket_image
        raw_image = upload.stream.read(MAX_TICKET_IMAGE_BYTES + 1)
        image_data, mime_type, sha256 = normalize_ticket_image(raw_image)
    except ValueError as exc:
        flash(str(exc))
        return redirect(url_for(
            'missions.mission_edit', movement_id=m.id,
            return_to=_mission_center_return_url(request.form.get('return_to')),
        ))
    except ImportError:
        flash('معالجة الصور غير متاحة على الخادم حاليًا؛ لم يتم تغيير المرفق الحالي.')
        return redirect(url_for(
            'missions.mission_edit', movement_id=m.id,
            return_to=_mission_center_return_url(request.form.get('return_to')),
        ))

    attachment = MissionTicketImage.query.filter_by(movement_id=m.id).first()
    replacing = attachment is not None
    if attachment is None:
        attachment = MissionTicketImage(movement_id=m.id)
        db.session.add(attachment)
    attachment.image_data = image_data
    attachment.mime_type = mime_type
    attachment.sha256 = sha256
    attachment.uploaded_by = me().id
    attachment.uploaded_at = datetime.utcnow()
    log('UPDATE', 'Movement', m.id, 'إرفاق أو استبدال صورة تيكيت المأمورية')
    try:
        db.session.commit()
    except SQLAlchemyError as exc:
        db.session.rollback()
        # Keep uploaded image bytes and SQL parameters out of application logs.
        current_app.logger.error(
            'Unable to persist a ticket image for mission %s (error=%s).', m.id, type(exc).__name__
        )
        flash('تعذر حفظ الصورة في قاعدة البيانات. لم يتم اعتماد التغيير؛ حاول مرة أخرى.')
        return redirect(url_for(
            'missions.mission_edit', movement_id=m.id,
            return_to=_mission_center_return_url(request.form.get('return_to')),
        ))

    flash(('تم استبدال' if replacing else 'تم إرفاق') + ' صورة التيكيت بالمأمورية. ستظهر كصفحة ثانية عند معاينة PDF أو طباعته.')
    return redirect(url_for(
        'missions.mission_edit', movement_id=m.id,
        return_to=_mission_center_return_url(request.form.get('return_to')),
    ))


def _mission_center_return_url(target=None):
    """Accept only local return paths inside the canonical mission center."""
    target = (
        target
        or request.form.get('return_to')
        or request.args.get('return_to')
        or ''
    ).strip()
    prefix = '/reports/assignments/print-missions'
    if (
        (target == prefix or target.startswith(prefix + '?'))
        and not any(char in target for char in ('\r', '\n', '\\'))
        and not target.startswith('//')
    ):
        return target
    return prefix


@bp.post('/reports/assignments/mission-close/<int:movement_id>')
@req
def mission_close(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    locked_employee = lock_employee_for_movement(m.employee_id)
    if not locked_employee:
        abort(404)
    refreshed = lock_movement_for_employee(movement_id, locked_employee.id)
    if not refreshed or not refreshed.is_active or refreshed.movement_type != 'انتداب':
        abort(403)
    m = refreshed
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    if mission_state_label(m) == 'مغلقة':
        flash('المأمورية مغلقة بالفعل.')
        return redirect('/reports/assignments/print-missions')
    if not m.from_date or not m.to_date:
        flash('لا يمكن إغلاق المأمورية قبل تسجيل تاريخي البداية والنهاية.')
        return redirect(url_for('missions.mission_edit', movement_id=m.id, return_to=_mission_center_return_url()))
    if m.to_date < m.from_date:
        flash('تاريخ نهاية المأمورية لا يجوز أن يسبق تاريخ بدايتها.')
        return redirect(url_for('missions.mission_edit', movement_id=m.id, return_to=_mission_center_return_url()))
    overlap = movement_overlaps(
        m.employee_id, 'انتداب', m.from_date, m.to_date, None, m.id,
    )
    if overlap:
        flash(overlap)
        return redirect(url_for('missions.mission_edit', movement_id=m.id, return_to=_mission_center_return_url()))
    close_mission(m)
    flash('تم إغلاق المأمورية.')
    return redirect(_mission_center_return_url())


@bp.post('/reports/assignments/mission-reopen/<int:movement_id>')
@req
def mission_reopen(movement_id):
    m = db.session.get(Movement, movement_id)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    # A direct reopen would bypass the mandatory manager review for a closed
    # mission. The Manager can set the approved final state to "تحت التحرير"
    # through the closed-mission edit-request workflow instead.
    flash('لا يمكن إعادة فتح المأمورية مباشرة. أرسل طلب تعديل ليعتمده الـManager أولًا.')
    return redirect(_mission_center_return_url())


def _render_mission_print_date_form(m, return_to=None, form_values=None, validation_error=''):
    """Render the temporary end-date form without discarding a correctable draft."""
    return render_template(
        'mission_print_date.html',
        m=m,
        return_to=_mission_center_return_url(return_to),
        form_values=dict(form_values or {}),
        validation_error=validation_error,
    )


@bp.get('/reports/assignments/mission-print-date/<int:movement_id>')
@req
def mission_print_date(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can_print_mission(m):
        abort(403)
    if m.to_date:
        return redirect(url_for('missions.mission_pdf', movement_id=m.id))
    if getattr(m, 'assignment_state', None) == 'مغلق' or mission_state_label(m) == 'مغلقة':
        flash('المأمورية مغلقة ولا يوجد لها تاريخ «إلى». أرسل طلب تعديل ليعالجه الـManager قبل الطباعة.')
        return redirect(_mission_center_return_url())
    return _render_mission_print_date_form(m, request.args.get('return_to'))


@bp.post('/reports/assignments/mission-print-date/<int:movement_id>')
@req
def mission_print_date_save(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can_print_mission(m):
        abort(403)
    if m.to_date:
        return redirect(url_for('missions.mission_pdf', movement_id=m.id))
    if getattr(m, 'assignment_state', None) == 'مغلق' or mission_state_label(m) == 'مغلقة':
        flash('المأمورية مغلقة ولا يوجد لها تاريخ «إلى». أرسل طلب تعديل ليعالجه الـManager قبل الطباعة.')
        return redirect(_mission_center_return_url())
    raw_print_to_date = request.form.get('print_to_date', '')
    print_to_date = _safe_mission_date(raw_print_to_date)
    if not print_to_date:
        return _render_mission_print_date_form(
            m,
            request.form.get('return_to'),
            {'print_to_date': raw_print_to_date},
            'أدخل تاريخ «إلى» صحيحًا للطباعة باستخدام التقويم.',
        )
    if m.from_date and print_to_date < m.from_date:
        return _render_mission_print_date_form(
            m,
            request.form.get('return_to'),
            {'print_to_date': raw_print_to_date},
            'تاريخ «إلى» لا يجوز أن يسبق تاريخ «من».',
        )
    employee = db.session.get(Employee, m.employee_id)
    branch = db.session.get(Branch, employee.branch_id) if employee else None
    destination = m.destination
    creator = db.session.get(User, m.created_by) if m.created_by else None
    ticket_image = MissionTicketImage.query.filter_by(movement_id=m.id).first()
    data = mission_template_pdf(
        m,
        employee,
        branch,
        destination,
        current_app.root_path,
        creator,
        print_to_date=print_to_date,
        closer=m.closed_by_user,
        ticket_image_data=ticket_image.image_data if ticket_image else None,
    )
    from flask import Response
    return Response(
        data,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename=mission-{m.id}.pdf'},
    )


@bp.get('/reports/assignments/mission-pdf/<int:movement_id>')
@req
def mission_pdf(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can_print_mission(m):
        abort(403)
    if not m.to_date:
        if (
            mission_state_label(m) == 'تحت التحرير'
            and getattr(m, 'assignment_state', None) != 'مغلق'
        ):
            return redirect(url_for('missions.mission_print_date', movement_id=m.id, return_to=_mission_center_return_url(request.form.get('return_to'))))
        flash('تاريخ «إلى» غير مسجل في مأمورية مغلقة. أرسل طلب تعديل ليعالجه الـManager ثم أعد الطباعة.')
        return redirect(_mission_center_return_url())
    employee = db.session.get(Employee, m.employee_id)
    branch = db.session.get(Branch, employee.branch_id) if employee else None
    destination = m.destination
    creator = db.session.get(User, m.created_by) if m.created_by else None
    ticket_image = MissionTicketImage.query.filter_by(movement_id=m.id).first()
    data = mission_template_pdf(
        m, employee, branch, destination, current_app.root_path, creator,
        closer=m.closed_by_user,
        ticket_image_data=ticket_image.image_data if ticket_image else None,
    )
    from flask import Response
    return Response(
        data,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename=mission-{m.id}.pdf'},
    )


@bp.get('/reports/assignments/print-missions')
@req
def mission_print_list():
    if not can('view_reports'):
        abort(403)
    # المدير المركزي ومسؤول التطبيق والمشرف يمكنهم متابعة المأموريات عبر المحافظات؛
    # نطاق المدير المركزي هنا شامل، مع بقاء باقي الصفحات التشغيلية خاضعة لنطاقها المعتاد.
    from ..services.mission_query import build_mission_report_context

    context = build_mission_report_context(
        roles=roles(),
        allowed_bids=readable_branch_ids(),
        args=request.args,
        paginate=True,
    )
    # Keep filters intact while changing only the page number.
    def _mission_page_url(page_number):
        query_args = request.args.to_dict()
        query_args['page'] = str(page_number)
        return url_for('missions.mission_print_list', **query_args)

    context['previous_page_url'] = _mission_page_url(context['page'] - 1) if context['page'] > 1 else None
    context['next_page_url'] = _mission_page_url(context['page'] + 1) if context['page'] < context['page_count'] else None
    start_page = max(1, context['page'] - 2)
    end_page = min(context['page_count'], start_page + 4)
    start_page = max(1, end_page - 4)
    context['page_links'] = [
        {'number': page_number, 'url': _mission_page_url(page_number)}
        for page_number in range(start_page, end_page + 1)
    ]
    # The list and each status chip use the same domain interpretation as the
    # close/reopen routes, including legacy assignment_state values.
    context['mission_state_label'] = mission_state_label
    return render_template('mission_reports.html', **context)


@bp.get('/reports/assignments/print-missions/print')
@req
def mission_print_all():
    """Render every filtered mission row in a dedicated print-friendly report.

    The normal mission center intentionally paginates at 50 rows. Printing from
    that page used to omit matching rows on later pages. This endpoint reuses the
    exact read-only filter/scope service with pagination disabled so print output
    and XLSX export cover the same authorized filtered result set.
    """
    if not can('view_reports'):
        abort(403)

    from ..services.mission_query import build_mission_report_context

    context = build_mission_report_context(
        roles=roles(),
        allowed_bids=readable_branch_ids(),
        args=request.args,
        paginate=False,
        include_creator=True,
        include_total=True,
    )
    context['mission_state_label'] = mission_state_label
    context['report_generated_at'] = datetime.now()

    def _selected_name(items, selected_id):
        return next((item.name for item in items if str(item.id) == str(selected_id)), '')

    print_filters = []
    if context.get('date_from'):
        print_filters.append(('من تاريخ', context['date_from']))
    if context.get('date_to'):
        print_filters.append(('إلى تاريخ', context['date_to']))
    if context.get('selected_governorate'):
        name = _selected_name(context['report_governorates'], context['selected_governorate'])
        print_filters.append(('محافظة الموظف', name or context['selected_governorate']))
    if context.get('selected_branch'):
        name = _selected_name(context['report_branches'], context['selected_branch'])
        print_filters.append(('فرع الموظف', name or context['selected_branch']))
    if context.get('selected_employee_object'):
        employee = context['selected_employee_object']
        print_filters.append(('الموظف', f'{employee.full_name} — {employee.job_code or "بدون كود"}'))
    if context.get('selected_destination_governorate'):
        name = _selected_name(context['destination_governorates'], context['selected_destination_governorate'])
        print_filters.append(('محافظة جهة المأمورية', name or context['selected_destination_governorate']))
    if context.get('selected_destination_branch'):
        name = _selected_name(context['destination_branches'], context['selected_destination_branch'])
        print_filters.append(('فرع جهة المأمورية', name or context['selected_destination_branch']))
    if context.get('mission_state'):
        print_filters.append(('حالة المأمورية', context['mission_state']))
    if context.get('duration'):
        print_filters.append(('المدة', {'open': 'مفتوح بلا تاريخ نهاية', 'dated': 'محدد بتاريخ نهاية'}.get(context['duration'], context['duration'])))
    if context.get('follow_up'):
        print_filters.append(('متابعة الانتهاء', 'ينتهي خلال 7 أيام'))
    context['print_filters'] = print_filters
    return render_template('mission_reports_print.html', **context)


@bp.post('/reports/assignments/mission-edit-request/<int:movement_id>')
@req
def mission_edit_request_create(movement_id):
    m = db.session.get(Movement, movement_id)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    rs = roles()
    # Supervisor or Application Admin acting in the selected work-governorate
    # can request a change; Manager cannot create a request he would review.
    if not (('مشرف محافظة' in rs or 'مسؤول التطبيق' in rs) and 'Manager Application Support' not in rs) or not can('manage_movements'):
        abort(403)
    if not m.employee or not branch_ok(m.employee.branch_id):
        abort(403)
    if mission_state_label(m) != 'مغلقة':
        flash('طلب التعديل بعد الإغلاق متاح للمأموريات المغلقة فقط.')
        return redirect(_mission_center_return_url())
    if not can_view_movement(m):
        abort(403)
    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 5:
        flash('يجب تسجيل سبب واضح للتعديل.')
        return redirect(_mission_center_return_url())
    # The service owns duplicate-pending detection and persistence so the route
    # does not perform a second, race-prone query against the request table.
    created_request = create_mission_edit_request(m, reason)
    if created_request is None:
        flash('يوجد بالفعل طلب تعديل قيد المراجعة لهذه المأمورية.')
        return redirect(_mission_center_return_url())
    flash('تم إرسال طلب التعديل إلى الـManager مع كامل التفاصيل والسبب.')
    return redirect(_mission_center_return_url())


@bp.get('/reports/assignments/edit-requests')
@req
def mission_edit_requests():
    rs = roles()
    if 'Manager Application Support' not in rs or not can('manage_movements'):
        abort(403)
    if not scope_governorate_id():
        flash('اختر محافظة العمل من الشريط العلوي لمراجعة طلبات تعديل المأموريات داخل نطاقها.')
        return redirect(url_for('dashboard.home'))
    # Reviewing a closed-mission request is a write operation, not a global report.
    # Limit the queue to source missions in the Manager's selected work governorate.
    scoped_branch_ids = set(bids())
    rows = list_pending_mission_edit_requests(rs, scoped_branch_ids)
    return render_template('mission_edit_requests.html', rows=rows)


@bp.get('/reports/assignments/edit-requests/<int:request_id>')
@req
def mission_edit_request_review(request_id):
    rs = roles()
    if 'Manager Application Support' not in rs or not can('manage_movements'):
        abort(403)
    r = db.session.get(MissionEditRequest, request_id)
    if not r or r.status != 'قيد المراجعة':
        abort(404)
    if not scope_governorate_id():
        flash('اختر محافظة العمل من الشريط العلوي لمراجعة الطلبات.')
        return redirect(url_for('dashboard.home'))
    if not r.movement or not r.movement.employee or not branch_ok(r.movement.employee.branch_id):
        abort(403)
    # Review choices include every active destination, like the supervisor workflow;
    # the request's source mission remains constrained to the selected work scope.
    branches, govs = mission_edit_request_review_context(r)
    return render_template('mission_edit_request_review.html', request_row=r, m=r.movement, branches=branches, destination_governorates=govs)


@bp.post('/reports/assignments/edit-requests/<int:request_id>')
@req
def mission_edit_request_save(request_id):
    rs = roles()
    if 'Manager Application Support' not in rs or not can('manage_movements'):
        abort(403)
    r = db.session.get(MissionEditRequest, request_id)
    if not r or r.status != 'قيد المراجعة':
        abort(404)
    m = r.movement
    if (
        not scope_governorate_id()
        or not m
        or not m.employee
        or not branch_ok(m.employee.branch_id)
    ):
        abort(403)
    dest_id = (request.form.get('destination_branch_id') or '').strip()
    destination = db.session.get(Branch, int(dest_id)) if dest_id.isdigit() else None
    raw_fd = request.form.get('from_date', '')
    raw_td = request.form.get('to_date', '')
    fd = _safe_mission_date(raw_fd)
    td = _safe_mission_date(raw_td)
    if (raw_fd and fd is None) or (raw_td and td is None):
        flash('تاريخ البداية أو النهاية غير صحيح. اختر تاريخًا صالحًا ثم حاول مرة أخرى.')
        return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))
    final_state = (request.form.get('final_state') or '').strip()
    notes = (request.form.get('manager_notes') or '').strip()
    # The Manager is the sole approver; the approved request may move across
    # governorates, but destinations must still be active and valid.
    allowed_destination_ids = {
        branch.id for branch in Branch.query.join(
            Governorate, Governorate.id == Branch.governorate_id
        ).filter(Branch.is_active == True, Governorate.is_active == True).all()
    }
    error = validate_and_execute_mission_edit_request(
        r, m, destination, fd, td, final_state, notes,
        allowed_destination_branch_ids=allowed_destination_ids,
    )
    if error:
        flash(error)
        # A concurrent Manager may have already resolved this request while the
        # current submission was waiting for its row lock. Avoid redirecting the
        # second reviewer back to a review page that is no longer pending.
        if r.status != 'قيد المراجعة':
            return redirect(url_for('missions.mission_edit_requests'))
        return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))
    flash(f'تم تنفيذ طلب التعديل، وحفظ المأمورية بحالة «{final_state}».')
    return redirect(url_for('missions.mission_edit_requests'))


@bp.get('/reports/assignments/export.xlsx')
@req
def mission_export_xlsx():
    if not can('view_reports'):
        abort(403)
    # Keep the spreadsheet in parity with the visible report: same authorization
    # scope and every active filter (employee, origin/destination, state and dates).
    from ..services.mission_query import build_mission_report_context

    context = build_mission_report_context(
        roles=roles(),
        allowed_bids=readable_branch_ids(),
        args=request.args,
        include_creator=True,
    )
    out = build_mission_export_xlsx(context['rows'])
    from flask import send_file
    return send_file(
        out,
        as_attachment=True,
        download_name='المأموريات.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )



@bp.get('/reports/assignments/monthly')
@req
def mission_monthly_aggregation():
    """Monthly closed-mission aggregation for Manager/Admin incentive preparation.

    This is intentionally a factual aggregation only: it does not invent or apply
    an incentive formula. Manager and application admin both receive a
    cross-governorate aggregation.
    """
    rs = roles()
    if not can('view_reports'):
        abort(403)

    from datetime import date as _date, timedelta as _timedelta
    month_raw = (request.args.get('month') or '').strip()
    today = _date.today()
    month_filter_error = False
    if not month_raw:
        month_start = today.replace(day=1)
    elif re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month_raw):
        try:
            year, month = [int(x) for x in month_raw.split('-', 1)]
            month_start = _date(year, month, 1)
        except (ValueError, TypeError):
            month_start = today.replace(day=1)
            month_filter_error = True
    else:
        # Invalid month filters must not silently fall back to the current month.
        month_start = today.replace(day=1)
        month_filter_error = True
    next_month = (month_start.replace(day=28) + _timedelta(days=4)).replace(day=1)
    month_value = month_start.strftime('%Y-%m')

    scope_branch_ids = {
        b.id for b in Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True).all()
    }

    q = (
        Movement.query.join(Employee)
        .filter(
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
            assignment_closed_filter(Movement),
            Employee.branch_id.in_(scope_branch_ids),
            Movement.from_date != None,
            Movement.to_date != None,
            Movement.from_date < next_month,
            Movement.to_date >= month_start,
        )
    ) if scope_branch_ids else Movement.query.filter(False)

    if month_filter_error:
        q = q.filter(False)
    rows = q.order_by(Employee.full_name.asc(), Movement.from_date.asc(), Movement.id.asc()).all()
    grouped = {}
    total_missions = 0
    total_days = 0
    for m in rows:
        # Count the overlap with the selected calendar month, not days outside it.
        start = max(m.from_date, month_start)
        end = min(m.to_date, next_month - _timedelta(days=1))
        days = max(0, (end - start).days + 1)
        key = (m.employee_id, m.employee.branch_id)
        item = grouped.setdefault(key, {
            'employee': m.employee,
            'branch': m.employee.branch,
            'missions': 0,
            'days': 0,
            'rows': [],
        })
        item['missions'] += 1
        item['days'] += days
        item['rows'].append(m)
        total_missions += 1
        total_days += days

    groups = sorted(
        grouped.values(),
        key=lambda x: (x['branch'].name if x['branch'] else '', x['employee'].full_name),
    )
    return render_template(
        'mission_monthly.html',
        groups=groups,
        month_value=month_value,
        month_start=month_start,
        month_end=next_month - _timedelta(days=1),
        total_missions=total_missions,
        total_days=total_days,
        scope_selected=bool(scope_branch_ids),
        month_filter_error=month_filter_error,
    )


@bp.get('/reports/assignments/print-mission/<int:movement_id>')
@req
def mission_print(movement_id):
    # Compatibility alias only: every mission print entry uses the same
    # official PDF/date-validation flow rather than a second HTML print screen.
    m = db.session.get(Movement, movement_id)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    if not can_print_mission(m):
        abort(403)
    return redirect(url_for('missions.mission_pdf', movement_id=m.id))
