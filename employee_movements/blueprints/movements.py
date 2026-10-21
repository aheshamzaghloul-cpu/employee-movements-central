"""Movement registration, editing and history."""

import math
from datetime import date, datetime, timedelta

from flask import abort, Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import aliased, joinedload

from ..assignments import resolve_current_movement
from ..access import (
    bids,
    branch_ok,
    can,
    can_manage_movement,
    can_manage_movement_destination,
    can_manage_movement_employee,
    can_view_movement,
    gids,
    log,
    me,
    movement_is_closed,
    req,
    roles,
)
from ..constants import ASSIGNMENT_ALERT_DAYS
from ..extensions import db
from ..form_state import form_values_from_request
from ..pagination import safe_page_number
from ..movement_state import assignment_open_filter
from ..navigation import safe_local_return_to
from ..models import (
    Branch,
    BranchNameAlias,
    Employee,
    EmployeeNameAlias,
    Governorate,
    GovernorateNameAlias,
    Movement,
    MovementHistory,
    TicketEmployeeCodeAlias,
    User,
)
from ..search import normalize_search_text, search_contains
from ..services.entity_matching import employee_search_filter, rank_scoped_employee_suggestions
from ..services.movement_search_payloads import (
    _branch_search_payload,
    _employee_search_aliases,
    _movement_search_text_map,
)
from ..validation import (
    active_leave_types,
    active_movement_types,
    lock_employee_for_movement,
    lock_movement_for_employee,
    movement_overlaps,
    parse_date,
    record_movement_history,
    validate_movement_fields,
)

bp = Blueprint('movements', __name__)



@bp.get('/api/movement-employees')
@req
def movement_employees_api():
    """بحث موظفين عام من الصفحة الرئيسية؛ المحافظة والفرع فلاتر اختيارية."""
    gid = request.args.get('governorate_id', '').strip()
    bid = request.args.get('branch_id', '').strip()
    q = (request.args.get('q') or '').strip()
    movement_type = (request.args.get('movement_type') or '').strip()
    # Employee lookup without a movement_type is the homepage's intentional
    # global identity search. Supplying a movement type switches this endpoint
    # into a transactional picker and therefore requires write capability.
    if movement_type and (not can('manage_movements') or not can_manage_movement()):
        abort(403)
    if not movement_type and not (can('manage_employees') or can('view_reports') or can('manage_movements')):
        abort(403)
    if len(q) > 120:
        return {'results': [], 'branches': []}
    if (gid and not gid.isdigit()) or (bid and not bid.isdigit()):
        return {'results': [], 'branches': []}
    gov = None
    if gid:
        if not gid.isdigit():
            return {'results': [], 'branches': []}
        gov = db.session.get(Governorate, int(gid))
        if not gov or not gov.is_active:
            return {'results': [], 'branches': []}
    branch_rows = (
        (
            Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.governorate_id == gov.id, Branch.is_active == True, Governorate.is_active == True)
            .order_by(Branch.name.asc())
            .all()
        )
        if gov
        else Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).order_by(Branch.name.asc()).all()
    )
    # Home-page employee search is intentionally global for every role and is
    # read-only: it returns identifying/search fields, not operational records.
    # Movement pickers remain separately scoped, except assignment destinations
    # and employee selection which follow the explicit cross-governorate rule.
    rs = roles()
    global_home_search = bool(q) and not movement_type
    if not global_home_search:
        # Transactional employee pickers are always limited to the selected work governorate.
        branch_rows = [b for b in branch_rows if branch_ok(b.id)]
    branch_payload = _branch_search_payload(branch_rows)
    branch_ids = [b.id for b in branch_rows]
    if bid:
        bid_int = int(bid)
        if bid_int not in branch_ids:
            return {
                'results': [],
                'branches': branch_payload,
            }
        branch_ids = [bid_int]
    if not q and not bid:
        return {
            'results': [],
            'branches': branch_payload,
        }
    # Empty authorized scope must produce no rows, never remove the branch predicate.
    filters = [Employee.is_active == True, Employee.branch_id.in_(branch_ids) if branch_ids else False]
    scoped_query = Employee.query.filter(*filters)
    if q:
        scoped_query = scoped_query.filter(employee_search_filter(q, include_branch=True))
    rows = scoped_query.order_by(Employee.full_name.asc()).limit(20).all()
    suggested_ids = set()
    suggested_reasons = {}
    if q and not rows and len(normalize_search_text(q)) >= 3:
        fallback_query = Employee.query.filter(Employee.is_active == True, Employee.branch_id.in_(branch_ids) if branch_ids else False)
        pool = fallback_query.order_by(Employee.full_name.asc()).limit(2500).all()
        ranked = rank_scoped_employee_suggestions(q, pool, limit=8)
        rows = [item['employee'] for item in ranked]
        suggested_ids = {item['employee'].id for item in ranked}
        suggested_reasons = {
            item['employee'].id: item.get('match_reasons') or []
            for item in ranked
        }
    employee_aliases = _employee_search_aliases(rows)
    return {
        'results': [
            {'id': e.id, 'name': e.full_name, 'code': e.job_code or '', 'branch': e.branch.name if e.branch else '', 'governorate': e.branch.governorate.name if e.branch and e.branch.governorate else '', 'search_aliases': employee_aliases.get(e.id, ''), 'match_kind': 'approximate' if e.id in suggested_ids else 'normal', 'match_reasons': suggested_reasons.get(e.id, [])}
            for e in rows
        ],
        'branches': branch_payload,
    }


