"""Employee records, resignation/reactivation and role conversion."""

from datetime import date, datetime

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for

from ..access import (
    actual_roles,
    bids,
    branch_ok,
    can,
    can_manage_employee,
    gids,
    log,
    me,
    only,
    req,
    roles,
    user_gov_ids,
)
from ..assignments import (
    current_assignment_for_employee,
    effective_branch_id_for_employee,
    employee_is_effectively_in_branch,
    organizational_entry_for_employee,
    sync_role_accounts,
)
from ..constants import MOVEMENT_TYPES
from ..extensions import db
from ..models import (
    Branch,
    Employee,
    EntryAssignment,
    EntryAssignmentBranch,
    Governorate,
    Movement,
    SupervisorEntry,
    User,
    UserBranch,
    UserRole,
)
from ..validation import parse_date, valid_email

bp = Blueprint('employees', __name__)


@bp.get('/employee-role-select')
@req
@only('مسؤول التطبيق')
def employee_role_select():
    eid = request.args.get('employee_id', '').strip()
    if not eid.isdigit():
        flash('اختر موظفًا مسجلًا أولًا.')
        return redirect('/structure#add-entry-role')
    e = db.session.get(Employee, int(eid))
    if not e or not e.is_active:
        flash('الموظف غير موجود أو غير نشط.')
        return redirect('/structure#add-entry-role')
    if e.user_id and 'المدخل الأول' in actual_roles(db.session.get(User, e.user_id)):
        flash('هذا الموظف مسجل بالفعل كمدخل أول.')
        return redirect('/structure#add-entry-role')
    return redirect(url_for('employees.employee_convert_role', i=e.id))


@bp.get('/employee-search')
@req
def employee_search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return {'results': []}
    bs = bids()
    if not bs:
        return {'results': []}
    like = f'%{q}%'
    rows = (
        Employee.query.filter(Employee.is_active == True, Employee.branch_id.in_(bs))
        .filter(
            (
                Employee.full_name.ilike(like)
                | Employee.job_code.ilike(like)
                | Employee.job_title.ilike(like)
            ),
        )
        .order_by(Employee.full_name)
        .limit(12)
        .all()
    )
    results = []
    for e in rows:
        moves = (
            Movement.query.filter_by(employee_id=e.id, is_active=True)
            .order_by(Movement.id.desc())
            .limit(80)
            .all()
        )
        latest = {}
        for mv in moves:
            if mv.movement_type not in latest:
                latest[mv.movement_type] = mv

        def fmt(mv):
            if not mv:
                return None
            if mv.movement_type == 'إجازة':
                dates = ''
                if mv.from_date and mv.to_date:
                    dates = f'{mv.from_date.strftime('%Y-%m-%d')} ← {mv.to_date.strftime('%Y-%m-%d')}'
                return {'label': mv.leave_type or 'إجازة', 'detail': dates, 'status': mv.status}
            if mv.movement_type == 'انتداب':
                dates = ''
                if mv.from_date and mv.to_date:
                    dates = f'{mv.from_date.strftime('%Y-%m-%d')} ← {mv.to_date.strftime('%Y-%m-%d')}'
                return {
                    'label': mv.destination.name if mv.destination else 'انتداب',
                    'detail': dates,
                    'status': mv.status,
                }
            return {
                'label': 'إذن',
                'detail': mv.permission_date.strftime('%Y-%m-%d') if mv.permission_date else '—',
                'status': mv.status,
            }

        results.append(
            {
                'id': e.id,
                'name': e.full_name,
                'code': e.job_code or '',
                'branch': e.branch.name if e.branch else '',
                'last_leave': fmt(latest.get('إجازة')),
                'last_assignment': fmt(latest.get('انتداب')),
                'last_permission': fmt(latest.get('إذن')),
            },
        )
    return {'results': results}


