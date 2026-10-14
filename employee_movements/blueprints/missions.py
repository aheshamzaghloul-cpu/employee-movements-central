"""Assignment missions (مأموريات): edit, close, print and PDF."""

from datetime import datetime
import re

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from flask import abort, Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..access import bids, branch_ok, can, can_manage_movement, can_manage_movement_destination, can_manage_movement_employee, can_print_mission, can_view_movement, gids, log, me, req, roles
from ..constants import STATUSES
from ..extensions import db
from ..models import Branch, BranchNameAlias, Employee, TicketEmployeeCodeAlias, Governorate, Movement, User, MissionEditRequest
from ..validation import parse_date, movement_overlaps, record_movement_history, validate_movement_fields
from ..search import normalize_search_text, normalized_sql_text

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


from ..services.mission_documents import (
    mission_export_xlsx as build_mission_export_xlsx,
    mission_state_label,
    mission_template_pdf,
)
from ..services.mission_lifecycle import (
    apply_mission_edit,
    close_mission,
    reopen_mission,
)
from ..services.ticket_mission_rules import should_create_mission
from ..services.ticket_matching import (
    branch_code_match_candidates,
    branch_exact_match,
    entity_name_similarity,
    job_code_lookup_variants,
    normalize_entity_name,
    normalize_job_code,
    rank_branch_candidates,
    rank_employee_code_candidates,
)
from ..services.mission_edit_request import (
    create_mission_edit_request,
    list_pending_mission_edit_requests,
    mission_edit_request_review_context,
    validate_and_execute_mission_edit_request,
)


_TICKET_FIELD_LABELS = {
    'basic_branch_name': 'اسم الفرع الأساسي',
    'destination_branch_name': 'الفرع المحول إليه',
    'job_code': 'الكود الوظيفي',
    'destination_is_basic': 'هل الفرع المحول إليه فرعك الأساسي؟',
    'needs_mission': 'هل تحتاج مأمورية؟',
    'from_date': 'من يوم',
    'to_date': 'إلى يوم',
}


def _ticket_mission_all_active_branches():
    return (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True)
        .order_by(Governorate.name.asc(), Branch.name.asc())
        .all()
    )


def _ticket_mission_strip_branch_code_tokens(value, branches):
    codes = {normalize_job_code(branch.code or '') for branch in branches if normalize_job_code(branch.code or '')}
    text = str(value or '')
    for token_match in list(re.finditer(r"[A-Za-z0-9٠-٩۰-۹]+", text))[::-1]:
        if normalize_job_code(token_match.group(0)) in codes:
            text = text[:token_match.start()] + ' ' + text[token_match.end():]
    return re.sub(r"\s+", " ", text).strip(" -–—|·")


def _ticket_mission_basic_branch_alias_matches(value, branch):
    """Match the employee's known basic branch while guarding duplicate branch codes."""
    if not branch:
        return False
    all_active = _ticket_mission_all_active_branches()
    global_records = _ticket_mission_branch_records(all_active)
    global_code_matches = branch_code_match_candidates(value, global_records)
    branch_records = _ticket_mission_branch_records([branch])
    if global_code_matches:
        # Exact branch codes are authoritative only when globally unique and
        # attached to this branch. A duplicated code must be disambiguated by name.
        if len(global_code_matches) == 1:
            return global_code_matches[0]['id'] == branch.id
        name_value = _ticket_mission_strip_branch_code_tokens(value, all_active)
        name_records = [{
            **record,
            'code': '',
            'label': ' · '.join(part for part in (
                branch.name,
                branch.governorate.name if branch.governorate else '',
            ) if part),
        } for record in branch_records]
        return len(branch_exact_match(name_value, name_records)) == 1
    return len(branch_exact_match(value, branch_records)) == 1


def _ticket_mission_branches():
    """Return only active destinations available to the current user's assignment scope."""
    rows = _ticket_mission_all_active_branches()
    return [branch for branch in rows if can_manage_movement_destination(branch, 'انتداب')]


def _ticket_job_code_sql(column):
    """SQL-side counterpart of normalize_job_code for formatted official codes."""
    expression = normalized_sql_text(column)
    for separator in (' ', '-', '‐', '‑', '–', '—', '/', '.', '_'):
        expression = func.replace(expression, separator, '')
    return expression