@bp.get('/api/movement-preflight')
@req
def movement_preflight_api():
    """تحقق تشغيلي سريع قبل الحفظ؛ لا يغني عن التحقق النهائي في POST."""
    employee_raw = (request.args.get('employee_id') or '').strip()
    movement_type = (request.args.get('movement_type') or '').strip()
    leave_type = (request.args.get('leave_type') or '').strip() or None
    destination_raw = (request.args.get('destination_branch_id') or '').strip()
    from_date = (request.args.get('from_date') or '').strip() or None
    to_date = (request.args.get('to_date') or '').strip() or None
    permission_date = (request.args.get('permission_date') or '').strip() or None
    open_assignment = request.args.get('open_assignment') == '1'

    if not employee_raw.isdigit():
        return {'ready': False, 'ok': False, 'level': 'info', 'message': 'اختر الموظف أولًا.', 'suggestion': 'ابدأ باختيار الموظف.'}
    employee = db.session.get(Employee, int(employee_raw))
    if not can_manage_movement_employee(employee, movement_type):
        abort(403)
    if not can('manage_movements') or not can_manage_movement():
        abort(403)

    destination_id = int(destination_raw) if destination_raw.isdigit() else None
    if movement_type == 'انتداب' and destination_id is not None:
        destination = db.session.get(Branch, destination_id)
        if not destination or not destination.is_active or not destination.governorate or not destination.governorate.is_active:
            abort(403)
        if not can_manage_movement_destination(destination, movement_type):
            abort(403)
    if movement_type == 'انتداب' and open_assignment:
        to_date = None
    validation = validate_movement_fields(
        movement_type, leave_type, destination_id, from_date, to_date, permission_date,
        destination_scope_checked=(movement_type == 'انتداب' and destination_id is not None),
    )
    if validation:
        return {'ready': False, 'ok': False, 'level': 'error', 'message': validation, 'suggestion': 'أكمل البيانات المطلوبة أو صححها قبل المتابعة.'}

    try:
        parsed_from = parse_date(from_date) if from_date else None
        parsed_to = parse_date(to_date) if to_date else None
        parsed_permission = parse_date(permission_date) if permission_date else None
    except ValueError:
        return {'ready': False, 'ok': False, 'level': 'error', 'message': 'التاريخ غير صحيح.', 'suggestion': 'اختر التاريخ من التقويم.'}

    overlap = movement_overlaps(employee.id, movement_type, from_date, to_date, permission_date)
    if overlap:
        return {
            'ready': True,
            'ok': False,
            'level': 'error',
            'message': overlap,
            'suggestion': 'راجع الحركة الحالية أو غيّر فترة الحركة الجديدة.',
        }

    today = date.today()
    current_rows = (
        Movement.query
        .filter(Movement.employee_id == employee.id, Movement.is_active == True)
        .order_by(Movement.created_at.desc(), Movement.id.desc())
        .all()
    )
    current = resolve_current_movement(current_rows, today)
    current_readable = bool(
        current
        and (
            (can('view_reports') and can_view_movement(current))
            or (can('manage_movements') and can_manage_movement(current))
        )
    )

    message = 'الحركة متوافقة مبدئيًا ويمكن تسجيلها.'
    suggestion = 'يمكنك المتابعة إلى تسجيل الحركة.'
    if current and current_readable:
        if current.movement_type == 'إجازة':
            detail = current.leave_type or 'إجازة'
            message = f'للموظف حركة سارية اليوم: {detail}.'
            suggestion = 'تأكد أن فترة الحركة الجديدة لا تتقاطع معها؛ التحقق النهائي سيتم عند الحفظ.'
        elif current.movement_type == 'انتداب':
            dest = current.destination.name if current.destination else 'جهة أخرى'
            message = f'للموظف انتداب ساري حاليًا إلى {dest}.'
            suggestion = 'إذا كان الانتداب سيستمر، لا تسجل حركة متعارضة معه.'
        else:
            message = 'للموظف إذن مسجل اليوم.'
            suggestion = 'يمكن تسجيل حركة لفترة لا تتعارض مع الإذن.'

    if current and not current_readable:
        message = 'توجد حركة حالية للموظف؛ تفاصيلها خارج نطاق العرض المسموح، وسيُتحقق من التعارض محليًا عند الحفظ.'
        suggestion = 'يمكنك المتابعة فقط إذا كانت بيانات الحركة الجديدة مكتملة؛ لن تُعرض تفاصيل الحركة غير المسموح بها.'

    return {
        'ready': True,
        'ok': True,
        'level': 'warning' if current else 'success',
        'message': message,
        'suggestion': suggestion,
        'employee': {'id': employee.id, 'name': employee.full_name, 'code': employee.job_code or ''},
        'current_movement': ({
            'id': current.id,
            'type': current.movement_type,
            'leave_type': current.leave_type or '',
            'destination': current.destination.name if current.destination else '',
            'from_date': current.from_date.isoformat() if current.from_date else '',
            'to_date': current.to_date.isoformat() if current.to_date else '',
        } if current and current_readable else None),
    }