@bp.route('/employees', methods=['GET', 'POST'])
@req
def employees():
    bs = bids()
    if request.method == 'POST':
        if not can('manage_employees'):
            abort(403)
        bid = (
            int(request.form.get('branch_id', '0'))
            if request.form.get('branch_id', '').isdigit()
            else 0
        )
        if not branch_ok(bid):
            abort(403)
        submitted_gid = (
            int(request.form.get('governorate_id', '0'))
            if request.form.get('governorate_id', '').isdigit()
            else 0
        )
        branch_obj = db.session.get(Branch, bid)
        name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        job_title = request.form.get('job_title', '').strip()
        job_code = request.form.get('job_code', '').strip()
        hire_date = request.form.get('hire_date', '').strip()
        company_phone = request.form.get('company_phone', '').strip()
        personal_phone = request.form.get('personal_phone', '').strip()
        if not branch_obj or branch_obj.governorate_id != submitted_gid:
            flash('يجب اختيار محافظة وفرع صحيحين.')
        elif not all([name, email, job_title, job_code, hire_date]):
            flash('جميع البيانات الأساسية للموظف مطلوبة.')
        elif not valid_email(email):
            flash('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.')
        elif not parse_date(hire_date):
            flash('تاريخ التعيين مطلوب وبصيغة صحيحة.')
        else:
            existing = Employee.query.filter_by(email=email).first()
            if existing:
                if existing.is_active:
                    flash('البريد الإلكتروني مستخدم بالفعل لموظف آخر.')
                    return redirect(url_for('employees.employees'))
                if existing.resignation_date is not None:
                    flash(
                        'الموظف مسجل كمستقيل. أعد تفعيله أولًا من «الموظفون المستقيلون» بتاريخ إعادة التعيين، ثم حدّث بياناته.',
                    )
                    return redirect(url_for('employees.resigned_employees'))
                # الموظف غير ظاهر في القائمة لأنه معطّل إداريًا. لا ننشئ سجلًا ثانيًا.
                existing.full_name = name
                existing.email = email
                existing.branch_id = bid
                existing.job_title = job_title
                existing.job_code = job_code
                existing.hire_date = parse_date(hire_date)
                existing.company_phone = company_phone
                existing.personal_phone = personal_phone
                existing.is_active = True
                existing.deleted_at = None
                existing.deleted_by = None
                log('RESTORE', 'Employee', existing.id, existing.full_name)
                db.session.commit()
                flash('تمت استعادة الموظف السابق وتحديث بياناته، مع الاحتفاظ بكل تاريخه وحركاته.')
                return redirect(url_for('employees.employee_card', i=existing.id))
            e = Employee(
                employee_code=None,
                email=email,
                full_name=name,
                branch_id=bid,
                job_title=job_title,
                job_code=job_code,
                hire_date=parse_date(hire_date),
                company_phone=company_phone,
                personal_phone=personal_phone,
            )
            db.session.add(e)
            db.session.commit()
            log('ADD', 'Employee', e.id, e.full_name)
            db.session.commit()
            flash('تمت إضافة الموظف بنجاح. يمكنك الآن تسجيل أول حركة له.')
            return redirect(url_for('employees.employee_card', i=e.id))
    # في شاشة الموظفين، المشرف يستطيع اختيار أي محافظة للبحث والاستعراض.
    # هذا لا يمنحه صلاحيات تعديل/حذف خارج نطاقه؛ عمليات التعديل والحذف تظل محكومة بدوال الصلاحيات.
    supervisor_search_all = 'مشرف محافظة' in roles()
    search_branch_ids = (
        [b.id for b in Branch.query.filter(Branch.is_active == True).all()]
        if supervisor_search_all
        else bs
    )
    branches = (
        (
            Branch.query.filter(Branch.id.in_(search_branch_ids), Branch.is_active == True)
            .order_by(Branch.name)
            .all()
        )
        if search_branch_ids
        else []
    )
    q = request.args.get('q', '').strip()
    employee_filter = request.args.get('employee_id', '').strip()
    branch_filter = request.args.get('branch_id', '').strip()
    allowed_search_branch_ids = set(search_branch_ids)
    gov_filter = request.args.get('governorate_id', '').strip()
    query = (
        Employee.query.filter(Employee.is_active == True, Employee.branch_id.in_(search_branch_ids))
        if search_branch_ids
        else Employee.query.filter(False)
    )
    if q:
        like = f'%{q}%'
        query = query.filter(
            db.or_(
                Employee.full_name.ilike(like),
                Employee.job_code.ilike(like),
                Employee.job_title.ilike(like),
            ),
        )
    if branch_filter.isdigit() and int(branch_filter) in allowed_search_branch_ids:
        query = query.filter(Employee.branch_id == int(branch_filter))
    rows = [
        e
        for e in query.order_by(Employee.full_name).all()
        if e.branch_id in allowed_search_branch_ids or effective_branch_id_for_employee(e.id) in allowed_search_branch_ids
    ]
    if branch_filter.isdigit() and int(branch_filter) in allowed_search_branch_ids:
        rows = [e for e in rows if employee_is_effectively_in_branch(e, int(branch_filter))]
    govs = (
        Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if supervisor_search_all
        else (
            (
                Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
                .order_by(Governorate.name)
                .all()
            )
            if gids()
            else []
        )
    )
    allowed_search_gov_ids = {g.id for g in govs}
    if gov_filter.isdigit() and int(gov_filter) in allowed_search_gov_ids:
        branches = (
            Branch.query.filter(
                Branch.governorate_id == int(gov_filter),
                Branch.is_active == True,
                Branch.id.in_(search_branch_ids),
            )
            .order_by(Branch.name)
            .all()
        )
        if not (branch_filter.isdigit() and int(branch_filter) in [b.id for b in branches]):
            branch_filter = ''
        query = Employee.query.filter(
            Employee.is_active == True,
            Employee.branch_id.in_([b.id for b in branches]),
        )
        if q:
            like = f'%{q}%'
            query = query.filter(
                db.or_(
                    Employee.full_name.ilike(like),
                    Employee.job_code.ilike(like),
                    Employee.job_title.ilike(like),
                ),
            )
        rows = (
            [
                e
                for e in query.order_by(Employee.full_name).all()
                if employee_is_effectively_in_branch(e, int(branches[0].id))
            ]
            if len(branches) == 1
            else [
                e
                for e in query.order_by(Employee.full_name).all()
                if any((employee_is_effectively_in_branch(e, b.id) for b in branches))
            ]
        )
    if employee_filter.isdigit():
        eid = int(employee_filter)
        rows = [e for e in rows if e.id == eid]
    # المدخل الأول المسؤول عن كل موظف: يُحسب من فروع المسؤولية التنظيمية،
    # مع الاحتفاظ بسجل موظف واحد وعدم إنشاء سجل إضافي للمدخل.
    entry_map = {}
    if rows:
        row_ids = {e.id for e in rows}
        assignments = (
            EntryAssignment.query.filter(
                EntryAssignment.employee_id.in_(row_ids),
                EntryAssignment.is_active == True,
            )
            .all()
        )
        for a in assignments:
            entry_map[a.employee_id] = a.employee.full_name if a.employee else ''

    # عرض جميع المحافظات في قائمة البحث للحسابات ذات النطاق الشامل،
    # بينما تبقى نتائج الموظفين نفسها محكومة بصلاحيات/nطاق الحساب.
    filter_govs = (
        (
            Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
            .order_by(Governorate.name)
            .all()
        )
        if gids()
        else []
    )
    # محافظة الإضافة تبقى مقيدة بنطاق الإدارة للمستخدم، بينما قائمة البحث يمكن أن تشمل كل المحافظات للمشرف.
    add_govs = (
        (
            Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
            .order_by(Governorate.name)
            .all()
        )
        if gids()
        else []
    )
    add_branch_ids = (
        {
            b.id
            for b in Branch.query.filter(Branch.governorate_id.in_([g.id for g in add_govs]), Branch.is_active == True).all()
        }
        if add_govs
        else set()
    )
    add_branches = (
        (
            Branch.query.filter(Branch.id.in_(add_branch_ids), Branch.is_active == True)
            .order_by(Branch.name)
            .all()
        )
        if add_branch_ids
        else []
    )

    # عرض الموظفين يكون مجمعًا حسب المحافظة ثم الفرع، بدل قائمة واحدة طويلة.
    grouped_employees = []
    branch_ids_with_rows = sorted({e.branch_id for e in rows if e.branch_id})
    if branch_ids_with_rows:
        branch_objs = (
            Branch.query.filter(Branch.id.in_(branch_ids_with_rows))
            .order_by(Branch.governorate_id, Branch.name)
            .all()
        )
        by_branch = {b.id: [] for b in branch_objs}
        for e in rows:
            if e.branch_id in by_branch:
                by_branch[e.branch_id].append(e)
        by_gov = {}
        for b in branch_objs:
            if by_branch.get(b.id):
                by_gov.setdefault(b.governorate_id, {'governorate': b.governorate, 'branches': []})['branches'].append(
                    {'branch': b, 'employees': by_branch[b.id]},
                )
        grouped_employees = sorted(
            by_gov.values(),
            key=lambda x: x['governorate'].name if x['governorate'] else '',
        )
        for group in grouped_employees:
            group['branches'].sort(key=lambda x: x['branch'].name)
    return render_template(
        'employees.html',
        rows=rows,
        rows_page=rows,
        grouped_employees=grouped_employees,
        bs=branches,
        add_govs=add_govs,
        add_bs=add_branches,
        q=q,
        govs=filter_govs,
        gov_filter=gov_filter,
        entry_map=entry_map,
        total_rows=len(rows),
    )