def _ticket_mission_employee(job_code):
    """Resolve one active employee by official code or a confirmed alternate code.

    Missing ``200`` is supported only when all exact/prefix/alias variants point
    to the same employee. Ambiguity always requires manual resolution.
    """
    code = normalize_job_code(job_code)
    if not code:
        return None, 'لم يُقرأ الكود الوظيفي بوضوح. اكتبه كما يظهر في التيكيت.'
    if len(code) < 4:
        return None, 'الكود الوظيفي المقروء قصير جدًا لتحديد موظف بأمان. راجعه يدويًا أو أعد رفع صورة أوضح.'
    variants = job_code_lookup_variants(code)
    official_rows = (
        Employee.query.filter(
            Employee.is_active == True,
            Employee.job_code.isnot(None),
            _ticket_job_code_sql(Employee.job_code).in_(variants),
        )
        .options(joinedload(Employee.branch).joinedload(Branch.governorate))
        .all()
    )
    alias_rows = (
        TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.normalized_alias.in_(variants))
        .join(Employee, Employee.id == TicketEmployeeCodeAlias.employee_id)
        .filter(Employee.is_active == True)
        .options(joinedload(TicketEmployeeCodeAlias.employee).joinedload(Employee.branch).joinedload(Branch.governorate))
        .all()
    )
    candidates_by_id = {employee.id: employee for employee in official_rows}
    for alias in alias_rows:
        candidates_by_id[alias.employee.id] = alias.employee
    if not candidates_by_id:
        return None, 'لم يُعثر على موظف نشط بهذا الكود أو بصيغة بديلة مؤكدة. راجع الكود أو اختر موظفًا من الاقتراحات.'
    if len(candidates_by_id) > 1:
        return None, 'الكود أو إحدى صِيَغه المحتملة يطابق أكثر من موظف. لم نختَر أحدًا تلقائيًا؛ اختر الموظف الصحيح من المرشحين.'
    employee = next(iter(candidates_by_id.values()))
    if not can_manage_movement_employee(employee, 'انتداب'):
        return None, 'الموظف خارج نطاق الصلاحية المتاح لك لتسجيل الانتداب.'
    return employee, ''


def _ticket_mission_employee_suggestions(job_code, basic_branch_name='', limit=5):
    """Return scoped fuzzy candidates from official codes and confirmed aliases.

    Results are only displayed for human confirmation and are never auto-selected.
    """
    code = normalize_job_code(job_code)
    if len(code) < 4:
        return []
    variants = job_code_lookup_variants(code)
    lengths = set()
    for variant in variants:
        for delta in (-1, 0, 1):
            if len(variant) + delta >= 4:
                lengths.add(len(variant) + delta)
    if not lengths:
        return []

    code_length = func.length(_ticket_job_code_sql(Employee.job_code))
    employee_rows = (
        Employee.query.filter(
            Employee.is_active == True,
            Employee.job_code.isnot(None),
            code_length.in_(sorted(lengths)),
        )
        .options(joinedload(Employee.branch).joinedload(Branch.governorate))
        .order_by(Employee.id.asc())
        .limit(5000)
        .all()
    )
    alias_rows = (
        TicketEmployeeCodeAlias.query.filter(
            func.length(TicketEmployeeCodeAlias.normalized_alias).in_(sorted(lengths))
        )
        .join(Employee, Employee.id == TicketEmployeeCodeAlias.employee_id)
        .filter(Employee.is_active == True)
        .options(joinedload(TicketEmployeeCodeAlias.employee).joinedload(Employee.branch).joinedload(Branch.governorate))
        .all()
    )
    by_id = {employee.id: employee for employee in employee_rows}
    aliases_by_employee = {}
    for alias in alias_rows:
        by_id[alias.employee.id] = alias.employee
        aliases_by_employee.setdefault(alias.employee.id, []).append(alias.alias_text)

    ranked = rank_employee_code_candidates(
        code, by_id.values(), basic_branch_name, limit=40,
        aliases_by_employee=aliases_by_employee,
    )
    suggestions = []
    for match in ranked:
        employee = match['employee']
        if not can_manage_movement_employee(employee, 'انتداب'):
            continue
        suggestions.append(match)
        if len(suggestions) >= limit:
            break
    return suggestions