@bp.get('/api/movements-page-filters')
@req
def movements_page_filters_api():
    """فلاتر صفحة الحركات: المحافظات ضمن النطاق ثم الفروع ثم موظفو الفرع فقط."""
    if not (can('view_reports') or can('manage_movements')):
        abort(403)
    rs = roles()
    movement_type = (request.args.get('movement_type') or '').strip()
    # Read-only filters (no movement_type) are global. Supplying movement_type
    # switches to the transactional picker, which must remain in the work scope.
    global_read_filter = not movement_type
    allowed_gids = (
        {g.id for g in Governorate.query.filter_by(is_active=True).all()}
        if global_read_filter
        else set(gids())
    )
    # Always validate the parent governorate too: a branch can be flagged active
    # while its governorate is inactive, and must not appear in the picker.
    allowed_bids = (
        {b.id for b in Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).all()}
        if global_read_filter
        else set(bids())
    )
    gid_raw = (request.args.get('governorate_id') or '').strip()
    bid_raw = (request.args.get('branch_id') or '').strip()
    if (gid_raw and not gid_raw.isdigit()) or (bid_raw and not bid_raw.isdigit()):
        return {'branches': [], 'employees': []}
    gid = int(gid_raw) if gid_raw.isdigit() else None
    bid = int(bid_raw) if bid_raw.isdigit() else None
    if gid is not None and gid not in allowed_gids:
        return {'branches': [], 'employees': []}
    branch_q = Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True, Branch.id.in_(allowed_bids))
    if gid is not None:
        branch_q = branch_q.filter(Branch.governorate_id == gid)
    branches = branch_q.order_by(Branch.name.asc()).all()
    branch_payload = _branch_search_payload(branches)
    branch_ids = [b.id for b in branches]
    if bid is not None and bid not in branch_ids:
        return {
            'branches': branch_payload,
            'employees': [],
        }
    employees = []
    employee_movements = {}
    if bid is not None:
        employees = (
            Employee.query.filter(Employee.is_active == True, Employee.branch_id == bid)
            .order_by(Employee.full_name.asc())
            .all()
        )
        employee_ids = [e.id for e in employees]
        if employee_ids:
            today = date.today()
            movement_rows = (
                Movement.query
                .filter(Movement.employee_id.in_(employee_ids), Movement.is_active == True)
                .order_by(Movement.created_at.desc(), Movement.id.desc())
                .all()
            )
            by_employee = {}
            for m in movement_rows:
                by_employee.setdefault(m.employee_id, []).append(m)
            for employee_id, employee_moves in by_employee.items():
                current = resolve_current_movement(employee_moves, today)
                current_readable = bool(
                    current
                    and (
                        (can('view_reports') and can_view_movement(current))
                        or (can('manage_movements') and can_manage_movement(current))
                    )
                )
                if current and current_readable:
                    employee_movements[employee_id] = {
                        'type': current.movement_type,
                        'leave_type': current.leave_type or '',
                        'destination': current.destination.name if current.destination else '',
                        'to_date': current.to_date.isoformat() if current.to_date else '',
                    }
    employee_aliases = _employee_search_aliases(employees)
    return {
        'branches': branch_payload,
        'employees': [
            {
                'id': e.id,
                'name': e.full_name,
                'code': e.job_code or '',
                'branch_id': e.branch_id,
                'search_aliases': employee_aliases.get(e.id, ''),
                'current_movement': employee_movements.get(e.id),
            }
            for e in employees
        ],
    }


