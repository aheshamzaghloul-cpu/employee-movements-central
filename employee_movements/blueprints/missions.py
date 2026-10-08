"""Assignment missions (مأموريات): edit, close, print and PDF."""

from datetime import datetime

from flask import abort, Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..access import bids, branch_ok, can, can_manage_movement, can_print_mission, can_view_movement, gids, log, me, req, roles
from ..constants import STATUSES
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement, User, MissionEditRequest
from ..validation import parse_date, movement_overlaps

bp = Blueprint('missions', __name__)


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
from ..services.mission_edit_request import (
    create_mission_edit_request,
    list_pending_mission_edit_requests,
    mission_edit_request_review_context,
    validate_and_execute_mission_edit_request,
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
    if mission_state_label(m) != 'تحت التحرير' and not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):
        flash('المأمورية مغلقة. تعديلها بعد الإغلاق متاح للـManager ومسؤول التطبيق فقط.')
        return redirect('/reports/assignments/print-missions')
    bs = bids()
    branches = (
        Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
    )
    destination_governorates = Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all()
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
    fd = parse_date(request.form.get('from_date', ''))
    td = parse_date(request.form.get('to_date', ''))
    if (
        not destination
        or not destination.is_active
    ):
        flash('اختر جهة مأمورية صحيحة من الفروع النشطة.')
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
    if not m.to_date:
        flash('لا يمكن إغلاق المأمورية قبل تسجيل «إلى تاريخ».')
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
    if mission_state_label(m) != 'مغلقة':
        flash('المأمورية بالفعل تحت التحرير.')
        return redirect('/reports/assignments/print-missions')
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
    print_to_date = parse_date(request.form.get('print_to_date', ''))
    if not print_to_date:
        flash('أدخل تاريخ «إلى» للطباعة.')
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
    data = mission_template_pdf(m, employee, branch, destination, current_app.root_path, creator)
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
    # المأموريات تعمل داخل نطاق المحافظة المختارة لمسؤول التطبيق وManager،
    # وداخل محافظات المشرف للمشرف؛ لا تُعرض بيانات تشغيلية قبل تحديد النطاق.
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
    if MissionEditRequest.query.filter_by(movement_id=m.id, status='قيد المراجعة').first():
        flash('يوجد بالفعل طلب تعديل قيد المراجعة لهذه المأمورية.')
        return redirect('/reports/assignments/print-missions')
    create_mission_edit_request(m, reason)
    flash('تم إرسال طلب التعديل إلى الـManager مع كامل التفاصيل والسبب.')
    return redirect('/reports/assignments/print-missions')


@bp.get('/reports/assignments/edit-requests')
@req
def mission_edit_requests():
    rs = roles()
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & rs) or not can('manage_movements'):
        abort(403)
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
    fd = parse_date(request.form.get('from_date', ''))
    td = parse_date(request.form.get('to_date', ''))
    final_state = (request.form.get('final_state') or '').strip()
    notes = (request.form.get('manager_notes') or '').strip()
    error = validate_and_execute_mission_edit_request(
        r, m, destination, fd, td, final_state, notes
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
    rs = roles()
    global_actor = 'مسؤول التطبيق' in rs or 'مشرف محافظة' in rs
    allowed_bids = set(bids())
    q = Movement.query.join(Employee).filter(
        Movement.is_active == True,
        Movement.movement_type == 'انتداب',
    )
    if not global_actor:
        q = q.filter(Employee.branch_id.in_(allowed_bids)) if allowed_bids else Movement.query.filter(False)
    mission_state = request.args.get('mission_state', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    if mission_state in ('تحت التحرير', 'مغلقة'):
        q = q.filter(Movement.mission_state == mission_state)
    from datetime import date as _date
    try:
        df = _date.fromisoformat(date_from) if date_from else None
    except ValueError:
        df = None
    try:
        dt = _date.fromisoformat(date_to) if date_to else None
    except ValueError:
        dt = None
    if df and dt and df > dt:
        df, dt = dt, df
    if df:
        q = q.filter(Movement.to_date >= df)
    if dt:
        q = q.filter(Movement.from_date <= dt)
    rows = q.order_by(Movement.from_date.asc(), Movement.id.asc()).all()
    from flask import send_file
    out = build_mission_export_xlsx(rows)
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
    an incentive formula. Manager scope remains the selected work governorate;
    application admin remains global.
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

    if 'مسؤول التطبيق' in rs:
        scope_branch_ids = {
            b.id for b in Branch.query.filter_by(is_active=True).all()
        }
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