@bp.get('/employees/edit-data')
@req
def employee_edit_data():
    if not can('manage_employees'):
        abort(403)
    bs = bids()
    rows = (
        (
            Employee.query.join(Branch, Employee.branch_id == Branch.id)
            .filter(
                Employee.is_active == True,
                Branch.is_active == True,
                Employee.branch_id.in_(bs),
            )
            .order_by(Employee.full_name)
            .all()
        )
        if bs
        else []
    )
    q = request.args.get('q', '').strip()
    if q:
        ql = q.lower()
        rows = [
            e
            for e in rows
            if ql in (e.full_name or '').lower() or ql in (e.job_code or '').lower() or ql in (e.email or '').lower()
        ]
    return render_template('employee_edit_data.html', rows=rows, q=q)


@bp.route('/employees/<int:i>/edit', methods=['GET', 'POST'])
@req
def employee_edit(i):
    e = db.session.get(Employee, i)
    if (
        not e
        or e.deleted_at is not None
        or not can_manage_employee(e)
        or not can('manage_employees')
    ):
        abort(403)
    if request.method == 'POST':
        bid = int(request.form['branch_id'])
        if not branch_ok(bid):
            abort(403)
        submitted_gid = (
            int(request.form.get('governorate_id', '0'))
            if request.form.get('governorate_id', '').isdigit()
            else 0
        )
        branch_obj = db.session.get(Branch, bid)
        if not branch_obj or branch_obj.governorate_id != submitted_gid:
            flash('يجب اختيار فرع تابع للمحافظة المحددة.')
            return redirect(url_for('employees.employee_edit', i=i))
        name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        job_title = request.form.get('job_title', '').strip()
        job_code = request.form.get('job_code', '').strip()
        hire_date = request.form.get('hire_date', '').strip()
        company_phone = request.form.get('company_phone', '').strip()
        personal_phone = request.form.get('personal_phone', '').strip()
        if not all([name, email, job_title, job_code, hire_date, company_phone, personal_phone]):
            flash('جميع بيانات الموظف مطلوبة.')
            return redirect(url_for('employees.employee_edit', i=i))
        if not valid_email(email):
            flash('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.')
            return redirect(url_for('employees.employee_edit', i=i))
        dup = Employee.query.filter(Employee.email == email, Employee.id != i).first()
        if dup:
            flash('البريد الإلكتروني مستخدم بالفعل لموظف آخر.')
            return redirect(url_for('employees.employee_edit', i=i))
        if not parse_date(hire_date):
            flash('تاريخ التعيين مطلوب وبصيغة صحيحة.')
            return redirect(url_for('employees.employee_edit', i=i))
        e.full_name = name
        e.email = email
        e.branch_id = bid
        e.job_title = job_title
        e.job_code = job_code
        if e.user_id:
            linked_user = db.session.get(User, e.user_id)
            if linked_user:
                other = User.query.filter(User.email == email, User.id != linked_user.id).first()
                if other:
                    flash('البريد الإلكتروني مستخدم بالفعل لحساب آخر.')
                    return redirect(url_for('employees.employee_edit', i=i))
                linked_user.email = email
                linked_user.full_name = name
                linked_user.job_title = job_title
                linked_user.job_code = job_code
        e.hire_date = parse_date(hire_date)
        e.company_phone = company_phone
        e.personal_phone = personal_phone
        log('EDIT', 'Employee', i, e.full_name)
        db.session.commit()
        flash('تم تعديل الموظف.')
        return redirect(url_for('employees.employees'))
    return render_template(
        'employee_edit.html',
        e=e,
        bs=Branch.query.filter(Branch.id.in_(bids()), Branch.is_active == True).all(),
        govs=(
            Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
            .order_by(Governorate.name)
            .all()
        ),
    )