@bp.post('/movements/create')
@req
def movement_create():
    """Create an operational movement directly from the home employee card."""
    employee_id = request.form.get('employee_id', '').strip()
    movement_type = (request.form.get('movement_type') or '').strip()
    return_to = safe_local_return_to(request.form.get('return_to'), '/movements#movement-current')

    def reject_form(message):
        # Release the employee row lock before rendering the corrected form.
        # No user-entered PII is persisted in the signed client-side session.
        db.session.rollback()
        g._movement_form_values = form_values_from_request(request.form)
        flash(message)
        return movements()

    if not employee_id.isdigit():
        db.session.rollback()
        g._movement_form_values = form_values_from_request(request.form)
        flash('اختر موظفًا أولًا.')
        return movements()

    employee = db.session.get(Employee, int(employee_id))
    if not can_manage_movement_employee(employee, movement_type):
        abort(403)
    if not can('manage_movements') or not can_manage_movement():
        abort(403)
    # Serialize concurrent movement writes for this employee before checking
    # overlaps. Re-check permissions against the refreshed row after acquiring it.
    employee = lock_employee_for_movement(employee.id)
    if not employee or not can_manage_movement_employee(employee, movement_type):
        abort(403)

    form = request.form
    leave_type = (form.get('leave_type') or '').strip() or None
    destination = (
        db.session.get(Branch, int(form.get('destination_branch_id')))
        if (form.get('destination_branch_id') or '').isdigit()
        else None
    )
    from_date = (form.get('leave_from_date') if movement_type == 'إجازة' else form.get('assignment_from_date')) or None
    to_date = None if (movement_type == 'انتداب' and form.get('open_assignment') == '1') else ((form.get('leave_to_date') if movement_type == 'إجازة' else form.get('assignment_to_date')) or None)
    permission_date = form.get('permission_date') or None
    destination_id = destination.id if destination else None
    if movement_type == 'انتداب' and destination is None:
        return reject_form('اختر جهة مأمورية نشطة من القائمة قبل التسجيل.')
    if movement_type == 'انتداب' and (not destination.is_active or not destination.governorate or not destination.governorate.is_active):
        abort(403)
    if movement_type == 'انتداب' and not can_manage_movement_destination(destination, movement_type):
        abort(403)

    error = validate_movement_fields(
        movement_type, leave_type, destination_id, from_date, to_date, permission_date,
        destination_scope_checked=(movement_type == 'انتداب' and destination is not None),
    )
    if error:
        return reject_form(error)

    overlap = movement_overlaps(employee.id, movement_type, from_date, to_date, permission_date)
    if overlap:
        return reject_form(overlap)

    try:
        parsed_from = parse_date(from_date) if from_date else None
        parsed_to = parse_date(to_date) if to_date else None
        parsed_permission = parse_date(permission_date) if permission_date else None
    except ValueError:
        return reject_form('التاريخ غير صحيح.')

    movement = Movement(
        employee_id=employee.id,
        movement_type=movement_type,
        leave_type=leave_type,
        destination_branch_id=destination_id,
        from_date=parsed_from,
        to_date=parsed_to,
        permission_date=parsed_permission,
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
    record_movement_history(movement, None, 'مسجلة', 'ADD', 'تسجيل حركة مباشرة من واجهة التشغيل')
    log('ADD', 'Movement', movement.id, f'تسجيل {movement_type} للموظف {employee.full_name}')
    db.session.commit()
    flash(f'تم تسجيل {movement_type} للموظف «{employee.full_name}» بنجاح.')
    return redirect(return_to)


@bp.get('/movements')
@req
def movements():
    # صفحة الحركات للمتابعة والسجل فقط؛ تسجيل الحركة يتم من الرئيسية.
    if not (can('view_reports') or can('manage_movements')):
        abort(403)
    movement_form_values = getattr(g, '_movement_form_values', None)
    if not isinstance(movement_form_values, dict):
        movement_form_values = form_values_from_request(request.form) if request.method == 'POST' else {}
    bs = bids()
    # Shared read directory: users can inspect active movement records from all
    # active governorates. bs/scoped_branches remain the selected write scope and
    # are used by row-action authorization and movement creation.
    scoped_branches = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.id.in_(bs), Branch.is_active == True, Governorate.is_active == True)
        .order_by(Branch.name.asc()).all()
        if bs else []
    )
    today = date.today()
    tomorrow = today + timedelta(days=ASSIGNMENT_ALERT_DAYS)

    # The historical log is filtered and paginated in SQL. Do not hydrate every
    # movement into the web worker on each page open.
    raw_filters = {
        'q': (request.args.get('q') or '').strip()[:120],
        'governorate_id': (request.args.get('governorate_id') or '').strip(),
        'branch_id': (request.args.get('branch_id') or '').strip(),
        'employee_id': (request.args.get('employee_id') or '').strip(),
        'movement_type': (request.args.get('movement_type') or '').strip(),
    }
    allowed_types = set(active_movement_types())
    invalid_type_filter = bool(raw_filters['movement_type']) and raw_filters['movement_type'] not in allowed_types
    invalid_numeric_filter = any(
        raw_filters[key] and not raw_filters[key].isdigit()
        for key in ('governorate_id', 'branch_id', 'employee_id')
    )
    filter_error = invalid_numeric_filter or invalid_type_filter
    filter_conflict = False
    selected_gov_id = int(raw_filters['governorate_id']) if raw_filters['governorate_id'].isdigit() else None
    selected_branch_id = int(raw_filters['branch_id']) if raw_filters['branch_id'].isdigit() else None
    selected_employee_id = int(raw_filters['employee_id']) if raw_filters['employee_id'].isdigit() else None

    # Numeric IDs are not automatically valid filters. Verify that each selected
    # record still exists and is active, and that child selections belong to the
    # selected parent. Otherwise show an explicit conflict instead of an
    # indistinguishable empty result. This is read-filter validation, not scope
    # authorization; mutation endpoints still enforce their own permissions.
    if selected_gov_id is not None:
        selected_governorate = Governorate.query.filter(
            Governorate.id == selected_gov_id,
            Governorate.is_active == True,
        ).first()
        if not selected_governorate:
            filter_error = True
            filter_conflict = True

    selected_filter_branch = None
    if selected_branch_id is not None:
        selected_filter_branch = (
            Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(
                Branch.id == selected_branch_id,
                Branch.is_active == True,
                Governorate.is_active == True,
            )
            .first()
        )
        if not selected_filter_branch:
            filter_error = True
            filter_conflict = True
        elif selected_gov_id is not None and selected_filter_branch.governorate_id != selected_gov_id:
            filter_error = True
            filter_conflict = True

    selected_filter_employee = None
    if selected_employee_id is not None:
        selected_filter_employee = (
            db.session.query(Employee.id, Employee.branch_id, Branch.governorate_id)
            .join(Branch, Branch.id == Employee.branch_id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(
                Employee.id == selected_employee_id,
                Employee.is_active == True,
                Branch.is_active == True,
                Governorate.is_active == True,
            )
            .first()
        )
        if not selected_filter_employee:
            filter_error = True
            filter_conflict = True
        else:
            _selected_employee_record_id, employee_branch_id, employee_governorate_id = selected_filter_employee
            if selected_branch_id is not None and employee_branch_id != selected_branch_id:
                filter_error = True
                filter_conflict = True
            if selected_gov_id is not None and employee_governorate_id != selected_gov_id:
                filter_error = True
                filter_conflict = True

    destination_branch = aliased(Branch, name='movement_log_destination_branch')

    def movement_log_query():
        query = (
            Movement.query
            .join(Employee, Employee.id == Movement.employee_id)
            .join(Branch, Branch.id == Employee.branch_id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .outerjoin(destination_branch, destination_branch.id == Movement.destination_branch_id)
            .filter(
                Movement.is_active == True,
                Branch.is_active == True,
                Governorate.is_active == True,
            )
        )
        if filter_error:
            # Invalid filters fail closed. Never discard an invalid value and
            # accidentally broaden the result set to the full movement log.
            return query.filter(Movement.id == -1)
        if selected_gov_id is not None:
            query = query.filter(Branch.governorate_id == selected_gov_id)
        if selected_branch_id is not None:
            query = query.filter(Employee.branch_id == selected_branch_id)
        if selected_employee_id is not None:
            query = query.filter(Employee.id == selected_employee_id)
        if raw_filters['movement_type']:
            query = query.filter(Movement.movement_type == raw_filters['movement_type'])
        term = raw_filters['q']
        if term:
            matched_employee_aliases = select(EmployeeNameAlias.employee_id).where(
                search_contains(EmployeeNameAlias.alias_text, term)
            )
            matched_employee_codes = select(TicketEmployeeCodeAlias.employee_id).where(
                search_contains(TicketEmployeeCodeAlias.alias_text, term)
            )
            matched_branch_aliases = select(BranchNameAlias.branch_id).where(
                search_contains(BranchNameAlias.alias_text, term)
            )
            matched_governorate_aliases = select(GovernorateNameAlias.governorate_id).where(
                search_contains(GovernorateNameAlias.alias_text, term)
            )
            query = query.filter(or_(
                search_contains(Employee.full_name, term),
                search_contains(Employee.job_code, term),
                search_contains(Employee.employee_code, term),
                search_contains(Employee.job_title, term),
                search_contains(Branch.name, term),
                search_contains(Branch.code, term),
                search_contains(Governorate.name, term),
                search_contains(Movement.movement_type, term),
                search_contains(Movement.leave_type, term),
                search_contains(Movement.notes, term),
                search_contains(destination_branch.name, term),
                search_contains(destination_branch.code, term),
                Employee.id.in_(matched_employee_aliases),
                Employee.id.in_(matched_employee_codes),
                Branch.id.in_(matched_branch_aliases),
                Governorate.id.in_(matched_governorate_aliases),
            ))
        return query

    log_query = movement_log_query()
    movement_page_size = 100
    movement_page_raw = (request.args.get('page') or '1').strip()
    movement_page = safe_page_number(movement_page_raw)
    total_records = log_query.order_by(None).count()
    movement_page_count = max(1, math.ceil(total_records / movement_page_size))
    movement_page = min(movement_page, movement_page_count)
    rows = (
        log_query
        .options(
            joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate),
            joinedload(Movement.destination),
        )
        .order_by(Movement.created_at.desc(), Movement.id.desc())
        .limit(movement_page_size)
        .offset((movement_page - 1) * movement_page_size)
        .all()
    )

    # Resolve current status from only movements that can affect today's state,
    # using the same priority order as resolve_current_movement(): leave, dated
    # assignment, open assignment, then today's permission. ROW_NUMBER means the
    # database returns one canonical current movement per employee, rather than
    # loading each employee's entire movement history to Python.
    current_candidate = or_(
        and_(Movement.movement_type == 'إجازة', Movement.from_date <= today, Movement.to_date >= today),
        and_(Movement.movement_type == 'انتداب',
             assignment_open_filter(Movement),
             Movement.from_date <= today, or_(Movement.to_date.is_(None), Movement.to_date >= today)),
        and_(Movement.movement_type == 'إذن', Movement.permission_date == today),
    )
    current_priority = case(
        (Movement.movement_type == 'إجازة', 1),
        (and_(Movement.movement_type == 'انتداب', Movement.to_date.is_not(None)), 2),
        (Movement.movement_type == 'انتداب', 3),
        else_=4,
    )
    ranked_current = (
        db.session.query(
            Movement.id.label('movement_id'),
            func.row_number().over(
                partition_by=Movement.employee_id,
                order_by=(current_priority.asc(), Movement.created_at.desc(), Movement.id.desc()),
            ).label('current_rank'),
        )
        .join(Employee, Employee.id == Movement.employee_id)
        .join(Branch, Branch.id == Employee.branch_id)
        .join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(
            Movement.is_active == True,
            Branch.is_active == True,
            Governorate.is_active == True,
            current_candidate,
        )
        .subquery()
    )
    current_rows_query = (
        Movement.query
        .filter(Movement.id.in_(select(ranked_current.c.movement_id).where(ranked_current.c.current_rank == 1)))
        .options(
            joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate),
            joinedload(Movement.destination),
        )
    )
    current_rows_total = current_rows_query.order_by(None).count()
    current_page_size = 50
    current_page_raw = (request.args.get('current_page') or '1').strip()
    current_page = safe_page_number(current_page_raw)
    current_page_count = max(1, math.ceil(current_rows_total / current_page_size))
    current_page = min(current_page, current_page_count)
    current_rows = (
        current_rows_query
        .order_by(Movement.created_at.desc(), Movement.id.desc())
        .limit(current_page_size)
        .offset((current_page - 1) * current_page_size)
        .all()
    )

    followup_query = (
        Movement.query
        .join(Employee, Employee.id == Movement.employee_id)
        .join(Branch, Branch.id == Employee.branch_id)
        .join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(
            Movement.is_active == True,
            Branch.is_active == True,
            Governorate.is_active == True,
            Movement.movement_type.in_(('إجازة', 'انتداب')),
            Movement.to_date.is_not(None),
            Movement.to_date <= tomorrow,
            or_(Movement.movement_type != 'انتداب', assignment_open_filter(Movement)),
        )
    )
    followup_rows_total = followup_query.order_by(None).count()
    followup_page_size = 50
    followup_page_raw = (request.args.get('followup_page') or '1').strip()
    followup_page = safe_page_number(followup_page_raw)
    followup_page_count = max(1, math.ceil(followup_rows_total / followup_page_size))
    followup_page = min(followup_page, followup_page_count)
    followup_rows = (
        followup_query
        .options(
            joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate),
            joinedload(Movement.destination),
        )
        .order_by(Movement.to_date.asc(), Movement.id.asc())
        .limit(followup_page_size)
        .offset((followup_page - 1) * followup_page_size)
        .all()
    )

    # Homepage quick actions may open this page with a selected employee and movement type.
    # Query values are hints only: validate the type, active employee, write permission, and scope
    # before using them to populate the form.
    movement_return_to = safe_local_return_to(
        movement_form_values.get('return_to') or request.args.get('return_to'), '/movements#movement-current'
    )
    requested_type = str(movement_form_values.get('movement_type') or '').strip() or (request.args.get('movement_type') or '').strip()
    initial_movement_type = requested_type if requested_type in active_movement_types() else ''
    initial_employee = None
    initial_branch_id = None
    initial_governorate_id = None
    initial_employee_notice = ''
    requested_employee_id = str(movement_form_values.get('employee_id') or '').strip() or (request.args.get('employee_id') or '').strip()
    if requested_employee_id:
        if not requested_employee_id.isdigit():
            initial_employee_notice = 'تعذر تحديد الموظف المطلوب. أعد البحث عنه من الرئيسية واختر سجلًا صحيحًا.'
        elif not initial_movement_type:
            initial_employee_notice = 'تم تمرير موظف دون نوع حركة صالح. اختر نوع الحركة ثم حدد الموظف من القائمة.'
        else:
            candidate = db.session.get(Employee, int(requested_employee_id))
            if not candidate:
                initial_employee_notice = 'لم يعد الموظف المحدد موجودًا. أعد البحث عنه من الرئيسية.'
            elif not candidate.is_active or not candidate.branch or not candidate.branch.is_active or not candidate.branch.governorate or not candidate.branch.governorate.is_active:
                initial_employee_notice = 'لا يمكن التسجيل للموظف المحدد لأن حالته أو فرعه غير نشط. راجع سجل الموظف قبل المتابعة.'
            elif not can('manage_movements') or not can_manage_movement() or not can_manage_movement_employee(candidate, initial_movement_type):
                initial_employee_notice = 'لم يتم تحديد الموظف تلقائيًا لأن محافظة الموظف خارج نطاق العمل الحالي أو لأن نوع الحركة غير مسموح. اختر محافظة العمل الصحيحة أو موظفًا ضمن النطاق.'
            else:
                initial_employee = candidate
                initial_branch_id = candidate.branch_id
                initial_governorate_id = candidate.branch.governorate_id

    destination_branches = Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).order_by(Branch.name.asc()).all()
    initial_destination_governorate_id = None
    draft_destination_id = str(movement_form_values.get('destination_branch_id') or '').strip()
    if draft_destination_id.isdigit():
        draft_destination = next((branch for branch in destination_branches if branch.id == int(draft_destination_id)), None)
        if draft_destination and can_manage_movement_destination(draft_destination, 'انتداب'):
            initial_destination_governorate_id = draft_destination.governorate_id
    movement_search_text_by_id = _movement_search_text_map(rows)
    return render_template(
        'movements.html',
        rows=rows,
        movement_search_text_by_id=movement_search_text_by_id,
        current_rows=current_rows,
        current_rows_total=current_rows_total,
        current_page=current_page,
        current_page_count=current_page_count,
        current_page_size=current_page_size,
        followup_rows=followup_rows,
        followup_rows_total=followup_rows_total,
        followup_page=followup_page,
        followup_page_count=followup_page_count,
        followup_page_size=followup_page_size,
        total_records=total_records,
        movement_page=movement_page,
        movement_page_count=movement_page_count,
        movement_page_size=movement_page_size,
        movement_filters=raw_filters,
        movement_filter_error=filter_error,
        movement_filter_conflict=filter_conflict,
        today=today,
        tomorrow=tomorrow,
        bs=scoped_branches,
        destination_branches=destination_branches,
        # محافظة الموظف/من: تعرض كل المحافظات النشطة في قائمة الاختيار،
        # بينما يظل الوصول الفعلي للموظف محكومًا بـ branch_ok في الـ API والحفظ.
        movement_governorates=(
            Governorate.query.filter_by(is_active=True)
            .order_by(Governorate.name.asc()).all()
        ),
        movement_scoped_governorate_ids=sorted(gids()),
        movement_global_picker_allowed=bool(
            roles() & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'}
        ),
        destination_governorates=(
            Governorate.query.filter(Governorate.is_active == True)
            .order_by(Governorate.name.asc()).all()
        ),
        movement_leave_types=active_leave_types(),
        movement_types=active_movement_types(),
        initial_movement_type=initial_movement_type,
        initial_employee=initial_employee,
        initial_branch_id=initial_branch_id,
        initial_governorate_id=initial_governorate_id,
        initial_employee_notice=initial_employee_notice,
        movement_form_values=movement_form_values,
        initial_destination_governorate_id=initial_destination_governorate_id,
        movement_return_to=movement_return_to,
        movement_filter_governorates=(
            Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()
        ),
    )


