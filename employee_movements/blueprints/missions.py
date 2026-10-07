"""Assignment missions (مأموريات): edit, close, print and PDF."""

import io
import os
from datetime import datetime

import fitz
from flask import abort, Blueprint, current_app, flash, redirect, render_template, request, url_for

from ..access import bids, branch_ok, can, can_manage_movement, can_view_movement, gids, log, me, req, roles
from ..constants import STATUSES
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement, User, MissionEditRequest
from ..validation import movement_overlaps, parse_date, record_movement_history

bp = Blueprint('missions', __name__)


def mission_state_label(m):
    return getattr(m, 'mission_state', None) or 'تحت التحرير'


def mission_template_pdf(m, employee, branch, destination, creator=None, print_to_date=None):
    """Generate the mission PDF by using the supplied sample PDF itself as the immutable template.

    Only the variable data regions are redacted/reinserted.  The template's original geometry,
    borders, labels, title, colors and embedded font remain untouched.
    """
    template = os.path.join(current_app.root_path, 'static', 'mission', 'mission_template.pdf')
    font = os.path.join(current_app.root_path, 'static', 'mission', 'mission-original.ttf')
    doc = fitz.open(template)
    page = doc[0]

    # The sample is 595.32 x 841.92 pt. These rectangles are the actual variable cells
    # measured from the supplied PDF, not approximate HTML coordinates.
    # mission number + state, one continuous string
    # current user / job (print metadata)
    # print date + time
    # page number
    # employee name cell
    # basic branch cell
    # employee code cell
    # mission destination cell
    # to-date cell
    # from-date cell
    # approval title
    # approval destination
    variable_regions = [
        fitz.Rect(497.5, 74.0, 553.8, 88.8),
        fitz.Rect(458.0, 89.5, 553.8, 106.2),
        fitz.Rect(31.0, 80.0, 115.0, 94.0),
        fitz.Rect(62.0, 94.0, 84.5, 109.5),
        fitz.Rect(346.6, 158.7, 482.9, 177.2),
        fitz.Rect(156.8, 158.7, 274.4, 177.2),
        fitz.Rect(57.1, 158.7, 88.5, 177.2),
        fitz.Rect(346.5, 188.8, 482.9, 207.2),
        fitz.Rect(299.9, 253.9, 360.2, 272.6),
        fitz.Rect(428.8, 253.9, 483.1, 272.6),
        fitz.Rect(100.0, 281.5, 180.0, 298.5),
        fitz.Rect(100.0, 300.0, 180.0, 317.0),
    ]
    for rect in variable_regions:
        page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # Register the exact font extracted from the supplied sample PDF on the page.
    # This is important: insert_htmlbox can then use the actual Arabic OpenType shaping
    # tables from the sample font instead of falling back to a browser/default font.
    if os.path.exists(font):
        page.insert_font(fontfile=font, fontname='missionorig')
    else:
        fallback = os.path.join(current_app.root_path, 'static', 'mission', 'NotoNaskhArabic-Regular.ttf')
        if os.path.exists(fallback):
            page.insert_font(fontfile=fallback, fontname='missionorig')

    now = datetime.now()

    def put(rect, text, size=9.9603748, align='right', direction='rtl'):
        text = '' if text is None else str(text)
        safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html = f'<div style="font-family:missionorig;font-size:{size:.6f}pt;line-height:1;white-space:nowrap;text-align:{align};direction:{direction};">{safe}</div>'
        page.insert_htmlbox(rect, html)

    # Upper-right: keep the mission number visually BEFORE the Arabic status.
    # LTR here is intentional so the rendered result is exactly: 40873 مغلقة / 40873 تحت التحرير.
    status = 'مغلقة' if mission_state_label(m) == 'مغلقة' else 'تحت التحرير'
    put(fitz.Rect(498.0, 74.2, 552.8, 87.9), f'{m.id} {status}', 8.0403004, 'right', 'ltr')

    creator_name = creator.full_name if creator else ''
    creator_job = creator.job_title if creator and creator.job_title else ''
    if creator_name:
        put(fitz.Rect(462.5, 90.2, 552.8, 98.2), f'- {creator_name}', 6.0002327, 'right', 'rtl')
    if creator_job:
        put(fitz.Rect(462.5, 97.3, 552.8, 106.0), creator_job, 6.0002327, 'right', 'rtl')

    # Keep the source's exact size/color/positions for the small print metadata.
    put(fitz.Rect(32.0, 82.0, 77.8, 93.0), now.strftime('%Y/%m/%d'), 8.0403004, 'left', 'ltr')
    put(fitz.Rect(80.5, 82.0, 115.0, 93.0), now.strftime('%H:%M:%S'), 8.0403004, 'left', 'ltr')
    put(fitz.Rect(62.0, 96.5, 84.5, 107.5), '1 \\ 1', 8.0403004, 'center', 'ltr')

    # Employee information stays completely inside the original cells.
    employee_name = employee.full_name if employee else ''
    gov_name = branch.governorate.name if branch and branch.governorate else ''
    branch_name = branch.name if branch else ''
    destination_gov = (
        destination.governorate.name
        if destination and destination.governorate
        else ''
    )
    destination_name = destination.name if destination else ''

    put(fitz.Rect(347.0, 159.1, 482.7, 176.9), employee_name, 9.9603748, 'right', 'rtl')
    # Requested order: governorate first, then branch. The employee code remains in its own cell.
    basic_branch = (
        f'{gov_name} - {branch_name}'
        if gov_name and branch_name
        else gov_name or branch_name
    )
    put(fitz.Rect(157.0, 159.1, 274.2, 176.9), basic_branch, 9.9603748, 'right', 'rtl')
    put(
        fitz.Rect(57.2, 159.1, 88.4, 176.9),
        employee.job_code if employee and employee.job_code else '',
        9.9603748,
        'center',
        'ltr',
    )

    # Requested order for mission destination: governorate first, then branch.
    mission_dest = (
        f'{destination_gov} - {destination_name}'
        if destination_gov and destination_name
        else destination_gov or destination_name
    )
    put(fitz.Rect(346.8, 189.2, 482.7, 206.9), mission_dest, 9.9603748, 'right', 'rtl')

    # Dates occupy the exact original cells. For an open assignment, print_to_date
    # is a temporary print-only end date and is never written back to the movement.
    effective_to_date = print_to_date or m.to_date
    put(
        fitz.Rect(300.1, 254.6, 359.9, 271.9),
        effective_to_date.strftime('%Y/%m/%d') if effective_to_date else '',
        9.9603748,
        'center',
        'ltr',
    )
    put(
        fitz.Rect(429.1, 254.6, 482.8, 271.9),
        m.from_date.strftime('%Y/%m/%d') if m.from_date else '',
        9.9603748,
        'center',
        'ltr',
    )

    # Approval title is fixed text from the sample; only the destination data changes.
    put(fitz.Rect(116.8, 284.6, 172.2, 296.0), 'اعتماد مدير فرع', 9.9603748, 'center', 'rtl')
    put(fitz.Rect(107.9, 303.0, 170.1, 314.5), mission_dest, 9.9603748, 'center', 'rtl')

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    out.seek(0)
    return out.getvalue()


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
    old = (m.destination_branch_id, m.from_date, m.to_date)
    m.destination_branch_id = destination.id
    m.from_date = fd
    m.to_date = td
    # Closed missions remain closed after an authorized Manager/Admin edit.
    # Reopening is still a distinct audited action.
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    record_movement_history(
        m,
        m.status,
        m.status,
        'MISSION_EDIT',
        f'تعديل بيانات المأمورية: جهة={destination.name}، من={fd}، إلى={td or 'انتداب مفتوح'}',
    )
    log('MISSION_EDIT', 'Movement', m.id, f'{old} -> {(destination.id, fd, td)}')
    db.session.commit()
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
    m.mission_state = 'مغلقة'
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    record_movement_history(
        m,
        m.status,
        m.status,
        'MISSION_CLOSE',
        'إغلاق المأمورية بعد مراجعة بياناتها',
    )
    log('MISSION_CLOSE', 'Movement', m.id, 'إغلاق المأمورية')
    db.session.commit()
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
    m.mission_state = 'تحت التحرير'
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    record_movement_history(m, m.status, m.status, 'MISSION_REOPEN', 'إعادة فتح المأمورية للتعديل')
    log('MISSION_REOPEN', 'Movement', m.id, 'إعادة فتح المأمورية')
    db.session.commit()
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
    if not can('view_reports') or not can_view_movement(m):
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
    if not can('view_reports') or not can_view_movement(m):
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
        creator,
        print_to_date=print_to_date,
    )
    from flask import Response
    return Response(
        data,
        mimetype='application/pdf',
        headers={'Content-Disposition': f'inline; filename=mission-{m.id}.pdf'},
    )