@bp.route('/employees/<int:i>/convert-role', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق')
def employee_convert_role(i):
    e = db.session.get(Employee, i)
    if not e or not e.is_active:
        abort(404)
    assignment = organizational_entry_for_employee(e)
    is_entry = bool(assignment)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'to_entry':
            branch_ids = {int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
            allowed_branch_ids = {b.id for b in Branch.query.filter_by(is_active=True).all()}
            branch_ids &= allowed_branch_ids
            if not branch_ids:
                flash('يجب اختيار فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
                return redirect(url_for('employees.employee_convert_role', i=i))
            sup_id = request.form.get('supervisor_id', '').strip()
            sup = db.session.get(User, int(sup_id)) if sup_id.isdigit() else None
            gov_ids = {
                b.governorate_id
                for b in Branch.query.filter(Branch.id.in_(branch_ids), Branch.is_active == True).all()
            }
            if (
                not sup
                or 'مشرف محافظة' not in actual_roles(sup)
                or not sup.is_active
                or not gov_ids & user_gov_ids(sup)
            ):
                flash('يجب اختيار مشرف محافظة صحيح لفروع المسؤولية.')
                return redirect(url_for('employees.employee_convert_role', i=i))
            # الدور هنا تنظيمي فقط: لا ننشئ اسم مستخدم أو كلمة مرور جديدة.
            if assignment:
                assignment.supervisor_id = sup.id
                assignment.is_active = True
                EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).delete()
            else:
                assignment = EntryAssignment(employee_id=e.id, supervisor_id=sup.id, is_active=True)
                db.session.add(assignment)
                db.session.flush()
            for bid in sorted(branch_ids):
                db.session.add(
                    EntryAssignmentBranch(entry_assignment_id=assignment.id, branch_id=bid),
                )
            # توافق مع البيانات القديمة: إذا كان للموظف حساب دخول قديم يحمل دور المدخل الأول،
            # أزل الدور القديم فقط ولا تحذف الحساب إذا كان له أدوار أخرى.
            if e.user_id:
                old_user = db.session.get(User, e.user_id)
                if old_user and 'المدخل الأول' in actual_roles(old_user):
                    UserRole.query.filter_by(user_id=old_user.id, role='المدخل الأول').delete()
                    UserBranch.query.filter_by(user_id=old_user.id).delete()
                    SupervisorEntry.query.filter_by(entry_id=old_user.id).delete()
                    if not actual_roles(old_user):
                        old_user.is_active = False
                    sync_role_accounts(old_user)
            log('ROLE_CHANGE', 'Employee', e.id, 'تحويل الموظف إلى مدخل أول تنظيمي بدون حساب دخول')
            db.session.commit()
            flash(
                'تم تحويل الموظف إلى مدخل أول تنظيمي مع الاحتفاظ بسجل الموظف وفرع التعيين والحركات السابقة.',
            )
            return redirect(url_for('employees.employee_edit', i=e.id))
        if action == 'to_employee':
            if not assignment:
                flash('الموظف ليس مدخلًا أول.')
                return redirect(url_for('employees.employee_convert_role', i=i))
            EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).delete()
            db.session.delete(assignment)
            # تنظيف أي ارتباطات قديمة مرتبطة بحساب سابق لهذا الموظف دون حذف الموظف أو تاريخه.
            if e.user_id:
                old_user = db.session.get(User, e.user_id)
                if old_user and 'المدخل الأول' in actual_roles(old_user):
                    UserRole.query.filter_by(user_id=old_user.id, role='المدخل الأول').delete()
                    UserBranch.query.filter_by(user_id=old_user.id).delete()
                    SupervisorEntry.query.filter_by(entry_id=old_user.id).delete()
                    if not actual_roles(old_user):
                        old_user.is_active = False
                    sync_role_accounts(old_user)
            log('ROLE_CHANGE', 'Employee', e.id, 'إرجاع المدخل الأول التنظيمي إلى موظف عادي')
            db.session.commit()
            flash(
                'تم إرجاع الموظف إلى موظف عادي مع الاحتفاظ بكل بياناته وحركاته. لم تُحذف الفروع أو الموظفون التابعون له.',
            )
            return redirect(url_for('employees.employee_edit', i=e.id))
    branches = Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
    supervisors = [
        u
        for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
        if 'مشرف محافظة' in actual_roles(u)
    ]
    current_branch_ids = (
        {
            x.branch_id
            for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).all()
        }
        if assignment
        else set()
    )
    current_sup = assignment.supervisor if assignment else None
    return render_template(
        'employee_role_convert.html',
        e=e,
        is_entry=is_entry,
        branches=branches,
        supervisors=supervisors,
        current_branch_ids=current_branch_ids,
        current_sup=current_sup,
    )