def _render_movement_edit_form(m, form_values=None, return_to=None):
    """Render the edit form without losing input or the originating page."""
    return render_template(
        'movement_edit.html',
        m=m,
        form_values=dict(form_values or {}),
        movement_return_to=safe_local_return_to(return_to, '/movements#movement-current'),
        destination_branches=(
            Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(Branch.is_active == True, Governorate.is_active == True)
            .order_by(Governorate.name.asc(), Branch.name.asc()).all()
        ),
        destination_governorates=(
            Governorate.query.filter(Governorate.is_active == True)
            .order_by(Governorate.name.asc()).all()
        ),
        leave_types=active_leave_types(),
        movement_types=active_movement_types(),
    )


@bp.route('/movements/<int:i>/edit', methods=['GET', 'POST'])
@req
def movement_edit(i):
    return_to = safe_local_return_to(request.values.get('return_to'), '/movements#movement-current')
    m = db.session.get(Movement, i)
    if not m or not m.is_active:
        abort(403)
    # الحركات معلومات تشغيلية مباشرة ويمكن تعديلها دون انتظار اعتماد.
    if not can_manage_movement(m) or not can('manage_movements'):
        abort(403)
    # Closed missions are never edited through the generic movement editor.
    # All post-close data changes must pass through the Manager request workflow.
    if m.movement_type == 'انتداب' and movement_is_closed(m):
        flash('المأمورية مغلقة. استخدم طلب تعديل المأمورية ليعالجه الـManager.')
        return redirect('/reports/assignments/print-missions')
    if request.method == 'POST':
        locked_employee = lock_employee_for_movement(m.employee_id)
        if not locked_employee:
            abort(404)
        refreshed = lock_movement_for_employee(i, locked_employee.id)
        if not refreshed or not refreshed.is_active:
            abort(403)
        m = refreshed
        if not can_manage_movement(m) or not can('manage_movements'):
            abort(403)
        if m.movement_type == 'انتداب' and movement_is_closed(m):
            flash('المأمورية مغلقة. استخدم طلب تعديل المأمورية ليعالجه الـManager.')
            return redirect('/reports/assignments/print-missions')
        f = request.form
        mt = f.get('movement_type')
        dest = (
            int(f['destination_branch_id'])
            if f.get('destination_branch_id', '').isdigit()
            else None
        )
        if mt == 'انتداب':
            destination = db.session.get(Branch, dest) if dest else None
            if (
                destination is None
                or not destination.is_active
                or not destination.governorate
                or not destination.governorate.is_active
            ):
                abort(403)
            if not can_manage_movement_destination(destination, mt):
                abort(403)
        fd = f.get('from_date')
        td = f.get('to_date')
        pd = f.get('permission_date')
        if mt == 'انتداب' and f.get('open_assignment') == '1':
            td = None
        err = validate_movement_fields(
            mt, f.get('leave_type') or None, dest, fd, td, pd,
            destination_scope_checked=(mt == 'انتداب' and dest is not None),
        )
        if err:
            flash(err, 'warning')
            return _render_movement_edit_form(m, f.to_dict(), return_to)
        try:
            parsed_from = parse_date(fd) if fd else None
            parsed_to = parse_date(td) if td else None
            parsed_permission = parse_date(pd) if pd else None
        except ValueError:
            flash('التاريخ غير صحيح.', 'warning')
            return _render_movement_edit_form(m, f.to_dict(), return_to)
        overlap = movement_overlaps(m.employee_id, mt, fd, td, pd, i)
        if overlap:
            flash(overlap, 'warning')
            return _render_movement_edit_form(m, f.to_dict(), return_to)
        old_status = m.status
        m.movement_type = mt
        m.leave_type = f.get('leave_type') or None
        m.destination_branch_id = dest
        m.from_date = parsed_from
        m.to_date = parsed_to
        m.permission_date = parsed_permission
        if mt == 'انتداب':
            m.assignment_state = 'ساري'
        else:
            m.assignment_state = 'ساري'
            m.mission_state = 'تحت التحرير'
            m.closed_by = None
            m.closed_at = None
            m.closure_reason = None
        m.notes = None
        m.modified_by = me().id
        m.modified_at = datetime.utcnow()
        m.status = 'مسجلة'
        record_movement_history(m, old_status, 'مسجلة', 'EDIT', 'تعديل بيانات الحركة مباشرة')
        log('EDIT', 'Movement', i, 'تعديل الحركة')
        db.session.commit()
        flash('تم تعديل الحركة وحفظها مباشرة.')
        return redirect(return_to)
    # The edit template consumes only destination choices and lookup values; do
    # not load unused employee/branch lists for the old generic editor.
    return _render_movement_edit_form(m, return_to=return_to)