def _ticket_mission_save_job_code_alias(raw_code, employee, creator_id):
    """Persist a corrected OCR code only after explicit opt-in and unique checks."""
    alias_text = str(raw_code or '').strip()[:100]
    normalized_alias = normalize_job_code(alias_text)
    official_code = normalize_job_code(employee.job_code or '')
    if not normalized_alias or len(normalized_alias) < 4 or not official_code:
        return False, 'لم تُحفظ صيغة الكود البديلة لأنها قصيرة أو غير واضحة.'
    if normalized_alias == official_code or normalized_alias in job_code_lookup_variants(official_code):
        return False, ''  # Prefix-200 variants are resolved natively and need no alias.

    variants = job_code_lookup_variants(normalized_alias)
    official_matches = Employee.query.filter(Employee.job_code.isnot(None)).all()
    conflicting_official = [
        row for row in official_matches
        if row.id != employee.id and normalize_job_code(row.job_code) in variants
    ]
    if conflicting_official:
        return False, 'لم تُحفظ صيغة الكود البديلة لأنها قد تطابق كودًا رسميًا لموظف آخر.'

    alias_matches = TicketEmployeeCodeAlias.query.filter(
        TicketEmployeeCodeAlias.normalized_alias.in_(variants)
    ).all()
    for existing in alias_matches:
        if existing.employee_id != employee.id:
            return False, 'لم تُحفظ صيغة الكود البديلة لأنها مرتبطة بموظف آخر أو قد تسبب التباسًا.'
        return False, 'صيغة الكود أو أحد أشكالها معروفة مسبقًا لهذا الموظف.'

    alias = TicketEmployeeCodeAlias(
        employee_id=employee.id,
        alias_text=alias_text,
        normalized_alias=normalized_alias,
        created_by=creator_id,
    )
    try:
        # Savepoint protects the already-validated mission transaction from a
        # concurrent request trying to register the same global alias.
        with db.session.begin_nested():
            db.session.add(alias)
            db.session.flush()
    except IntegrityError:
        return False, 'لم تُحفظ صيغة الكود البديلة لأنها أُضيفت بالتزامن أو أصبحت متعارضة.'
    log('ADD', 'TicketEmployeeCodeAlias', alias.id, 'حفظ صيغة كود بديلة بعد تأكيد مستخدم مخوّل')
    return True, 'تم حفظ صيغة الكود التي صححتها كبديل مؤكد لهذا الموظف.'


def _ticket_mission_branch_records(branches):
    """Provide branch names and confirmed aliases for current-scope matching."""
    if not branches:
        return []
    branch_ids = [branch.id for branch in branches]
    aliases = BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(branch_ids)).all()
    by_branch = {}
    for alias in aliases:
        by_branch.setdefault(alias.branch_id, []).append(alias.alias_text)
    records = []
    for branch in branches:
        governorate_name = branch.governorate.name if branch.governorate else ''
        records.append({
            'id': branch.id,
            'name': branch.name,
            'code': branch.code or '',
            'label': ' · '.join(part for part in (branch.code or '', branch.name, governorate_name) if part),
            'aliases': by_branch.get(branch.id, []),
            'branch': branch,
        })
    return records


def _ticket_mission_branch_choices(value, branches):
    """Auto-select only a unique official name, confirmed alias or globally unique branch code."""
    records = _ticket_mission_branch_records(branches)
    if not value:
        return '', [], ''

    code_matches = branch_code_match_candidates(value, records)
    if code_matches:
        # A branch code is only an automatic identifier when it is unique across
        # all active branches, not merely unique inside the current user's scope.
        all_active_branches = _ticket_mission_all_active_branches()
        global_code_matches = branch_code_match_candidates(
            value, _ticket_mission_branch_records(all_active_branches),
        )
        if len(global_code_matches) == 1 and global_code_matches[0]['id'] == code_matches[0]['id']:
            return code_matches[0]['id'], [], ''
        # If code is duplicated, strip code tokens and match only the branch name
        # and governorate. This avoids a duplicate code embedded in ``label`` from
        # turning a possibly ambiguous code into an accidental exact match.
        name_query = _ticket_mission_strip_branch_code_tokens(value, all_active_branches)
        name_records = [
            {
                **record,
                'code': '',
                'label': ' · '.join(part for part in (
                    record['branch'].name,
                    record['branch'].governorate.name if record['branch'].governorate else '',
                ) if part),
            }
            for record in records
        ]
        name_exact = branch_exact_match(name_query, name_records)
        if len(name_exact) == 1:
            return name_exact[0]['id'], [], ''
        suggestions = rank_branch_candidates(name_query, name_records, limit=5)
        return '', suggestions, 'كود الفرع غير فريد بين الفروع النشطة. اختر الوجهة يدويًا بعد مراجعة الاسم والمحافظة.'

    exact = branch_exact_match(value, records)
    if len(exact) == 1:
        return exact[0]['id'], [], ''
    suggestions = rank_branch_candidates(value, records, limit=5)
    if len(exact) > 1:
        return '', suggestions or exact[:5], 'اسم الفرع يطابق أكثر من فرع. اختر الوجهة يدويًا من الاقتراحات.'
    if suggestions:
        return '', suggestions, 'لم نجد تطابقًا حرفيًا مؤكدًا لاسم الوجهة؛ اختر الفرع الصحيح من الاقتراحات أو القائمة.'
    return '', [], 'لم يطابق اسم الوجهة سجلًا واضحًا. اختر الفرع الصحيح يدويًا من القائمة.'