@bp.post('/employees/<int:i>/resign')
@req
def employee_resign(i):
    e = db.session.get(Employee, i)
    if not e or not can_manage_employee(e) or (not can('manage_employees')):
        abort(403)
    if not e.is_active:
        flash('الموظف موجود بالفعل ضمن الموظفين المستقيلين.')
        return redirect('/employees')
    raw_date = (request.form.get('resignation_date') or '').strip()
    resignation_date = parse_date(raw_date)
    if not resignation_date:
        flash('يجب تحديد تاريخ الاستقالة.')
        return redirect('/employees')
    if resignation_date > date.today():
        flash('تاريخ الاستقالة لا يمكن أن يكون في المستقبل.')
        return redirect('/employees')
    e.is_active = False
    e.resignation_date = resignation_date
    e.rehire_date = None
    e.resignation_by = me().id if me() else None
    # الاحتفاظ بـ deleted_at داخليًا للتوافق مع السجلات القديمة ومنع ظهور الموظف في القوائم النشطة.
    e.deleted_at = datetime.utcnow()
    e.deleted_by = me().id if me() else None
    # إنهاء أي انتداب مفتوح مع الاحتفاظ بالحركة كاملة في التاريخ.
    open_moves = (
        Movement.query.filter_by(
            employee_id=e.id,
            is_active=True,
            movement_type='انتداب',
            assignment_state='ساري',
        )
        .all()
    )
    for m in open_moves:
        m.assignment_state = 'مغلق'
        m.closed_by = me().id if me() else None
        m.closed_at = datetime.utcnow()
        m.closure_reason = 'استقالة الموظف'
    assignment = organizational_entry_for_employee(e)
    if assignment:
        assignment.is_active = False
    # إزالة ارتباطات المدخل الأول التنظيمية حتى لا يبقى الموظف المستقيل مرتبطًا بفروع.
    if e.user_id:
        linked_user = db.session.get(User, e.user_id)
        if linked_user:
            UserRole.query.filter_by(user_id=linked_user.id, role='المدخل الأول').delete()
            UserBranch.query.filter_by(user_id=linked_user.id).delete()
            SupervisorEntry.query.filter_by(entry_id=linked_user.id).delete()
            if not actual_roles(linked_user):
                linked_user.is_active = False
    log(
        'RESIGN',
        'Employee',
        i,
        f'استقالة الموظف: {e.full_name} بتاريخ {resignation_date.isoformat()}',
    )
    db.session.commit()
    flash(
        f'تم تسجيل استقالة {e.full_name} بتاريخ {resignation_date.strftime('%Y-%m-%d')}. أزيل من قوائم الفرع ونُقل إلى الموظفين المستقيلين مع الاحتفاظ بكل تاريخه.',
    )
    return redirect(url_for('employees.employees'))