@bp.post('/movements/<int:i>/submit')
@req
def movement_submit(i):
    m = db.session.get(Movement, i)
    # Submission changes operational state, so both the explicit mutation
    # permission and the movement's scope must be checked on the server.
    if not m or not m.is_active:
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    # Keep the same employee -> movement lock order used by create/edit/close.
    # This prevents stale concurrent requests from writing duplicate history or
    # reopening a state transition after another request has already completed.
    employee = lock_employee_for_movement(m.employee_id)
    if not employee:
        abort(404)
    refreshed = lock_movement_for_employee(i, employee.id)
    if not refreshed or not refreshed.is_active:
        abort(403)
    m = refreshed
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    if m.movement_type == 'انتداب' and movement_is_closed(m):
        db.session.rollback()
        flash('لا يمكن تثبيت أو تغيير حالة مأمورية مغلقة مباشرة. أرسل طلب تعديل ليعالجه الـManager.')
        return redirect('/reports/assignments/print-missions')
    # The endpoint may be submitted twice by a double click or browser retry.
    # A registered row is already in the desired state; do not add duplicate
    # audit/history rows or mutate its timestamp again.
    if m.status == 'مسجلة':
        db.session.rollback()
        flash('الحركة مسجلة بالفعل؛ لم يتم إنشاء إجراء مكرر.')
        return redirect('/movements')
    old_status = m.status
    m.status = 'مسجلة'
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    record_movement_history(m, old_status, 'مسجلة', 'SUBMIT', 'تثبيت الحركة كسجل تشغيلي')
    log('SUBMIT', 'Movement', i, 'الحركة مسجلة مباشرة')
    db.session.commit()
    flash('الحركة مسجلة مباشرة.')
    return redirect('/movements')


