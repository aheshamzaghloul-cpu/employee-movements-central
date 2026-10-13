"""Employee records, resignation/reactivation and role conversion."""

from datetime import date, datetime

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from ..access import (
    actual_roles,
    bids,
    branch_ok,
    can,
    can_manage_employee,
    can_view_movement,
    gids,
    log,
    me,
    only,
    req,
    roles,
    scope_governorates_for_user,
    user_gov_ids,
)
from ..assignments import (
    current_assignment_for_employee,
    resolve_current_movement,
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
from ..search import normalize_search_text, search_contains

bp = Blueprint('employees', __name__)


def _safe_parse_date(value):
    """Parse a form date without turning invalid user input into a 500 error."""
    try:
        return parse_date(value)
    except (TypeError, ValueError):
        return None


@bp.get('/employee-role-select')
@req
@only('مسؤول التطبيق')
def employee_role_select():
    eid = request.args.get('employee_id', '').strip()
    if not eid.isdigit():
        flash('اختر موظفًا مسجلًا أولًا.')
        return redirect('/#entry-directory')
    e = db.session.get(Employee, int(eid))
    if not e or not e.is_active:
        flash('الموظف غير موجود أو غير نشط.')
        return redirect('/#entry-directory')
    if e.user_id and 'المدخل الأول' in actual_roles(db.session.get(User, e.user_id)):
        flash('هذا الموظف مسجل بالفعل كمدخل أول.')
        return redirect('/#entry-directory')
    return redirect(url_for('employees.employee_convert_role', i=e.id))


@bp.get('/employee-search')
@req
def employee_search():
    """Global homepage employee search with movement details gated separately.

    The search is intentionally independent from the selected work governorate,
    but authentication alone does not grant access to employee-directory data.
    """
    if not (can('manage_employees') or can('view_reports')):
        abort(403)
    q = (request.args.get('q', '') or '').strip()
    normalized_q = normalize_search_text(q)
    gov_raw = (request.args.get('governorate_id') or '').strip()
    branch_raw = (request.args.get('branch_id') or '').strip()
    if len(q) > 120 or (len(normalized_q) < 2 and not branch_raw):
        return {'results': []}
    if (gov_raw and not gov_raw.isdigit()) or (branch_raw and not branch_raw.isdigit()):
        return {'results': []}
    query = (
        Employee.query
        .join(Branch, Employee.branch_id == Branch.id)
        .join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Employee.is_active == True, Branch.is_active == True, Governorate.is_active == True)
    )
    if gov_raw:
        gov = db.session.get(Governorate, int(gov_raw))
        if not gov or not gov.is_active:
            return {'results': []}
        query = query.filter(Branch.governorate_id == gov.id)
    if branch_raw:
        branch = db.session.get(Branch, int(branch_raw))
        if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
            return {'results': []}
        if gov_raw and branch.governorate_id != int(gov_raw):
            return {'results': []}
        query = query.filter(Employee.branch_id == branch.id)
    if normalized_q:
        query = query.filter(db.or_(
            search_contains(Employee.full_name, q),
            search_contains(Employee.job_code, q),
        ))
    rows = query.order_by(Employee.full_name).limit(20).all()

    # This endpoint powers live identity suggestions only. Keep it lean and do not
    # fetch movement histories merely to populate a search dropdown.
    results = [
        {
            'id': e.id,
            'name': e.full_name,
            'code': e.job_code or '',
            'job_title': e.job_title or '',
            'branch': e.branch.name if e.branch else '',
            'governorate': e.branch.governorate.name if e.branch and e.branch.governorate else '',
        }
        for e in rows
    ]
    return {'results': results}