def _ticket_mission_save_branch_alias(raw_name, branch, creator_id):
    """Save a corrected spelling only after explicit opt-in and successful validation."""
    alias_text = str(raw_name or '').strip()[:200]
    branch_code = normalize_job_code(branch.code or '')
    if branch_code and branch_code.isalnum():
        # If the OCR phrase contains the exact branch code, store the remaining
        # branch wording as the alias rather than baking the code into the name.
        for token_match in re.finditer(r"[A-Za-z0-9٠-٩۰-۹]+", alias_text):
            if normalize_job_code(token_match.group(0)) == branch_code:
                alias_text = (alias_text[:token_match.start()] + ' ' + alias_text[token_match.end():]).strip(" -–—|·")
                break
    normalized_alias = normalize_entity_name(alias_text)
    official = normalize_entity_name(branch.name)
    if not normalized_alias or normalized_alias == official:
        return False, ''

    existing = BranchNameAlias.query.filter_by(normalized_alias=normalized_alias).first()
    if existing:
        if existing.branch_id == branch.id:
            return False, 'صيغة اسم الفرع محفوظة مسبقًا ضمن الأسماء البديلة.'
        return False, 'لم تُحفظ الصيغة البديلة لأنها مرتبطة باسم بديل آخر؛ تجنبنا إنشاء تطابق متعارض.'

    # Do not learn a spelling if it also looks like another active branch/alias.
    all_branches = _ticket_mission_all_active_branches()
    all_records = _ticket_mission_branch_records(all_branches)
    exact = branch_exact_match(alias_text, all_records)
    if any(item['id'] != branch.id for item in exact):
        return False, 'لم تُحفظ الصيغة البديلة لأنها قد تشير إلى فرع آخر.'
    db.session.add(BranchNameAlias(
        branch_id=branch.id,
        alias_text=alias_text,
        normalized_alias=normalized_alias,
        created_by=creator_id,
    ))
    db.session.flush()
    return True, 'تم حفظ صيغة اسم الفرع كاسم بديل لتسهيل التعرف عليها لاحقًا.'


def _ticket_mission_context(*, fields=None, scan_complete=False, error='', warning='', selected_destination_id='', employee_match=None, employee_suggestions=None, branch_suggestions=None, alias_notice=''):
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
        field_labels=_TICKET_FIELD_LABELS,
    )


def _require_ticket_mission_access():
    if not can('manage_movements') or not can_manage_movement():
        abort(403)


@bp.get('/missions/from-screenshot')
@req
def mission_from_screenshot():
    """Screen for locally reading only the seven approved ServiceDesk ticket fields."""
    _require_ticket_mission_access()
    return _ticket_mission_context()