@bp.post('/movements/<int:i>/close-assignment')
@req
def close_assignment(i):
    m = db.session.get(Movement, i)
    if (
        not m
        or m.movement_type != 'انتداب'
        or not m.is_active
    ):
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    locked_employee = lock_employee_for_movement(m.employee_id)
    if not locked_employee:
        abort(404)
    refreshed = lock_movement_for_employee(i, locked_employee.id)
    if not refreshed or not refreshed.is_active or refreshed.movement_type != 'انتداب':
        abort(403)
    m = refreshed
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    if movement_is_closed(m):
        flash('الانتداب مغلق بالفعل.')
        return redirect('/movements')
    raw_close_date = (request.form.get('close_date') or '').strip()
    try:
        close_date = parse_date(raw_close_date) if raw_close_date else date.today()
    except ValueError:
        flash('تاريخ الإغلاق غير صحيح. اختر تاريخًا صالحًا من التقويم.')
        return redirect('/movements')
    if close_date is None:
        flash('تاريخ الإغلاق غير صحيح. اختر تاريخًا صالحًا من التقويم.')
        return redirect('/movements')
    if m.from_date and close_date < m.from_date:
        flash('تاريخ الإغلاق لا يجوز أن يسبق بداية الانتداب.')
        return redirect('/movements')
    # Re-check the proposed closure date against every other active movement
    # before persisting the end date. This protects against a closure date that
    # would make the assignment overlap another registered movement.
    overlap = movement_overlaps(m.employee_id, 'انتداب', m.from_date.isoformat() if m.from_date else None, close_date.isoformat(), None, m.id)
    if overlap:
        flash(f'تعذر إغلاق الانتداب في هذا التاريخ: {overlap}')
        return redirect('/movements')
    m.assignment_state = 'مغلق'
    m.to_date = close_date
    m.closed_by = me().id
    m.closed_at = datetime.utcnow()
    m.closure_reason = (request.form.get('reason') or 'إغلاق الانتداب وعودة الموظف لفرعه الأصلي').strip()
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    record_movement_history(m, m.status, m.status, 'CLOSE_ASSIGNMENT', m.closure_reason)
    log('CLOSE_ASSIGNMENT', 'Movement', m.id, m.closure_reason)
    db.session.commit()
    flash('تم إنهاء الانتداب، وعاد الموظف لفرعه الأصلي.')
    return redirect('/movements')