@bp.route('/employees', methods=['GET', 'POST'])
@req
def employees():
    if not (can('manage_employees') or can('view_reports')):
        abort(403)
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
        email = request.form.get('email', '').strip().lower()
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
        elif not _safe_parse_date(hire_date):
            flash('تاريخ التعيين مطلوب وبصيغة صحيحة.')
        else:
            # Email and HR code are compared case-insensitively across active and
            # historical employees; a resigned record must not permit a duplicate.
            existing = Employee.query.filter(func.lower(Employee.email) == email).first()
            duplicate_code_query = Employee.query.filter(
                func.lower(func.trim(Employee.job_code)) == job_code.lower(),
            )
            if existing:
                duplicate_code_query = duplicate_code_query.filter(Employee.id != existing.id)
            if duplicate_code_query.first():
                flash('كود شئون العاملين مستخدم بالفعل لموظف آخر.')
                return redirect(url_for('employees.employees'))
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
                existing.hire_date = _safe_parse_date(hire_date)
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
                hire_date=_safe_parse_date(hire_date),
                company_phone=company_phone,
                personal_phone=personal_phone,
            )
            db.session.add(e)
            db.session.flush()
            log('ADD', 'Employee', e.id, e.full_name)
            db.session.commit()
            flash('تمت إضافة الموظف بنجاح. يمكنك الآن تسجيل أول حركة له.')
            return redirect(url_for('employees.employee_card', i=e.id))
    # صفحة الموظفين تشغيلية: لا يجوز لمرشح غير صالح أن يتحول إلى عرض أوسع.
    # البحث العام في كل المحافظات يظل محصورًا في الصفحة الرئيسية فقط.
    search_branch_ids = set(bs or [])
    raw_q = (request.args.get('q', '') or '').strip()
    invalid_q_filter = len(raw_q) > 120
    q = raw_q[:120]
    employee_filter= (request.args.get('employee_id', '') or '').strip()
    branch_filter = (request.args.get('branch_id', '') or '').strip()
    gov_filter = (request.args.get('governorate_id', '') or '').strip()
    scope_governorates = scope_governorates_for_user()

    scope_branches = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(
            Branch.id.in_(search_branch_ids) if search_branch_ids else False,
            Branch.is_active == True,
            Governorate.is_active == True,
        ).order_by(Branch.name).all()
    )
    allowed_search_branch_ids = {b.id for b in scope_branches}
    allowed_search_gov_ids = {b.governorate_id for b in scope_branches}
    invalid_gov_filter = bool(gov_filter) and (
        not gov_filter.isdigit() or int(gov_filter) not in allowed_search_gov_ids
    )
    scoped_branch_governorates = {b.id: b.governorate_id for b in scope_branches}
    invalid_branch_filter = bool(branch_filter) and (
        not branch_filter.isdigit()
        or int(branch_filter) not in allowed_search_branch_ids
        or (bool(gov_filter) and gov_filter.isdigit() and scoped_branch_governorates.get(int(branch_filter)) != int(gov_filter))
    )
    invalid_employee_filter = bool(employee_filter) and not employee_filter.isdigit()

    branches = list(scope_branches)
    rows = []

    if not (invalid_q_filter or invalid_gov_filter or invalid_branch_filter or invalid_employee_filter):
        selected_branch_ids = set(allowed_search_branch_ids)
        if gov_filter:
            selected_gov_id = int(gov_filter)
            branches = [b for b in branches if b.governorate_id == selected_gov_id]
            selected_branch_ids &= {b.id for b in branches}
        if branch_filter:
            requested_branch_id = int(branch_filter)
            # An allowed branch must also belong to the explicitly selected governorate.
            if gov_filter and requested_branch_id not in selected_branch_ids:
                selected_branch_ids = set()
            else:
                selected_branch_ids = {requested_branch_id}
                branches = [b for b in branches if b.id == requested_branch_id]

        if selected_branch_ids:
            query = Employee.query.filter(
                Employee.is_active == True,
                Employee.branch_id.in_(selected_branch_ids),
            )
            if q:
                query = query.filter(db.or_(
                    search_contains(Employee.full_name, q),
                    search_contains(Employee.job_code, q),
                    search_contains(Employee.job_title, q),
                ))
            candidates = query.order_by(Employee.full_name).all()
            rows = [
                e for e in candidates
                if (e.branch_id in selected_branch_ids or effective_branch_id_for_employee(e.id) in selected_branch_ids)
                and (not branch_filter or employee_is_effectively_in_branch(e, int(branch_filter)))
            ]

    # Keep filter dropdown options within the same authorized work scope. Invalid
    # explicit query parameters produce no rows instead of silently broadening results.
    govs = (
        Governorate.query.filter(
            Governorate.id.in_(allowed_search_gov_ids) if allowed_search_gov_ids else False,
            Governorate.is_active == True,
        ).order_by(Governorate.name).all()
    )
    if invalid_gov_filter:
        branches = []
    filter_error = bool(invalid_q_filter or invalid_gov_filter or invalid_branch_filter or invalid_employee_filter)
    if employee_filter.isdigit():
        eid = int(employee_filter)
        found_in_scope = any(e.id == eid for e in rows)
        rows = [e for e in rows if e.id == eid]
        if not found_in_scope:
            filter_error = True
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

    # حالة الحركة لكل موظف تُحسب مرة واحدة حتى تبقى قائمة الموظفين سريعة.
    today = date.today()
    status_map = {}
    if rows and can('view_reports'):
        row_ids = [e.id for e in rows]
        movement_candidates = (
            Movement.query.filter(Movement.employee_id.in_(row_ids), Movement.is_active == True)
            .order_by(Movement.from_date.desc().nullslast(), Movement.permission_date.desc().nullslast(), Movement.id.desc())
            .all()
        )
        movement_rows = [m for m in movement_candidates if can_view_movement(m)]
        by_employee = {}
        for m in movement_rows:
            by_employee.setdefault(m.employee_id, []).append(m)
        for e in rows:
            ms = by_employee.get(e.id, [])
            current = resolve_current_movement(ms, today)
            if current and current.movement_type == 'إجازة':
                status_map[e.id] = {'key': 'leave', 'label': 'إجازة', 'detail': current.leave_type or 'إجازة'}
            elif current and current.movement_type == 'انتداب' and current.to_date is not None:
                status_map[e.id] = {'key': 'assignment', 'label': 'منتدب إليه', 'detail': current.destination.name if current.destination else 'جهة الانتداب غير محددة'}
            elif current and current.movement_type == 'انتداب':
                status_map[e.id] = {'key': 'open-assignment', 'label': 'منتدب إليه · مفتوح', 'detail': current.destination.name if current.destination else 'جهة الانتداب غير محددة'}
            elif current and current.movement_type == 'إذن':
                status_map[e.id] = {'key': 'permission', 'label': 'إذن اليوم', 'detail': 'مسجل اليوم'}

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
        status_map=status_map,
        scope_governorates=scope_governorates,
        filter_error=filter_error,
    )