def employee_branch_in_scope(m):
    return bool(m and m.employee and (m.employee.branch_id in set(bids())))


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
    if not can('view_reports') or not can_view_movement(m):
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
    data = mission_template_pdf(m, employee, branch, destination, creator)
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
    global_actor = 'مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles()
    allowed_gids = set(gids())
    allowed_bids = set(bids())
    q = (
        Movement.query.join(Employee).filter(
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
        )
        if global_actor
        else (
            Movement.query.join(Employee).filter(
                Movement.is_active == True,
                Movement.movement_type == 'انتداب',
                Employee.branch_id.in_(allowed_bids),
            )
            if allowed_bids else Movement.query.filter(False)
        )
    )

    gov = request.args.get('governorate_id', '').strip()
    branch = request.args.get('branch_id', '').strip()
    destination_gov = request.args.get('destination_governorate_id', '').strip()
    destination_branch = request.args.get('destination_branch_id', '').strip()
    employee = request.args.get('employee_id', '').strip()
    status = request.args.get('status', '').strip()
    mission_state = request.args.get('mission_state', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    duration = request.args.get('duration', '').strip()

    # «من محافظة» في تقرير المأموريات اختيار بياناتي عالمي؛
    # الوصول الفعلي للموظف والصفوف يظل مقيدًا بـ allowed_bids.
    govs = Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all()
    branches = (
        Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
        if global_actor
        else (
            Branch.query.filter(Branch.id.in_(allowed_bids), Branch.is_active == True)
            .order_by(Branch.name.asc()).all()
            if allowed_bids else []
        )
    )
    destination_governorates = Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all()
    destination_branches = Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()

    selected_gov = None
    if gov.isdigit() and any((g.id == int(gov) for g in govs)):
        selected_gov = db.session.get(Governorate, int(gov))
        branches = [b for b in branches if b.governorate_id == selected_gov.id]
        q = q.filter(Employee.branch.has(Branch.governorate_id == selected_gov.id))
    else:
        gov = ''

    selected_destination_governorate = None
    if destination_gov.isdigit() and any((g.id == int(destination_gov) for g in destination_governorates)):
        selected_destination_governorate = db.session.get(Governorate, int(destination_gov))
        destination_branches = [b for b in destination_branches if b.governorate_id == selected_destination_governorate.id]
        q = q.filter(Movement.destination_branch.has(Branch.governorate_id == selected_destination_governorate.id))
    else:
        destination_gov = ''

    selected_destination_branch = None
    if destination_branch.isdigit() and any((b.id == int(destination_branch) for b in destination_branches)):
        selected_destination_branch = db.session.get(Branch, int(destination_branch))
        q = q.filter(Movement.destination_branch_id == selected_destination_branch.id)
    else:
        destination_branch = ''

    selected_branch = None
    if branch.isdigit() and any((b.id == int(branch) for b in branches)):
        selected_branch = db.session.get(Branch, int(branch))
        q = q.filter(Employee.branch_id == selected_branch.id)
    else:
        branch = ''

    employee_scope_ids = (
        [b.id for b in Branch.query.filter(Branch.is_active == True).all()]
        if 'مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles()
        else list(allowed_bids)
    )
    employees_q = Employee.query.filter(Employee.is_active == True, Employee.branch_id.in_(employee_scope_ids)) if employee_scope_ids else Employee.query.filter(False)
    if selected_branch:
        employees_q = employees_q.filter(Employee.branch_id == selected_branch.id)
    elif selected_gov:
        employees_q = employees_q.join(Branch).filter(Branch.governorate_id == selected_gov.id)
    employees = employees_q.order_by(Employee.full_name.asc()).all()

    if employee.isdigit() and any((e.id == int(employee) for e in employees)):
        q = q.filter(Movement.employee_id == int(employee))
    else:
        employee = ''
    if status in STATUSES:
        q = q.filter(Movement.status == status)
    if mission_state in ('تحت التحرير', 'مغلقة'):
        q = q.filter(Movement.mission_state == mission_state)
    elif mission_state:
        mission_state = ''
    if duration == 'open':
        q = q.filter(Movement.to_date.is_(None))
    elif duration == 'dated':
        q = q.filter(Movement.to_date.isnot(None))
    elif duration != '':
        duration = ''

    from datetime import date as _date

    def _parse_report_date(value):
        try:
            return _date.fromisoformat(value) if value else None
        except ValueError:
            return None

    df = _parse_report_date(date_from)
    dt = _parse_report_date(date_to)
    if df and dt and (df > dt):
        (df, dt) = (dt, df)
    if df:
        q = q.filter(Movement.to_date >= df)
    if dt:
        q = q.filter(Movement.from_date <= dt)

    rows = q.order_by(Movement.from_date.desc(), Movement.id.desc()).all()
    pending_edit_requests_count = 0
    if 'مسؤول التطبيق' in roles():
        pending_edit_requests_count = MissionEditRequest.query.filter_by(status='قيد المراجعة').count()
    elif 'Manager Application Support' in roles():
        scoped_ids = set(bids())
        if scoped_ids:
            pending_edit_requests_count = (MissionEditRequest.query.filter_by(status='قيد المراجعة')
                .join(Movement).join(Employee, Movement.employee_id == Employee.id)
                .filter(Employee.branch_id.in_(scoped_ids)).count())
    return render_template(
        'mission_reports.html',
        rows=rows,
        statuses=STATUSES,
        report_governorates=govs,
        report_branches=branches,
        destination_governorates=destination_governorates,
        destination_branches=destination_branches,
        employees=employees,
        selected_governorate=gov,
        selected_branch=branch,
        selected_destination_governorate=destination_gov,
        selected_destination_branch=destination_branch,
        selected_employee=employee,
        status=status,
        date_from=date_from,
        date_to=date_to,
        duration=duration,
        mission_state=mission_state,
        pending_edit_requests_count=pending_edit_requests_count,
    )


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
    pending = MissionEditRequest.query.filter_by(movement_id=m.id, status='قيد المراجعة').first()
    if pending:
        flash('يوجد بالفعل طلب تعديل قيد المراجعة لهذه المأمورية.')
        return redirect('/reports/assignments/print-missions')
    snapshot = f'الموظف: {m.employee.full_name if m.employee else "—"} | من: {m.from_date} | إلى: {m.to_date} | الوجهة: {m.destination.name if m.destination else "—"}'
    req_row = MissionEditRequest(
        movement_id=m.id, requested_by=me().id, reason=reason, details_snapshot=snapshot, status='قيد المراجعة'
    )
    db.session.add(req_row)
    db.session.flush()
    log('MISSION_EDIT_REQUEST', 'MissionEditRequest', req_row.id, f'طلب تعديل مأمورية #{m.id}: {reason}')
    db.session.commit()
    flash('تم إرسال طلب التعديل إلى الـManager مع كامل التفاصيل والسبب.')
    return redirect('/reports/assignments/print-missions')


@bp.get('/reports/assignments/edit-requests')
@req
def mission_edit_requests():
    rs = roles()
    if not ({'مسؤول التطبيق', 'Manager Application Support'} & rs) or not can('manage_movements'):
        abort(403)
    q = MissionEditRequest.query.filter_by(status='قيد المراجعة').join(Movement)
    if 'مسؤول التطبيق' not in rs:
        scoped = set(bids())
        if not scoped:
            q = q.filter(False)
        else:
            q = q.join(Employee, Movement.employee_id == Employee.id).filter(Employee.branch_id.in_(scoped))
    rows = q.order_by(MissionEditRequest.created_at.asc(), MissionEditRequest.id.asc()).all()
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
    branches = Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
    govs = Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all()
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
    if not destination or not destination.is_active or not fd or final_state not in ('مغلقة', 'تحت التحرير'):
        flash('أكمل بيانات التعديل واختر الحالة النهائية الصحيحة.')
        return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))
    if td and td < fd:
        flash('تاريخ النهاية لا يجوز أن يسبق البداية.')
        return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))
    if final_state == 'مغلقة' and not td:
        flash('لا يمكن حفظ المأمورية مغلقة بدون تاريخ نهاية.')
        return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))
    overlap = movement_overlaps(m.employee_id, 'انتداب', fd, td, None, m.id)
    if overlap:
        flash(overlap)
        return redirect(url_for('missions.mission_edit_request_review', request_id=r.id))
    m.destination_branch_id = destination.id
    m.from_date = fd
    m.to_date = td
    m.mission_state = final_state
    m.modified_by = me().id
    m.modified_at = datetime.utcnow()
    r.status = 'تم التنفيذ'
    r.reviewed_by = me().id
    r.reviewed_at = datetime.utcnow()
    r.manager_notes = notes
    r.final_state = final_state
    record_movement_history(m, m.status, m.status, 'MISSION_EDIT_REQUEST_EXECUTED', f'تنفيذ طلب تعديل #{r.id}; الحالة النهائية={final_state}; السبب={r.reason}; ملاحظات={notes}')
    log('MISSION_EDIT_REQUEST_EXECUTED', 'MissionEditRequest', r.id, f'المأمورية #{m.id} أصبحت {final_state}')
    db.session.commit()
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
    from io import BytesIO
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment
    from flask import send_file
    wb = Workbook(); ws = wb.active; ws.title = 'المأموريات'
    headers = ['رقم المأمورية','كود شئون العاملين','اسم الموظف','المحافظة الأصلية','الفرع الأصلي','من محافظة','من فرع','إلى محافظة','إلى فرع','من تاريخ','إلى تاريخ','عدد الأيام','حالة المأمورية','تاريخ الإنشاء','تاريخ الإغلاق','منشئ المأمورية','سبب الإغلاق','ملاحظات']
    ws.append(headers)
    for c in ws[1]: c.font = Font(bold=True); c.alignment = Alignment(horizontal='center')
    for m in rows:
        emp=m.employee; origin=emp.branch if emp else None; dest=m.destination
        start=m.from_date; end=m.to_date
        days=(end-start).days+1 if start and end else None
        ws.append([m.id, emp.job_code if emp else '', emp.full_name if emp else '', origin.governorate.name if origin and origin.governorate else '', origin.name if origin else '', origin.governorate.name if origin and origin.governorate else '', origin.name if origin else '', dest.governorate.name if dest and dest.governorate else '', dest.name if dest else '', start, end, days, m.mission_state or 'تحت التحرير', m.created_at, m.closed_at, (m.employee.full_name if m.employee else ''), m.closure_reason or '', m.notes or ''])
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        letter=col[0].column_letter; maxlen=max(len(str(c.value or '')) for c in col[:200]); ws.column_dimensions[letter].width=min(max(maxlen+2,12),32)
    out=BytesIO(); wb.save(out); out.seek(0)
    return send_file(out, as_attachment=True, download_name='المأموريات.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


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
    if not can('view_reports') or m.movement_type != 'انتداب' or (not can_view_movement(m)):
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