@bp.post('/employees/<int:i>/delete')
@req
def employee_delete(i):
    e = db.session.get(Employee, i)
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
    if not e:
        abort(404)
    # حذف منطقي إداري استثنائي؛ مسار دورة حياة الموظف الطبيعي هو «استقالة».
    e.is_active = False
    e.deleted_at = datetime.utcnow()
    e.deleted_by = me().id if me() else None
    assignment = organizational_entry_for_employee(e)
    if assignment:
        assignment.is_active = False
    log('DELETE', 'Employee', i, f'حذف منطقي إداري للموظف: {e.full_name}')
    db.session.commit()
    flash('تم إخفاء الموظف إداريًا. لا يُستخدم هذا المسار لتسجيل الاستقالة؛ استخدم «استقالة».')
    return redirect(url_for('employees.employees'))


@bp.get('/employees/resigned')
@req
def resigned_employees():
    if not can('manage_employees'):
        abort(403)
    # الموظفون المستقيلون يُعرضون من نطاق الفروع السابق، مع إبقاء السجل محفوظًا.
    bs = bids()
    q = Employee.query.filter(
        Employee.resignation_date.isnot(None) | Employee.deleted_at.isnot(None),
    )
    if bs:
        q = q.filter(Employee.branch_id.in_(bs))
    rows = (
        q.order_by(
            Employee.resignation_date.desc().nullslast(),
            Employee.deleted_at.desc().nullslast(),
            Employee.full_name,
        )
        .all()
    )
    return render_template('employee_resigned.html', rows=rows)