@bp.post('/missions/from-screenshot/scan')
@req
def mission_from_screenshot_scan():
    """Read screenshot locally in memory; never persist the uploaded file or full OCR transcript."""
    _require_ticket_mission_access()
    upload = request.files.get('screenshot')
    if not upload or not upload.filename:
        return _ticket_mission_context(error='اختر صورة التيكيت أولًا.')
    try:
        from io import BytesIO
        import warnings
        from PIL import Image, UnidentifiedImageError
        from ..services.ticket_screenshot_ocr import MAX_IMAGE_PIXELS, SUPPORTED_FORMATS, extract_ticket_fields

        image_bytes = upload.stream.read(2 * 1024 * 1024 + 1)
        if not image_bytes:
            return _ticket_mission_context(error='الملف فارغ. اختر صورة تيكيت صالحة.')
        if len(image_bytes) > 2 * 1024 * 1024:
            return _ticket_mission_context(error='حجم الصورة أكبر من 2 ميجابايت. قصّ الصورة حول النموذج ثم أعد المحاولة.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            try:
                probe = Image.open(BytesIO(image_bytes))
                image_format = (probe.format or '').upper()
                if image_format not in SUPPORTED_FORMATS:
                    return _ticket_mission_context(error='الصيغ المدعومة هي PNG وJPG وWEBP فقط.')
                if probe.width * probe.height > MAX_IMAGE_PIXELS:
                    return _ticket_mission_context(error='أبعاد الصورة أكبر من الحد المسموح.')
                probe.verify()
                with Image.open(BytesIO(image_bytes)) as image:
                    fields = extract_ticket_fields(image)
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                return _ticket_mission_context(error='تعذر فتح الصورة. تأكد أنها لقطة شاشة سليمة بصيغة PNG أو JPG أو WEBP.')
    except RuntimeError as exc:
        return _ticket_mission_context(error=str(exc))
    except ValueError as exc:
        return _ticket_mission_context(error=str(exc))
    except ImportError:
        return _ticket_mission_context(error='قارئ الصور المحلي غير مهيأ على الخادم. يلزم تثبيت مكونات OCR المحلية قبل استخدام هذه الميزة.')

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
    if fields.get('job_code'):
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
    warning_parts = [branch_warning, code_normalization_notice]
    missing = [label for key, label in _TICKET_FIELD_LABELS.items() if not fields.get(key)]
    if employee_error:
        warning_parts.append(employee_error)
    if employee_suggestions:
        warning_parts.append('ظهرت أسماء موظفين محتملة بسبب تقارب الكود؛ اختر المرشح الصحيح يدويًا. لن نعتمد كودًا متقاربًا تلقائيًا.')
    if missing:
        warning_parts.append('راجع الحقول التي لم تُقرأ بوضوح: ' + '، '.join(missing) + '.')
    warning = ' '.join(part for part in warning_parts if part)
    return _ticket_mission_context(
        fields=fields,
        scan_complete=True,
        warning=warning,
        selected_destination_id=selected_destination_id,
        employee_match=employee_match,
        employee_suggestions=employee_suggestions,
        branch_suggestions=branch_suggestions,
    )


@bp.post('/missions/from-screenshot/create')
@req
def mission_from_screenshot_create():
    """Create a mission only when the destination is non-basic and a mission is requested."""
    _require_ticket_mission_access()
    form = request.form
    fields = {key: (form.get(key) or '').strip() for key in _TICKET_FIELD_LABELS}
    source_job_code = (form.get('source_job_code') or fields.get('job_code') or '').strip()[:100]
    fields['source_job_code'] = source_job_code
    destination_id_raw = (form.get('destination_branch_id') or '').strip()
    employee_match = None
    destination_id = int(destination_id_raw) if destination_id_raw.isdigit() else None

    def reject(message):
        matched, match_error = _ticket_mission_employee(fields.get('job_code')) if fields.get('job_code') else (None, '')
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
            scan_complete=True,
            error=message or match_error,
            selected_destination_id=destination_id or '',
            employee_match=matched,
            employee_suggestions=employee_suggestions,
            branch_suggestions=branch_suggestions,
        )

    if not should_create_mission(fields.get('destination_is_basic'), fields.get('needs_mission')):
        if fields.get('needs_mission') != 'yes':
            return reject('لم تُنشأ مأمورية: يجب أن تكون إجابة «هل تحتاج مأمورية؟» هي «نعم». لم يتم تسجيل أي حركة.')
        return reject('لم تُنشأ مأمورية: يجب أن تكون إجابة «هل الفرع المحول إليه فرعك الأساسي؟» هي «لا، ليس فرعي الأساسي». لم يتم تسجيل أي حركة.')
    if not fields.get('basic_branch_name'):
        return reject('اسم الفرع الأساسي مطلوب. راجع قراءته من الصورة.')
    if not fields.get('job_code'):
        return reject('الكود الوظيفي مطلوب لتحديد الموظف الصحيح.')
    employee, employee_error = _ticket_mission_employee(fields['job_code'])
    if employee_error or not employee:
        return reject(employee_error or 'تعذر تحديد الموظف.')
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
    if form.get('remember_job_code_alias') == 'yes' and source_job_code:
        _, job_code_alias_notice = _ticket_mission_save_job_code_alias(
            source_job_code, employee, me().id,
        )
        if job_code_alias_notice:
            alias_notices.append(job_code_alias_notice)
    db.session.commit()
    flash(f'تم تسجيل المأمورية للموظف «{employee.full_name}» إلى فرع «{destination.name}» بنجاح.')
    for alias_notice in alias_notices:
        flash(alias_notice, 'info')
    return redirect('/reports/assignments/print-missions')
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
    if mission_state_label(m) != 'تحت التحرير' and not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):
        flash('المأمورية مغلقة. تعديلها بعد الإغلاق متاح للـManager ومسؤول التطبيق فقط.')
        return redirect('/reports/assignments/print-missions')
    bs = bids()
    branches = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).order_by(Branch.name.asc()).all()
    )
    destination_governorates = Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all()
    # Manager work scope is enforced in both the form and POST handler; only
    # the application administrator retains cross-governorate destination access.
    if 'Manager Application Support' in roles() and 'مسؤول التطبيق' not in roles():
        allowed_branch_ids = set(bids())
        branches = [branch for branch in branches if branch.id in allowed_branch_ids]
        allowed_governorate_ids = {branch.governorate_id for branch in branches}
        destination_governorates = [gov for gov in destination_governorates if gov.id in allowed_governorate_ids]
    return render_template('mission_edit.html', m=m, branches=branches, destination_governorates=destination_governorates)


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
    if mission_state_label(m) != 'تحت التحرير' and not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):
        flash('لا يمكن تعديل المأمورية المغلقة إلا من صلاحيات الـManager ومسؤول التطبيق.')
        return redirect('/reports/assignments/print-missions')
    dest_id = request.form.get('destination_branch_id', '').strip()
    destination = db.session.get(Branch, int(dest_id)) if dest_id.isdigit() else None
    raw_fd = request.form.get('from_date', '')
    raw_td = request.form.get('to_date', '')
    fd = _safe_mission_date(raw_fd)
    td = _safe_mission_date(raw_td)
    if (raw_fd and fd is None) or (raw_td and td is None):
        flash('تاريخ البداية أو النهاية غير صحيح. اختر تاريخًا صالحًا ثم حاول مرة أخرى.')
        return redirect(url_for('missions.mission_edit', movement_id=movement_id))
    if (
        not destination
        or not destination.is_active
        or not destination.governorate
        or not destination.governorate.is_active
        or not can_manage_movement_destination(destination, 'انتداب')
        or (
            'Manager Application Support' in roles()
            and 'مسؤول التطبيق' not in roles()
            and destination.id not in set(bids())
        )
    ):
        flash('اختر جهة مأمورية صحيحة من الفروع النشطة والمسموح بها.')
        return redirect(url_for('missions.mission_edit', movement_id=movement_id))
    if not fd:
        flash('يجب إدخال تاريخ بداية صحيح.')
        return redirect(url_for('missions.mission_edit', movement_id=movement_id))
    # الانتداب المفتوح يظل بدون تاريخ نهاية في السجل. تاريخ (إلى) يمكن إدخاله
    # لاحقًا عند الإغلاق، أو إدخاله مؤقتًا لغرض طباعة المأمورية فقط.
    if td and td < fd:
        flash('تاريخ النهاية لا يجوز أن يسبق بداية الانتداب.')
        return redirect(url_for('missions.mission_edit', movement_id=movement_id))
    if mission_state_label(m) == 'مغلقة' and not td:
        flash('المأمورية المغلقة يجب أن تحتفظ بتاريخ نهاية. استخدم إعادة الفتح أولًا إذا أردت جعلها مفتوحة.')
        return redirect(url_for('missions.mission_edit', movement_id=movement_id))
    overlap_end = td if td else None
    overlap = movement_overlaps(m.employee_id, 'انتداب', fd, overlap_end, None, m.id)
    if overlap:
        flash(overlap)
        return redirect(url_for('missions.mission_edit', movement_id=movement_id))
    # Authorization and input validation stay in the HTTP layer; the state change
    # and audit trail live in the mission lifecycle service.
    apply_mission_edit(m, destination, fd, td)
    flash('تم تعديل بيانات المأمورية بنجاح.')
    return redirect('/reports/assignments/print-missions')


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
    if mission_state_label(m) == 'مغلقة':
        flash('المأمورية مغلقة بالفعل.')
        return redirect('/reports/assignments/print-missions')
    if not m.from_date or not m.to_date:
        flash('لا يمكن إغلاق المأمورية قبل تسجيل تاريخي البداية والنهاية.')
        return redirect(url_for('missions.mission_edit', movement_id=m.id))
    if m.to_date < m.from_date:
        flash('تاريخ نهاية المأمورية لا يجوز أن يسبق تاريخ بدايتها.')
        return redirect(url_for('missions.mission_edit', movement_id=m.id))
    overlap = movement_overlaps(
        m.employee_id, 'انتداب', m.from_date, m.to_date, None, m.id,
    )
    if overlap:
        flash(overlap)
        return redirect(url_for('missions.mission_edit', movement_id=m.id))
    close_mission(m)
    flash('تم إغلاق المأمورية.')
    return redirect('/reports/assignments/print-missions')


