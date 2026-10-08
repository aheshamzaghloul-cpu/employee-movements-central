"""Movement registration, editing and history."""

from datetime import date, datetime, timedelta

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for

from ..assignments import resolve_current_movement
from ..access import bids, branch_ok, can, can_manage_movement, can_manage_movement_employee, gids, log, me, req, roles
from ..constants import ASSIGNMENT_ALERT_DAYS
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement, MovementHistory, User
from ..validation import (
    active_leave_types,
    active_movement_types,
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
    gov = None
    global_search = bool(q)
    if gid:
        if not gid.isdigit():
            return {'results': [], 'branches': []}
        gov = db.session.get(Governorate, int(gid))
        if not gov or not gov.is_active:
            return {'results': [], 'branches': []}
    branch_rows = (
        (
            Branch.query.filter(Branch.governorate_id == gov.id, Branch.is_active == True)
            .order_by(Branch.name.asc())
            .all()
        )
        if gov
        else Branch.query.filter_by(is_active=True).order_by(Branch.name.asc()).all()
    )
    # Supervisors may pick an employee from any active branch only for
    # assignment/mission registration. Leave and permission remain scoped.
    rs = roles()
    global_assignment_picker = movement_type == 'انتداب' and ('مسؤول التطبيق' in rs or 'مشرف محافظة' in rs)
    if not global_assignment_picker and 'مسؤول التطبيق' not in rs:
        branch_rows = [b for b in branch_rows if branch_ok(b.id)]
    branch_ids = [b.id for b in branch_rows]
    if bid.isdigit():
        bid_int = int(bid)
        if bid_int not in branch_ids:
            return {
                'results': [],
                'branches': [
                    {'id': b.id, 'name': b.name, 'governorate_id': b.governorate_id}
                    for b in branch_rows
                ],
            }
        branch_ids = [bid_int]
    if not q and (not bid.isdigit()):
        return {
            'results': [],
            'branches': [
                {'id': b.id, 'name': b.name, 'governorate_id': b.governorate_id}
                for b in branch_rows
            ],
        }
    filters = [Employee.is_active == True]
    if branch_ids:
        filters.append(Employee.branch_id.in_(branch_ids))
    if q:
        like = f'%{q}%'
        filters.append(db.or_(Employee.full_name.ilike(like), Employee.job_code.ilike(like)))
    rows = Employee.query.filter(*filters).order_by(Employee.full_name.asc()).limit(20).all()
    return {
        'results': [
            {'id': e.id, 'name': e.full_name, 'code': e.job_code or '', 'branch': e.branch.name if e.branch else '', 'governorate': e.branch.governorate.name if e.branch and e.branch.governorate else ''}
            for e in rows
        ],
        'branches': [
            {'id': b.id, 'name': b.name, 'governorate_id': b.governorate_id}
            for b in branch_rows
        ],
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
    rs = roles()
    if not can_manage_movement_employee(employee, movement_type):
        abort(403)
    if not can('manage_movements') or not can_manage_movement():
        abort(403)

    destination_id = int(destination_raw) if destination_raw.isdigit() else None
    if movement_type == 'انتداب' and destination_id is not None:
        destination = db.session.get(Branch, destination_id)
        if not destination or not destination.is_active:
            abort(403)
    if movement_type == 'انتداب' and open_assignment:
        to_date = None
    validation = validate_movement_fields(
        movement_type, leave_type, destination_id, from_date, to_date, permission_date
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

    message = 'الحركة متوافقة مبدئيًا ويمكن تسجيلها.'
    suggestion = 'يمكنك المتابعة إلى تسجيل الحركة.'
    if current:
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
        } if current else None),
    }