@bp.get('/employees/edit-data')
@req
def employee_edit_data():
    if not can('manage_employees'):
        abort(403)
    bs = bids()
    raw_q = (request.args.get('q', '') or '').strip()
    invalid_q_filter = len(raw_q) > 120
    q = raw_q[:120]
    rows = []
    if not invalid_q_filter and bs:
        query = (
            Employee.query.join(Branch, Employee.branch_id == Branch.id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(
                Employee.is_active == True,
                Branch.is_active == True,
                Governorate.is_active == True,
                Employee.branch_id.in_(bs),
            )
        )
        if q:
            query = query.filter(db.or_(
                search_contains(Employee.full_name, q),
                search_contains(Employee.job_code, q),
                search_contains(Employee.email, q),
            ))
        rows = query.order_by(Employee.full_name).all()
    return render_template('employee_edit_data.html', rows=rows, q=q, filter_error=invalid_q_filter)


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
        # Treat missing or malformed branch IDs as invalid form input rather
        # than letting int(...) raise an unhandled ValueError/KeyError (500).
        raw_branch_id = (request.form.get('branch_id') or '').strip()
        if not raw_branch_id.isdigit():
            flash('اختر فرعًا صحيحًا ضمن نطاق صلاحيتك.')
            return redirect(url_for('employees.employee_edit', i=i))
        bid = int(raw_branch_id)
        if not branch_ok(bid):
            abort(403)
        submitted_gid = (
            int(request.form.get('governorate_id', '0'))
            if request.form.get('governorate_id', '').isdigit()
            else 0
        )
        branch_obj = db.session.get(Branch, bid)
        if (
            not branch_obj
            or not branch_obj.is_active
            or not branch_obj.governorate
            or not branch_obj.governorate.is_active
            or branch_obj.governorate_id != submitted_gid
        ):
            flash('يجب اختيار فرع ومحافظة نشطين ومتطابقين ضمن نطاق صلاحيتك.')
            return redirect(url_for('employees.employee_edit', i=i))
        name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
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
        dup = Employee.query.filter(
            func.lower(Employee.email) == email, Employee.id != i,
        ).first()
        if dup:
            flash('البريد الإلكتروني مستخدم بالفعل لموظف آخر.')
            return redirect(url_for('employees.employee_edit', i=i))
        duplicate_code = Employee.query.filter(
            func.lower(func.trim(Employee.job_code)) == job_code.lower(),
            Employee.id != i,
        ).first()
        if duplicate_code:
            flash('كود شئون العاملين مستخدم بالفعل لموظف آخر.')
            return redirect(url_for('employees.employee_edit', i=i))
        if not _safe_parse_date(hire_date):
            flash('تاريخ التعيين مطلوب وبصيغة صحيحة.')
            return redirect(url_for('employees.employee_edit', i=i))
        # Validate a linked login's email before mutating either ORM object.
        # This keeps rejected form submissions free of partially staged changes.
        linked_user = db.session.get(User, e.user_id) if e.user_id else None
        if linked_user:
            other = User.query.filter(
                func.lower(User.email) == email, User.id != linked_user.id,
            ).first()
            if other:
                flash('البريد الإلكتروني مستخدم بالفعل لحساب آخر.')
                return redirect(url_for('employees.employee_edit', i=i))

        e.full_name = name
        e.email = email
        e.branch_id = bid
        e.job_title = job_title
        e.job_code = job_code
        if linked_user:
            linked_user.email = email
            linked_user.full_name = name
            linked_user.job_title = job_title
            linked_user.job_code = job_code
        e.hire_date = _safe_parse_date(hire_date)
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
    resignation_date = _safe_parse_date(raw_date)
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
    if not e:
        abort(404)
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
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
        Employee.is_active == False,
        Employee.resignation_date.isnot(None) | Employee.deleted_at.isnot(None),
    )
    # This endpoint is operational-scope-bound. An empty scope means no data,
    # never an unfiltered query (which would expose every governorate's records).
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
    if e.is_active:
        flash('الموظف مفعّل بالفعل ولا يحتاج إلى إعادة تعيين.')
        return redirect(url_for('employees.employee_card', i=e.id))
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
    raw_date = (request.form.get('rehire_date') or '').strip()
    rehire_date = _safe_parse_date(raw_date)
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
    can_read_movement_details = can('view_reports')
    # فتح البطاقة يحتاج صلاحية دليل الموظفين أو التقارير على الأقل؛ وجود
    # نطاق فرعي وحده لا يمنح إذن قراءة بيانات الموظف.
    if not (can('manage_employees') or can_read_movement_details):
        abort(403)
    # البحث في الرئيسية عالمي ومتعمد أن يتجاوز محافظة العمل، لكن فتح البطاقة
    # نفسها يظل خاضعًا للنطاق التشغيلي. مسؤول التطبيق يستطيع فتح أي بطاقة.
    if 'مسؤول التطبيق' not in roles(me()) and not branch_ok(e.branch_id):
        abort(403)
    if not e.is_active and (not (can('manage_employees') and can_manage_employee(e))):
        abort(403)

    today = date.today()
    if can_read_movement_details:
        all_active_movements = (
            Movement.query.filter_by(employee_id=i, is_active=True)
            .order_by(
                Movement.from_date.desc().nullslast(),
                Movement.permission_date.desc().nullslast(),
                Movement.id.desc(),
            )
            .all()
        )
        ms = [mv for mv in all_active_movements if can_view_movement(mv)]
    else:
        # مستخدم إدارة بيانات الموظفين دون صلاحية التقارير يرى البيانات الأساسية
        # فقط؛ لا نحسب الحالة الحالية من حركات لا يحق له قراءتها.
        ms = []
    last = {k: next((m for m in ms if m.movement_type == k), None) for k in MOVEMENT_TYPES}
    current_assignment = current_assignment_for_employee(e.id, today) if can_read_movement_details else None
    current_branch = (
        current_assignment.destination
        if current_assignment and current_assignment.destination
        else e.branch
    )

    # The card has its own deterministic current-state calculation so it remains
    # correct even when opened directly, outside the Home dashboard.
    current_status = {'key': 'none', 'label': 'لا توجد حركة حالية', 'detail': 'لا توجد حركة مسجلة الآن', 'movement': None, 'until': None}
    current = resolve_current_movement(ms, today) if can_read_movement_details else None
    if current and current.movement_type == 'إجازة':
        current_status = {'key': 'leave', 'label': 'إجازة', 'detail': current.leave_type or 'إجازة', 'movement': current, 'until': current.to_date}
    elif current and current.movement_type == 'انتداب' and current.to_date is not None:
        current_status = {'key': 'assignment', 'label': 'منتدب إليه', 'detail': current.destination.name if current.destination else 'جهة الانتداب غير محددة', 'movement': current, 'until': current.to_date}
    elif current and current.movement_type == 'انتداب':
        current_status = {'key': 'open-assignment', 'label': 'منتدب إليه · مفتوح', 'detail': current.destination.name if current.destination else 'جهة الانتداب غير محددة', 'movement': current, 'until': None}
    elif current and current.movement_type == 'إذن':
        current_status = {'key': 'permission', 'label': 'إذن اليوم', 'detail': 'مسجل اليوم', 'movement': current, 'until': today}

    return render_template(
        'employee.html',
        e=e,
        ms=ms,
        last=last,
        current_assignment=current_assignment,
        current_branch=current_branch,
        current_status=current_status,
        today=today,
    )