@bp.post('/reports/assignments/mission-reopen/<int:movement_id>')
@req
def mission_reopen(movement_id):
    m = db.session.get(Movement, movement_id)
    if (
        not m
        or not m.is_active
        or m.movement_type != 'انتداب'
    ):
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    # Reopening a closed mission is a privileged lifecycle transition. Keep
    # the same role boundary as the movement-level reopen endpoint; a direct
    # POST must not let a governorate supervisor bypass it.
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):
        abort(403)
    if mission_state_label(m) != 'مغلقة':
        flash('المأمورية بالفعل تحت التحرير.')
        return redirect('/reports/assignments/print-missions')
    if not m.from_date:
        flash('لا يمكن إعادة فتح مأمورية دون تاريخ بداية صحيح.')
        return redirect(url_for('missions.mission_edit', movement_id=m.id))
    overlap = movement_overlaps(
        m.employee_id, 'انتداب', m.from_date, None, None, m.id,
    )
    if overlap:
        flash(overlap)
        return redirect(url_for('missions.mission_edit', movement_id=m.id))
    reopen_mission(m)
    flash('تمت إعادة فتح المأمورية وعادت إلى «تحت التحرير».')
    return redirect(url_for('missions.mission_edit', movement_id=m.id))


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
        flash('المأمورية مغلقة ولا يوجد لها تاريخ «إلى». أعد فتحها أولًا.')
        return redirect('/reports/assignments/print-missions')
    return render_template('mission_print_date.html', m=m)


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
        flash('المأمورية مغلقة ولا يوجد لها تاريخ «إلى». أعد فتحها أولًا.')
        return redirect('/reports/assignments/print-missions')
    raw_print_to_date = request.form.get('print_to_date', '')
    print_to_date = _safe_mission_date(raw_print_to_date)
    if not print_to_date:
        flash('أدخل تاريخ «إلى» صحيحًا للطباعة باستخدام التقويم.')
        return redirect(url_for('missions.mission_print_date', movement_id=m.id))
    if m.from_date and print_to_date < m.from_date:
        flash('تاريخ «إلى» لا يجوز أن يسبق تاريخ «من».')
        return redirect(url_for('missions.mission_print_date', movement_id=m.id))
    employee = db.session.get(Employee, m.employee_id)
    branch = db.session.get(Branch, employee.branch_id) if employee else None
    destination = m.destination
    creator = db.session.get(User, m.created_by) if m.created_by else None
    data = mission_template_pdf(
        m,
        employee,
        branch,
        destination,
        current_app.root_path,
        creator,
        print_to_date=print_to_date,
        closer=m.closed_by_user,
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
            return redirect(url_for('missions.mission_print_date', movement_id=m.id))
        flash('تاريخ «إلى» غير مسجل في مأمورية مغلقة. أعد فتحها أولًا ثم أدخل التاريخ قبل الطباعة.')
        return redirect('/reports/assignments/print-missions')
    employee = db.session.get(Employee, m.employee_id)
    branch = db.session.get(Branch, employee.branch_id) if employee else None
    destination = m.destination
    creator = db.session.get(User, m.created_by) if m.created_by else None
    data = mission_template_pdf(
        m, employee, branch, destination, current_app.root_path, creator,
        closer=m.closed_by_user,
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
        allowed_bids=bids(),
        args=request.args,
    )
    return render_template('mission_reports.html', **context)


@bp.post('/reports/assignments/mission-edit-request/<int:movement_id>')
@req
def mission_edit_request_create(movement_id):
    m = db.session.get(Movement, movement_id)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    rs = roles()
    if 'مشرف محافظة' not in rs or not can('manage_movements'):
        abort(403)
    if mission_state_label(m) != 'مغلقة':
        flash('طلب التعديل بعد الإغلاق متاح للمأموريات المغلقة فقط.')
        return redirect('/reports/assignments/print-missions')
    if not can_view_movement(m):
        abort(403)
    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 5:
        flash('يجب تسجيل سبب واضح للتعديل.')
        return redirect('/reports/assignments/print-missions')
    # The service owns duplicate-pending detection and persistence so the route
    # does not perform a second, race-prone query against the request table.
    created_request = create_mission_edit_request(m, reason)
    if created_request is None:
        flash('يوجد بالفعل طلب تعديل قيد المراجعة لهذه المأمورية.')
        return redirect('/reports/assignments/print-missions')
    flash('تم إرسال طلب التعديل إلى الـManager مع كامل التفاصيل والسبب.')
    return redirect('/reports/assignments/print-missions')


@bp.get('/reports/assignments/edit-requests')
@req
def mission_edit_requests():
    rs = roles()
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & rs) or not can('manage_movements'):
        abort(403)
    if 'مسؤول التطبيق' in rs:
        all_branch_ids = {
            b.id for b in Branch.query.join(
                Governorate, Governorate.id == Branch.governorate_id
            ).filter(Branch.is_active == True, Governorate.is_active == True).all()
        }
        rows = list_pending_mission_edit_requests({'مسؤول التطبيق'}, all_branch_ids)
    else:
        # Manager sees only the selected operational governorate(s), matching
        # the scope used by the rest of the operational pages.
        rows = list_pending_mission_edit_requests(rs, bids())
    return render_template('mission_edit_requests.html', rows=rows)