@bp.post('/employees/<int:i>/reactivate')
@req
def employee_reactivate(i):
    e = db.session.get(Employee, i)
    if not e or (e.resignation_date is None and e.deleted_at is None):
        abort(404)
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
    raw_date = (request.form.get('rehire_date') or '').strip()
    rehire_date = parse_date(raw_date)
    if not rehire_date:
        flash('يجب تحديد تاريخ إعادة التعيين.')
        return redirect(url_for('employees.resigned_employees'))
    if e.resignation_date and rehire_date < e.resignation_date:
        flash('تاريخ إعادة التعيين يجب أن يكون في أو بعد تاريخ الاستقالة.')
        return redirect(url_for('employees.resigned_employees'))
    e.is_active = True
    e.rehire_date = rehire_date
    e.deleted_at = None
    e.deleted_by = None
    e.resignation_by = None
    log(
        'REACTIVATE',
        'Employee',
        i,
        f'إعادة تعيين الموظف: {e.full_name} بتاريخ {rehire_date.isoformat()}',
    )
    db.session.commit()
    flash(
        f'تمت إعادة تفعيل {e.full_name} بتاريخ {rehire_date.strftime('%Y-%m-%d')}. أصبح الموظف متاحًا للفرع مرة أخرى.',
    )
    return redirect(url_for('employees.employee_card', i=e.id))


@bp.get('/employee/<int:i>')
@req
def employee_card(i):
    e = db.session.get(Employee, i)
    if not e:
        abort(404)
    if not e.is_active and (not (can('manage_employees') and can_manage_employee(e))):
        abort(403)
    ms = (
        Movement.query.filter_by(employee_id=i, is_active=True)
        .order_by(
            Movement.from_date.desc().nullslast(),
            Movement.permission_date.desc().nullslast(),
            Movement.id.desc(),
        )
        .all()
    )
    last = {k: next((m for m in ms if m.movement_type == k), None) for k in MOVEMENT_TYPES}
    current_assignment = current_assignment_for_employee(e.id)
    current_branch = (
        current_assignment.destination
        if current_assignment and current_assignment.destination
        else e.branch
    )
    return render_template(
        'employee.html',
        e=e,
        ms=ms,
        last=last,
        current_assignment=current_assignment,
        current_branch=current_branch,
    )