@bp.post('/movements/<int:i>/reopen-assignment')
@req
def reopen_assignment(i):
    m = db.session.get(Movement, i)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    # Direct reopen would let a caller edit a closed mission without the
    # mandatory Manager review. Reopening is now selected as the final state
    # of an approved mission-edit request.
    flash('إعادة الفتح المباشر غير متاحة. استخدم طلب تعديل المأمورية ليعتمده الـManager.')
    return redirect('/reports/assignments/print-missions')


@bp.get('/movements/<int:i>/assignment-form')
@req
def assignment_form(i):
    """Compatibility URL that now delegates to the official mission PDF flow."""
    m = db.session.get(Movement, i)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(404)
    # Printing is read-only. Use the same access policy and PDF/date flow as the
    # mission center instead of rendering a second, divergent paper template.
    if not can('view_reports') or not can_view_movement(m):
        abort(403)
    return redirect(url_for('missions.mission_pdf', movement_id=m.id))


@bp.post('/movements/<int:i>/delete')
@req
def movement_delete(i):
    m = db.session.get(Movement, i)
    if not m:
        abort(403)
    if not can('delete_movements') or not can_manage_movement(m):
        abort(403)
    # Serialize against edits, closes and other delete attempts using the shared
    # employee -> movement lock order. Refresh after waiting before deciding.
    employee = lock_employee_for_movement(m.employee_id)
    if not employee:
        abort(404)
    refreshed = lock_movement_for_employee(i, employee.id)
    if not refreshed:
        abort(404)
    m = refreshed
    if not can('delete_movements') or not can_manage_movement(m):
        db.session.rollback()
        abort(403)
    if m.movement_type == 'انتداب' and movement_is_closed(m):
        db.session.rollback()
        # Deleting a closed mission is a destructive shortcut around the
        # Manager-reviewed closed-mission change workflow. It cannot be used
        # to bypass a pending/requested state transition by any role.
        flash('لا يمكن حذف مأمورية مغلقة مباشرة. يجب أن تتم أي معالجة لها عبر طلب التعديل ومراجعة الـManager.')
    elif not m.is_active:
        db.session.rollback()
        flash('الحركة محذوفة بالفعل.')
    else:
        old_status = m.status
        m.is_active = False
        m.deleted_by = me().id
        m.deleted_at = datetime.utcnow()
        record_movement_history(m, old_status, old_status, 'DELETE', 'حذف/إخفاء الحركة')
        log('DELETE', 'Movement', i, f'حذف الحركة؛ الحالة قبل الحذف: {old_status}')
        db.session.commit()
        flash('تم حذف الحركة بنجاح.')
    return redirect('/movements')


@bp.get('/movements/<int:i>/history')
@req
def movement_history(i):
    m = db.session.get(Movement, i)
    if not m:
        abort(403)
    # Audit permission alone must not reveal another scope's movement history.
    if not can('view_reports') or not can_view_movement(m):
        abort(403)
    rows = (
        MovementHistory.query.filter_by(movement_id=i)
        .order_by(MovementHistory.created_at.desc())
        .all()
    )
    users = (
        {
            u.id: u.full_name
            for u in User.query.filter(User.id.in_([x.user_id for x in rows if x.user_id])).all()
        }
        if rows
        else {}
    )
    return render_template('movement_history.html', m=m, rows=rows, history_users=users)