@bp.get('/reports/assignments/edit-requests/<int:request_id>')
@req
def mission_edit_request_review(request_id):
    rs = roles()
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & rs) or not can('manage_movements'):
        abort(403)
    r = db.session.get(MissionEditRequest, request_id)
    if not r or r.status != 'قيد المراجعة':
        abort(404)
    if 'مسؤول التطبيق' not in rs and not branch_ok(r.movement.employee.branch_id):
        abort(403)
    branches, govs = mission_edit_request_review_context(r)
    if 'مسؤول التطبيق' not in rs:
        # Do not expose destination branch choices from other governorates in
        # the review page. The POST route still performs its own validation.
        allowed_ids = set(bids())
        branches = [branch for branch in branches if branch.id in allowed_ids]
        allowed_gov_ids = {branch.governorate_id for branch in branches}
        govs = [gov for gov in govs if gov.id in allowed_gov_ids]
    return render_template('mission_edit_request_review.html', request_row=r, m=r.movement, branches=branches, destination_governorates=govs)


@bp.post('/reports/assignments/edit-requests/<int:request_id>')
@req
def mission_edit_request_save(request_id):
    rs = roles()
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & rs) or not can('manage_movements'):
        abort(403)
    r = db.session.get(MissionEditRequest, request_id)
    if not r or r.status != 'قيد المراجعة':
        abort(404)
    m = r.movement
    if 'مسؤول التطبيق' not in rs and not branch_ok(m.employee.branch_id):
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
    # Enforce destination scope on the server, not just through filtered form
    # choices. Admin is cross-governorate; Manager is restricted to current scope.
    allowed_destination_ids = None if 'مسؤول التطبيق' in rs else set(bids())
    error = validate_and_execute_mission_edit_request(
        r, m, destination, fd, td, final_state, notes,
        allowed_destination_branch_ids=allowed_destination_ids,
    )
    if error:
        flash(error)
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
        allowed_bids=bids(),
        args=request.args,
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
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & rs) or not can('view_reports'):
        abort(403)

    from datetime import date as _date, timedelta as _timedelta
    month_raw = (request.args.get('month') or '').strip()
    today = _date.today()
    if len(month_raw) == 7:
        try:
            year, month = [int(x) for x in month_raw.split('-', 1)]
            month_start = _date(year, month, 1)
        except (ValueError, TypeError):
            month_start = today.replace(day=1)
    else:
        month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + _timedelta(days=4)).replace(day=1)
    month_value = month_start.strftime('%Y-%m')

    if {'مسؤول التطبيق', 'Manager Application Support'} & rs:
        scope_branch_ids = {b.id for b in Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).all()}
    else:
        scope_branch_ids = set(bids())

    q = (
        Movement.query.join(Employee)
        .filter(
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
            Movement.mission_state == 'مغلقة',
            Employee.branch_id.in_(scope_branch_ids),
            Movement.from_date != None,
            Movement.to_date != None,
            Movement.from_date < next_month,
            Movement.to_date >= month_start,
        )
    ) if scope_branch_ids else Movement.query.filter(False)

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
    )


@bp.get('/reports/assignments/print-mission/<int:movement_id>')
@req
def mission_print(movement_id):
    # الصفحة المرئية تعرض النموذج مع زر PDF المطابق للعينة الأصلية.
    m = db.session.get(Movement, movement_id)
    if not m or not m.is_active:
        abort(404)
    if not can_print_mission(m):
        abort(403)
    employee = db.session.get(Employee, m.employee_id)
    branch = db.session.get(Branch, employee.branch_id) if employee else None
    return render_template(
        'mission_print.html',
        movement=m,
        employee=employee,
        branch=branch,
        destination=m.destination,
        mission_state=mission_state_label(m),
        printed_at=datetime.now(),
    )