@bp.get('/api/movements-page-filters')
@req
def movements_page_filters_api():
    """فلاتر صفحة الحركات: المحافظات ضمن النطاق ثم الفروع ثم موظفو الفرع فقط."""
    rs = roles()
    movement_type = (request.args.get('movement_type') or '').strip()
    # Only assignment/mission registration gets the supervisor's global
    # employee picker. Leave/permission employee selection remains scoped.
    global_movement_picker = 'مسؤول التطبيق' in rs or ('مشرف محافظة' in rs and movement_type == 'انتداب')
    allowed_gids = (
        {g.id for g in Governorate.query.filter_by(is_active=True).all()}
        if global_movement_picker
        else set(gids())
    )
    allowed_bids = (
        {b.id for b in Branch.query.filter_by(is_active=True).all()}
        if global_movement_picker
        else set(bids())
    )
    gid_raw = (request.args.get('governorate_id') or '').strip()
    bid_raw = (request.args.get('branch_id') or '').strip()
    gid = int(gid_raw) if gid_raw.isdigit() else None
    bid = int(bid_raw) if bid_raw.isdigit() else None
    if gid is not None and gid not in allowed_gids:
        return {'branches': [], 'employees': []}
    branch_q = Branch.query.filter(Branch.is_active == True, Branch.id.in_(allowed_bids))
    if gid is not None:
        branch_q = branch_q.filter(Branch.governorate_id == gid)
    branches = branch_q.order_by(Branch.name.asc()).all()
    branch_ids = [b.id for b in branches]
    if bid is not None and bid not in branch_ids:
        return {
            'branches': [
                {'id': b.id, 'name': b.name, 'governorate_id': b.governorate_id}
                for b in branches
            ],
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
                if current:
                    employee_movements[employee_id] = {
                        'type': current.movement_type,
                        'leave_type': current.leave_type or '',
                        'destination': current.destination.name if current.destination else '',
                        'to_date': current.to_date.isoformat() if current.to_date else '',
                    }
    return {
        'branches': [
            {'id': b.id, 'name': b.name, 'governorate_id': b.governorate_id}
            for b in branches
        ],
        'employees': [
            {
                'id': e.id,
                'name': e.full_name,
                'code': e.job_code or '',
                'branch_id': e.branch_id,
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
    return_to = (request.form.get('return_to') or '/').strip()
    if not return_to.startswith('/') or return_to.startswith('//'):
        return_to = '/'
    if not employee_id.isdigit():
        flash('اختر موظفًا أولًا.')
        return redirect('/')

    employee = db.session.get(Employee, int(employee_id))
    rs = roles()
    if not can_manage_movement_employee(employee, movement_type):
        abort(403)
    if not can('manage_movements') or not can_manage_movement():
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
    if movement_type == 'انتداب' and (destination is None or not destination.is_active):
        abort(403)

    error = validate_movement_fields(
        movement_type, leave_type, destination_id, from_date, to_date, permission_date
    )
    if error:
        flash(error)
        return redirect(return_to)

    overlap = movement_overlaps(employee.id, movement_type, from_date, to_date, permission_date)
    if overlap:
        flash(overlap)
        return redirect(return_to)

    try:
        parsed_from = parse_date(from_date) if from_date else None
        parsed_to = parse_date(to_date) if to_date else None
        parsed_permission = parse_date(permission_date) if permission_date else None
    except ValueError:
        flash('التاريخ غير صحيح.')
        return redirect(return_to)

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
    rs = roles()
    global_assignment_actor = 'مسؤول التطبيق' in rs or 'مشرف محافظة' in rs
    bs = bids()
    scoped_branches = (
        Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
        if global_assignment_actor
        else (
            Branch.query.filter(Branch.id.in_(bs), Branch.is_active == True)
            .order_by(Branch.name.asc()).all()
            if bs else []
        )
    )
    if 'مسؤول التطبيق' in rs:
        rows = (
            Movement.query
            .filter(Movement.is_active == True)
            .order_by(Movement.created_at.desc())
            .all()
        )
    elif 'مشرف محافظة' in rs:
        # المشرف يرى كل الانتدابات/المأموريات، لكن الإجازات والأذونات
        # تبقى محكومة بنطاق الفروع التشغيلي.
        rows = (
            Movement.query.join(Employee)
            .filter(
                Movement.is_active == True,
                db.or_(
                    Movement.movement_type == 'انتداب',
                    Employee.branch_id.in_(bs),
                ),
            )
            .order_by(Movement.created_at.desc())
            .all()
        )
    else:
        rows = (
            Movement.query.join(Employee)
            .filter(Employee.branch_id.in_(bs), Movement.is_active == True)
            .order_by(Movement.created_at.desc()).all()
            if bs else []
        )
    today = date.today()
    tomorrow = today + timedelta(days=ASSIGNMENT_ALERT_DAYS)

    by_employee = {}
    for m in rows:
        by_employee.setdefault(m.employee_id, []).append(m)
    current_rows = []
    for employee_moves in by_employee.values():
        current = resolve_current_movement(employee_moves, today)
        if current:
            current_rows.append(current)
    followup_rows = [
        m
        for m in rows
        if (
            m.movement_type in ('إجازة', 'انتداب')
            and m.to_date is not None
            and m.to_date <= tomorrow
            and not (m.movement_type == 'انتداب' and m.assignment_state == 'مغلق')
        )
    ]
    followup_rows.sort(key=lambda m: (m.to_date or date.max, m.id))
    destination_branches = Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
    return render_template(
        'movements.html',
        rows=rows,
        current_rows=current_rows,
        followup_rows=followup_rows,
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
        destination_governorates=(
            Governorate.query.filter(Governorate.is_active == True)
            .order_by(Governorate.name.asc()).all()
        ),
        movement_leave_types=active_leave_types(),
        movement_types=active_movement_types(),
        movement_filter_governorates=(
            Governorate.query.filter(Governorate.is_active == True)
            .order_by(Governorate.name.asc()).all()
            if ('مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles())
            else (
                Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
                .order_by(Governorate.name.asc()).all()
                if gids() else []
            )
        ),
    )


@bp.route('/movements/<int:i>/edit', methods=['GET', 'POST'])
@req
def movement_edit(i):
    m = db.session.get(Movement, i)
    if not m or not m.is_active:
        abort(403)
    # الحركات معلومات تشغيلية مباشرة ويمكن تعديلها دون انتظار اعتماد.
    if not can_manage_movement(m) or not can('manage_movements'):
        abort(403)
    if request.method == 'POST':
        f = request.form
        mt = f.get('movement_type')
        dest = (
            int(f['destination_branch_id'])
            if f.get('destination_branch_id', '').isdigit()
            else None
        )
        if mt == 'انتداب':
            destination = db.session.get(Branch, dest) if dest else None
            if destination is None or not destination.is_active:
                abort(403)
        fd = f.get('from_date')
        td = f.get('to_date')
        pd = f.get('permission_date')
        if mt == 'انتداب' and f.get('open_assignment') == '1':
            td = None
        if m.movement_type == 'انتداب' and m.assignment_state == 'مغلق' and mt == 'انتداب' and not td:
            flash('المأمورية المغلقة يجب أن تحتفظ بتاريخ نهاية. لإعادتها مفتوحة استخدم إجراء إعادة الفتح أولًا.')
            return redirect(url_for('movements.movement_edit', i=i))
        err = validate_movement_fields(mt, f.get('leave_type') or None, dest, fd, td, pd)
        if err:
            flash(err)
            return redirect(url_for('movements.movement_edit', i=i))
        overlap = movement_overlaps(m.employee_id, mt, fd, td, pd, i)
        if overlap:
            flash(overlap)
            return redirect(url_for('movements.movement_edit', i=i))
        old_status = m.status
        m.movement_type = mt
        m.leave_type = f.get('leave_type') or None
        m.destination_branch_id = dest
        m.from_date = parse_date(fd)
        m.to_date = parse_date(td)
        m.permission_date = parse_date(pd)
        if mt == 'انتداب':
            # Editing a closed assignment is allowed only to Manager/Admin.
            # The edit must not silently reopen it; reopening remains an explicit action.
            if m.assignment_state != 'مغلق':
                m.assignment_state = 'ساري'
        else:
            m.assignment_state = 'ساري'
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
        return redirect('/movements')
    return render_template(
        'movement_edit.html',
        m=m,
        emps=(
            Employee.query.filter(Employee.is_active == True)
            .order_by(Employee.full_name)
            .all()
            if ('مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles())
            else Employee.query.filter(Employee.branch_id.in_(bids()), Employee.is_active == True)
            .order_by(Employee.full_name).all()
        ),
        bs=(
            Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
            if ('مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles())
            else Branch.query.filter(Branch.id.in_(bids()), Branch.is_active == True).all()
        ),
        destination_branches=Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all(),
        destination_governorates=Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all(),
        leave_types=active_leave_types(),
        movement_types=active_movement_types(),
    )


@bp.post('/movements/<int:i>/submit')
@req
def movement_submit(i):
    m = db.session.get(Movement, i)
    if not m or not m.is_active or (not can_manage_movement(m)):
        abort(403)
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
    if m.assignment_state == 'مغلق':
        flash('الانتداب مغلق بالفعل.')
        return redirect('/movements')
    close_date = parse_date(request.form.get('close_date') or '') or date.today()
    if m.from_date and close_date < m.from_date:
        flash('تاريخ الإغلاق لا يجوز أن يسبق بداية الانتداب.')
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
    if (
        not m
        or m.movement_type != 'انتداب'
        or not m.is_active
    ):
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    if m.assignment_state != 'مغلق':
        flash('الانتداب مفتوح بالفعل.')
        return redirect('/movements')
    m.assignment_state = 'ساري'
    m.closed_by = None
    m.closed_at = None
    m.closure_reason = None
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    record_movement_history(m, m.status, m.status, 'REOPEN_ASSIGNMENT', 'إعادة فتح الانتداب للتعديل أو التمديد')
    log('REOPEN_ASSIGNMENT', 'Movement', m.id, 'إعادة فتح الانتداب للتعديل أو التمديد')
    db.session.commit()
    flash('تمت إعادة فتح الانتداب. يمكنك الآن تعديل المدة أو تمديدها.')
    return redirect(url_for('movements.movement_edit', i=m.id))


@bp.get('/movements/<int:i>/assignment-form')
@req
def assignment_form(i):
    m = db.session.get(Movement, i)
    if not m or not m.is_active or m.movement_type != 'انتداب':
        abort(403)
    if not can('manage_movements') or not can_manage_movement(m):
        abort(403)
    return render_template('assignment_form.html', m=m, today=date.today())


@bp.post('/movements/<int:i>/delete')
@req
def movement_delete(i):
    m = db.session.get(Movement, i)
    if not m:
        abort(403)
    if not can('delete_movements'):
        flash('لا تملك صلاحية حذف المأموريات والحركات.')
    elif not can_manage_movement(m) and 'مسؤول التطبيق' not in roles():
        flash('لا تملك صلاحية حذف هذه الحركة ضمن نطاقك.')
    elif not m.is_active:
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
    if not can('view_audit'):
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
