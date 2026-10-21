"""Employee records, resignation/reactivation and role conversion."""

from datetime import date, datetime

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for
from sqlalchemy import func, select
from sqlalchemy.orm import aliased

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
    scope_governorates_for_user,
)
from ..assignments import (
    current_assignment_for_employee,
    latest_assignment_summaries,
    resolve_current_movement,
    organizational_entry_for_employee,
    entry_responsible_names_by_branch,
    entry_responsible_label,
)
from ..constants import MOVEMENT_TYPES
from ..extensions import db
from ..form_state import form_values_from_request
from ..pagination import safe_page_number
from ..movement_state import assignment_open_filter
from ..services.account_security import invalidate_user_workflows
from ..services.identity_locks import lock_employee_identity_writes
from ..models import (
    Branch,
    Employee,
    EmployeeNameAlias,
    TicketEmployeeCodeAlias,
    GovernorateNameAlias,
    BranchNameAlias,
    Governorate,
    Movement,
    SupervisorEntry,
    User,
    UserBranch,
    UserRole,
)
from ..validation import parse_date, valid_email
from ..search import normalize_search_text
from ..services.entity_matching import (
    conflicting_employee_code, employee_search_filter, normalize_alias_key,
    rank_scoped_employee_suggestions,
)
from ..services.entity_integrity import employee_name_conflict
from ..services.ticket_matching import job_code_lookup_variants
from sqlalchemy.exc import IntegrityError

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
    if eid and (not eid.isdigit() or not db.session.get(Employee, int(eid))):
        flash('تعذر العثور على سجل الموظف؛ أعد البحث من الرئيسية.')
        return redirect('/#entry-directory')
    flash('تكليف مسؤول إدخال الفروع لا يُدار كدور رسمي. استخدم مركز التكليفات في الرئيسية.')
    return redirect('/#entry-directory')


@bp.get('/employee-search')
@req
def employee_search():
    """Global employee-directory search for authenticated application users.

    Employee profile data is shared across all application roles by policy.
    Movement histories and mutation actions remain permission-gated separately.
    """
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
    scoped_query = query
    if normalized_q:
        query = query.filter(employee_search_filter(q, include_contacts=True, include_branch=True))
    rows = query.order_by(Employee.full_name).limit(20).all()
    suggested_ids = set()
    suggested_reasons = {}
    if normalized_q and not rows and len(normalized_q) >= 3:
        # Approximate matches are suggestions only; the UI labels them and the
        # user must select the intended employee explicitly.
        pool = scoped_query.order_by(Employee.full_name).limit(2500).all()
        ranked = rank_scoped_employee_suggestions(q, pool, limit=8)
        rows = [item['employee'] for item in ranked]
        suggested_ids = {item['employee'].id for item in ranked}

    # Resolve branch contact and the latest assignment summary in separate batched
    # read-only queries. Full history remains available on the employee profile.
    entry_names_by_branch = entry_responsible_names_by_branch({e.branch_id for e in rows if e.branch_id})
    latest_by_employee = latest_assignment_summaries({e.id for e in rows})
    results = [
        {
            'id': e.id,
            'name': e.full_name,
            # job_code is the legacy personnel-code field; employee_code is the
            # equivalent newer field. Expose one canonical code to the UI.
            'code': e.employee_code or e.job_code or '',
            'job_title': e.job_title or '',
            'branch': e.branch.name if e.branch else '',
            'branch_code': e.branch.code if e.branch else '',
            'governorate': e.branch.governorate.name if e.branch and e.branch.governorate else '',
            'hire_date': e.hire_date.strftime('%d/%m/%Y') if e.hire_date else '',
            'rehire_date': e.rehire_date.strftime('%d/%m/%Y') if e.rehire_date else '',
            'resignation_date': e.resignation_date.strftime('%d/%m/%Y') if e.resignation_date else '',
            'employment_status': (
                'على رأس العمل' if e.is_active and e.rehire_date and (not e.resignation_date or e.rehire_date >= e.resignation_date)
                else 'مستقيل' if e.resignation_date
                else 'على رأس العمل' if e.is_active
                else 'غير نشط'
            ),
            'email': e.email or '',
            'company_phone': e.company_phone or '',
            'personal_phone': e.personal_phone or '',
            'entry_responsible': entry_responsible_label(entry_names_by_branch.get(e.branch_id, [])),
            'entry_responsible_names': entry_names_by_branch.get(e.branch_id, []),
            'entry_responsible_status': (
                'conflict' if len(entry_names_by_branch.get(e.branch_id, [])) > 1
                else 'assigned' if entry_names_by_branch.get(e.branch_id, [])
                else 'unassigned'
            ),
            'last_assignment': latest_by_employee.get(e.id, {}).get('text', ''),
            'last_assignment_governorate': latest_by_employee.get(e.id, {}).get('governorate', ''),
            'match_kind': 'approximate' if e.id in suggested_ids else 'normal',
            'match_reasons': suggested_reasons.get(e.id, []),
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
    form_values = form_values_from_request(request.form) if request.method == 'POST' else {}
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
            # Share the same PostgreSQL identity gate as Excel, account-linked
            # employee writes, and assistant-managed changes. Lock the selected
            # branch before any Employee row, matching Excel's branch->employee
            # row-lock order and avoiding a cross-path deadlock.
            lock_employee_identity_writes(db.session)
            branch_obj = (
                Branch.query.filter_by(id=bid).populate_existing().with_for_update().one_or_none()
            )
            if (
                not branch_obj or not branch_obj.is_active or not branch_obj.governorate
                or not branch_obj.governorate.is_active or branch_obj.governorate_id != submitted_gid
                or not can('manage_employees') or not branch_ok(bid)
            ):
                flash('تغيّرت حالة الفرع أو نطاق الصلاحية أثناء التسجيل؛ أعد تحميل الصفحة قبل الحفظ.')
                return redirect(url_for('employees.employees'))
            # Email and HR code are compared case-insensitively across active and
            # historical employees; a resigned record must not permit a duplicate.
            existing_email_rows = Employee.query.filter(
                Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == email,
            ).populate_existing().with_for_update().all()
            if len(existing_email_rows) > 1:
                flash('يوجد أكثر من سجل موظف بالبريد نفسه بعد تطبيع الأحرف؛ لم يتم الاستعادة أو الإضافة لتجنب اختيار سجل خطأ.')
                return redirect(url_for('employees.employees'))
            existing = existing_email_rows[0] if existing_email_rows else None
            name_alias_conflict = employee_name_conflict(name, bid, exclude_employee_id=existing.id if existing else None)
            code_conflict = conflicting_employee_code(job_code, exclude_employee_id=existing.id if existing else None)
            if name_alias_conflict:
                flash('الاسم يطابق صيغة بديلة مؤكدة لموظف آخر؛ راجع سجل المطابقة قبل الإضافة.')
            elif code_conflict:
                flash('كود شئون العاملين أو أحد صِيَغه الرقمية مستخدم بالفعل لموظف آخر.')
            elif existing:
                if existing.is_active:
                    flash('البريد الإلكتروني مستخدم بالفعل لموظف آخر.')
                elif existing.resignation_date is not None:
                    flash(
                        'الموظف مسجل كمستقيل. أعد تفعيله أولًا من «الموظفون المستقيلون» بتاريخ إعادة التعيين، ثم حدّث بياناته.',
                    )
                    return redirect(url_for('employees.resigned_employees'))
                else:
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
                    try:
                        db.session.commit()
                    except IntegrityError:
                        db.session.rollback()
                        flash('تعذر استعادة الموظف لأن بيانات الهوية تعارضت مع سجل قائم؛ لم يتم اعتماد أي تغيير.')
                        return redirect(url_for('employees.employees'))
                    flash('تمت استعادة الموظف السابق وتحديث بياناته، مع الاحتفاظ بكل تاريخه وحركاته.')
                    return redirect(url_for('employees.employee_card', i=existing.id))
            else:
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
                try:
                    db.session.flush()
                    log('ADD', 'Employee', e.id, e.full_name)
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    flash('تعذر إضافة الموظف بسبب تعارض في البريد أو الكود أو قيد قاعدة البيانات؛ لم يتم إنشاء سجل جزئي.')
                    return redirect(url_for('employees.employees'))
                flash('تمت إضافة الموظف بنجاح. يمكنك الآن تسجيل أول حركة له.')
                return redirect(url_for('employees.employee_card', i=e.id))
    # القراءة في دليل الموظفين عامة عبر المحافظات لكل المستخدمين المسجلين.
    # المتغير bs أعلاه يظل نطاق العمل فقط، ويُستخدم في الإضافة/التعديل لا في تقييد العرض.
    search_branch_ids = {
        branch.id for branch in Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True).all()
    }
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
    employee_page_size = 100
    employee_page = 1
    employee_page_count = 1
    employee_query_total = 0
    employee_server_paginated = False

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
            query = (
                Employee.query
                .join(Branch, Employee.branch_id == Branch.id)
                .join(Governorate, Governorate.id == Branch.governorate_id)
                .filter(
                    Employee.is_active == True,
                    Employee.branch_id.in_(selected_branch_ids),
                )
            )
            if employee_filter:
                # Exact profile lookup must be a database predicate. Previously
                # this path loaded every employee in the selected scope and only
                # then narrowed the result in Python.
                query = query.filter(Employee.id == int(employee_filter))
            if branch_filter:
                # Mirror employee_is_effectively_in_branch() in SQL. Its old
                # per-row movement lookup caused an N+1 query pattern and made
                # branch-filtered lists bypass pagination entirely.
                today_for_scope = date.today()
                latest_current_assignment_id = (
                    select(func.max(Movement.id))
                    .where(
                        Movement.employee_id == Employee.id,
                        Movement.is_active == True,
                        Movement.movement_type == 'انتداب',
                        assignment_open_filter(Movement),
                        Movement.from_date.is_not(None),
                        Movement.from_date <= today_for_scope,
                        db.or_(Movement.to_date.is_(None), Movement.to_date >= today_for_scope),
                    )
                    .correlate(Employee)
                    .scalar_subquery()
                )
                current_assignment_row = aliased(Movement)
                query = query.outerjoin(
                    current_assignment_row,
                    current_assignment_row.id == latest_current_assignment_id,
                ).filter(
                    db.or_(
                        current_assignment_row.id.is_(None),
                        current_assignment_row.destination_branch_id.is_(None),
                        current_assignment_row.destination_branch_id == int(branch_filter),
                    )
                )
            if q:
                query = query.filter(employee_search_filter(q, include_job_title=True, include_contacts=True, include_branch=True))
            # Exact profile lookup stays a one-record query; every directory list,
            # including governorate/branch-filtered views, is paginated by SQL.
            employee_server_paginated = not employee_filter
            if employee_server_paginated:
                employee_query_total = query.count()
                employee_page_count = max(1, (employee_query_total + employee_page_size - 1) // employee_page_size)
                raw_page = (request.args.get('page') or '1').strip()
                employee_page = safe_page_number(raw_page, employee_page_count)
                candidates = query.order_by(Employee.full_name, Employee.id).limit(employee_page_size).offset(
                    (employee_page - 1) * employee_page_size
                ).all()
            else:
                candidates = query.order_by(Employee.full_name, Employee.id).all()
            rows = candidates

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

    # When an exact/substring query is empty, show clearly labelled, scoped
    # suggestions rather than silently treating a fuzzy candidate as a match.
    approximate_employee_ids = set()
    approximate_employee_reasons = {}
    if q and not rows and not employee_filter and not filter_error:
        employee_server_paginated = False
        employee_page = 1
        employee_page_count = 1
        scoped_ids = {branch.id for branch in branches if branch.is_active and branch.governorate and branch.governorate.is_active}
        if scoped_ids:
            fallback_query = (
                Employee.query.join(Branch, Employee.branch_id == Branch.id)
                .join(Governorate, Governorate.id == Branch.governorate_id)
                .filter(
                    Employee.is_active == True,
                    Branch.is_active == True,
                    Governorate.is_active == True,
                    Employee.branch_id.in_(scoped_ids),
                )
            )
            pool = fallback_query.order_by(Employee.full_name).limit(2500).all()
            ranked = rank_scoped_employee_suggestions(q, pool, limit=8)
            rows = [item['employee'] for item in ranked]
            approximate_employee_ids = {item['employee'].id for item in ranked}
            approximate_employee_reasons = {
                item['employee'].id: '، '.join(item.get('match_reasons') or [])
                for item in ranked
                if item.get('match_reasons')
            }

    # Alternative identity spellings are included in client-side filtering so
    # the browser and server share the same local matching vocabulary.
    employee_alias_text = {}
    employee_code_alias_text = {}
    branch_alias_text = {}
    governorate_alias_text = {}
    row_ids_for_alias = [employee.id for employee in rows]
    if row_ids_for_alias:
        for alias in EmployeeNameAlias.query.filter(EmployeeNameAlias.employee_id.in_(row_ids_for_alias)).all():
            employee_alias_text.setdefault(alias.employee_id, []).append(alias.alias_text)
        for alias in TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.employee_id.in_(row_ids_for_alias)).all():
            employee_code_alias_text.setdefault(alias.employee_id, []).append(alias.alias_text)
    visible_branch_ids = {employee.branch_id for employee in rows if employee.branch_id}
    if visible_branch_ids:
        for alias in BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(visible_branch_ids)).all():
            branch_alias_text.setdefault(alias.branch_id, []).append(alias.alias_text)
    visible_gov_ids = {branch.governorate_id for branch in branches if branch.governorate_id}
    if visible_gov_ids:
        for alias in GovernorateNameAlias.query.filter(GovernorateNameAlias.governorate_id.in_(visible_gov_ids)).all():
            governorate_alias_text.setdefault(alias.governorate_id, []).append(alias.alias_text)

    # اسم مسؤول الإدخال الأول يُحدد وفق الفرع المسجل للموظف، لا وفق تطابق
    # رقم الموظف مع رقم الشخص المكلف بالإدخال. إظهار التضارب أفضل من اختيار اسم خاطئ.
    entry_map = {}
    if rows:
        names_by_branch = entry_responsible_names_by_branch({e.branch_id for e in rows if e.branch_id})
        for employee in rows:
            entry_map[employee.id] = entry_responsible_label(names_by_branch.get(employee.branch_id, []))

    # مرشحات البحث للقراءة تشمل كل المحافظات؛ لا تغيّر محافظة العمل ولا تمنح حق التعديل.
    filter_govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
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
    page_result_count = len(rows)
    result_total = employee_query_total if employee_server_paginated else len(rows)
    page_links = []
    if employee_server_paginated and employee_page_count > 1:
        start_page = max(1, employee_page - 2)
        end_page = min(employee_page_count, start_page + 4)
        start_page = max(1, end_page - 4)
        for page_number in range(start_page, end_page + 1):
            query_args = request.args.to_dict()
            query_args['page'] = str(page_number)
            page_links.append({
                'number': page_number,
                'url': url_for('employees.employees', **query_args),
            })
    previous_page_url = None
    next_page_url = None
    if employee_server_paginated and employee_page > 1:
        query_args = request.args.to_dict()
        query_args['page'] = str(employee_page - 1)
        previous_page_url = url_for('employees.employees', **query_args)
    if employee_server_paginated and employee_page < employee_page_count:
        query_args = request.args.to_dict()
        query_args['page'] = str(employee_page + 1)
        next_page_url = url_for('employees.employees', **query_args)

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
        total_rows=result_total,
        page_result_count=page_result_count,
        employee_server_paginated=employee_server_paginated,
        employee_page=employee_page,
        employee_page_size=employee_page_size,
        employee_page_count=employee_page_count,
        employee_page_links=page_links,
        employee_previous_page_url=previous_page_url,
        employee_next_page_url=next_page_url,
        status_map=status_map,
        scope_governorates=scope_governorates,
        filter_error=filter_error,
        approximate_employee_ids=approximate_employee_ids,
        approximate_employee_reasons=approximate_employee_reasons,
        employee_alias_text=employee_alias_text,
        employee_code_alias_text=employee_code_alias_text,
        branch_alias_text=branch_alias_text,
        governorate_alias_text=governorate_alias_text,
        grouped_branch_count=sum(len(group['branches']) for group in grouped_employees),
        form_values=form_values,
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
        scoped_query = query
        if q:
            query = query.filter(employee_search_filter(q, include_contacts=True, include_branch=True))
        rows = query.order_by(Employee.full_name).limit(200).all()
        approximate_employee_ids = set()
        if q and not rows and not invalid_q_filter:
            pool = scoped_query.order_by(Employee.full_name).limit(2500).all()
            ranked = rank_scoped_employee_suggestions(q, pool, limit=8)
            rows = [item['employee'] for item in ranked]
            approximate_employee_ids = {item['employee'].id for item in ranked}
            approximate_employee_reasons = {
                item['employee'].id: '، '.join(item.get('match_reasons') or [])
                for item in ranked
                if item.get('match_reasons')
            }
    else:
        approximate_employee_ids = set()
        approximate_employee_reasons = {}
    return render_template(
        'employee_edit_data.html', rows=rows, q=q, filter_error=invalid_q_filter,
        approximate_employee_ids=approximate_employee_ids,
        approximate_employee_reasons=approximate_employee_reasons,
    )


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
    form_values = form_values_from_request(request.form) if request.method == 'POST' else {}

    def render_edit_form(values=None):
        return render_template(
            'employee_edit.html',
            e=e,
            employee_name_aliases=EmployeeNameAlias.query.filter_by(employee_id=e.id).order_by(EmployeeNameAlias.alias_text).all(),
            employee_code_aliases=TicketEmployeeCodeAlias.query.filter_by(employee_id=e.id).order_by(TicketEmployeeCodeAlias.alias_text).all(),
            bs=Branch.query.filter(Branch.id.in_(bids()), Branch.is_active == True).all(),
            govs=(
                Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
                .order_by(Governorate.name)
                .all()
            ),
            form_values=values or {},
        )

    def retry_edit(message):
        flash(message)
        return render_edit_form(form_values_from_request(request.form))

    if request.method == 'POST':
        # Parse the submitted branch before taking row locks. All employee
        # writers use the identity gate; lock branch first, then employee, to
        # match the import workflow's stable catalogue->employee order.
        raw_branch_id = (request.form.get('branch_id') or '').strip()
        if not raw_branch_id.isdigit():
            return retry_edit('اختر فرعًا صحيحًا ضمن نطاق صلاحيتك.')
        bid = int(raw_branch_id)
        lock_employee_identity_writes(db.session)
        branch_obj = (
            Branch.query.filter_by(id=bid).populate_existing().with_for_update().one_or_none()
        )
        db.session.refresh(e, with_for_update=True)
        if e.deleted_at is not None or not can_manage_employee(e) or not can('manage_employees'):
            abort(403)
        if not branch_ok(bid):
            abort(403)
        submitted_gid = (
            int(request.form.get('governorate_id', '0'))
            if request.form.get('governorate_id', '').isdigit()
            else 0
        )
        if (
            not branch_obj
            or not branch_obj.is_active
            or not branch_obj.governorate
            or not branch_obj.governorate.is_active
            or branch_obj.governorate_id != submitted_gid
        ):
            return retry_edit('يجب اختيار فرع ومحافظة نشطين ومتطابقين ضمن نطاق صلاحيتك.')
        name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip().lower()
        job_title = request.form.get('job_title', '').strip()
        job_code = request.form.get('job_code', '').strip()
        hire_date = request.form.get('hire_date', '').strip()
        company_phone = request.form.get('company_phone', '').strip()
        personal_phone = request.form.get('personal_phone', '').strip()
        if not all([name, email, job_title, job_code, hire_date]):
            return retry_edit('اسم الموظف والبريد والوظيفة والكود الوظيفي وتاريخ التعيين بيانات مطلوبة.')
        # The shared lock was acquired before reloading the target above.
        name_alias_conflict = employee_name_conflict(name, bid, exclude_employee_id=e.id)
        if name_alias_conflict:
            return retry_edit('الاسم يطابق صيغة بديلة مؤكدة لموظف آخر؛ لم يتم التعديل.')
        code_conflict = conflicting_employee_code(job_code, exclude_employee_id=e.id)
        if code_conflict:
            return retry_edit('كود شئون العاملين أو أحد صِيَغه الرقمية مستخدم بالفعل لموظف آخر.')
        if not valid_email(email):
            return retry_edit('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.')
        dup = Employee.query.filter(
            func.lower(Employee.email) == email, Employee.id != i,
        ).first()
        if dup:
            return retry_edit('البريد الإلكتروني مستخدم بالفعل لموظف آخر.')
        if not _safe_parse_date(hire_date):
            return retry_edit('تاريخ التعيين مطلوب وبصيغة صحيحة.')
        # Validate a linked login's email before mutating either ORM object.
        # This keeps rejected form submissions free of partially staged changes.
        linked_user = db.session.get(User, e.user_id) if e.user_id else None
        if linked_user:
            other = User.query.filter(
                func.lower(User.email) == email, User.id != linked_user.id,
            ).first()
            if other:
                return retry_edit('البريد الإلكتروني مستخدم بالفعل لحساب آخر.')

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
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash('تعذر حفظ تعديل الموظف بسبب تعارض في الهوية أو البريد؛ لم يتم اعتماد التغييرات.')
            return redirect(url_for('employees.employee_edit', i=i))
        flash('تم تعديل الموظف.')
        return redirect(url_for('employees.employees'))
    return render_edit_form(form_values)


@bp.post('/employees/<int:i>/aliases')
@req
@only('مسؤول التطبيق')
def employee_alias_add(i):
    """Explicitly confirm a global alternate employee name or job code."""
    employee = db.session.get(Employee, i)
    if not employee or not employee.is_active or employee.deleted_at is not None:
        abort(404)
    kind = (request.form.get('alias_kind') or '').strip()
    alias_text = (request.form.get('alias_text') or '').strip()[:200]
    normalized = normalize_alias_key(alias_text, 'code' if kind == 'employee_code' else 'name')
    if kind not in {'employee_name', 'employee_code'} or len(normalized) < (4 if kind == 'employee_code' else 2):
        flash('اكتب صيغة بديلة واضحة؛ الاسم حرفان على الأقل والكود أربعة أحرف/أرقام على الأقل.')
        return redirect(url_for('employees.employee_edit', i=i))

    try:
        # Name/code aliases participate in the same uniqueness rules as the
        # canonical employee identity and Excel imports. Refresh the owner after
        # the transaction lock so a stale edit form cannot attach an alias to a
        # changed/deactivated employee silently.
        lock_employee_identity_writes(db.session)
        db.session.refresh(employee, with_for_update=True)
        if not employee.is_active or employee.deleted_at is not None:
            db.session.rollback()
            flash('تغيّرت حالة الموظف أثناء المراجعة؛ أعد فتح السجل قبل إضافة صيغة بديلة.')
            return redirect(url_for('employees.employee_edit', i=i))
        if kind == 'employee_name':
            official_key = normalize_alias_key(employee.full_name)
            if normalized == official_key:
                flash('هذه الصيغة تطابق الاسم الرسمي بالفعل.')
                return redirect(url_for('employees.employee_edit', i=i))
            # An alias must not shadow another employee's canonical name.
            for other in Employee.query.filter(Employee.id != employee.id).all():
                if normalize_alias_key(other.full_name) == normalized:
                    flash('لا يمكن حفظ هذه الصيغة؛ فهي تطابق الاسم الرسمي لموظف آخر.')
                    return redirect(url_for('employees.employee_edit', i=i))
            existing = EmployeeNameAlias.query.filter_by(normalized_alias=normalized).first()
            if existing:
                flash('صيغة الاسم محفوظة بالفعل لهذا الموظف.' if existing.employee_id == employee.id else 'صيغة الاسم مرتبطة بموظف آخر؛ لم يتم تغيير الربط.')
                return redirect(url_for('employees.employee_edit', i=i))
            row = EmployeeNameAlias(employee_id=employee.id, alias_text=alias_text, normalized_alias=normalized, created_by=me().id)
            db.session.add(row)
            db.session.flush()
            log('ADD', 'EmployeeNameAlias', row.id, 'حفظ صيغة اسم بديلة مؤكدة')
        else:
            variants = job_code_lookup_variants(alias_text)
            official_variants = job_code_lookup_variants(employee.job_code or '')
            if variants & official_variants:
                flash('هذه الصيغة يغطيها تطبيع الكود الحالي بالفعل؛ لا حاجة لحفظ بديل.')
                return redirect(url_for('employees.employee_edit', i=i))
            code_conflict = conflicting_employee_code(alias_text, exclude_employee_id=employee.id)
            if code_conflict:
                flash('لا يمكن حفظ الكود البديل؛ فقد يشير إلى كود رسمي أو بديل لموظف آخر.')
                return redirect(url_for('employees.employee_edit', i=i))
            existing_rows = TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.normalized_alias.in_(variants)).all()
            for existing in existing_rows:
                if existing.employee_id != employee.id:
                    flash('الكود البديل مرتبط بموظف آخر أو قد يسبب التباسًا.')
                    return redirect(url_for('employees.employee_edit', i=i))
            if existing_rows:
                flash('صيغة الكود البديلة محفوظة بالفعل.')
                return redirect(url_for('employees.employee_edit', i=i))
            row = TicketEmployeeCodeAlias(employee_id=employee.id, alias_text=alias_text, normalized_alias=normalized, created_by=me().id)
            db.session.add(row)
            db.session.flush()
            log('ADD', 'TicketEmployeeCodeAlias', row.id, 'حفظ صيغة كود بديلة مؤكدة من إدارة الموظف')
        db.session.commit()
        flash('تم حفظ الصيغة البديلة، وستُستخدم في البحث داخل الصفحات المصرح بها.')
    except IntegrityError:
        db.session.rollback()
        flash('لم تُحفظ الصيغة لأن هناك تعارضًا متزامنًا أو صيغة مشابهة محفوظة بالفعل.')
    return redirect(url_for('employees.employee_edit', i=i))


@bp.route('/employees/<int:i>/convert-role', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق')
def employee_convert_role(i):
    # Compatibility endpoint for old bookmarks: the only writable interface for
    # branch-entry assignments is the homepage operational workspace.
    e = db.session.get(Employee, i)
    if not e or not e.is_active:
        abort(404)
    flash('إدارة تكليف مسؤول إدخال الفروع تتم من الرئيسية، ولا تغيّر صفة الموظف أو دور تسجيل الدخول.')
    return redirect('/#entry-directory')


@bp.post('/employees/<int:i>/resign')
@req
def employee_resign(i):
    e = db.session.get(Employee, i)
    if not e or not can_manage_employee(e) or (not can('manage_employees')):
        abort(403)
    # Lifecycle changes affect whether the identity may be selected by another
    # workflow, so they serialize with create/edit/import/restore operations.
    lock_employee_identity_writes(db.session)
    db.session.refresh(e, with_for_update=True)
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
    if not e.is_active or e.deleted_at is not None:
        flash('الموظف موجود بالفعل ضمن الموظفين المستقيلين أو غير نشط.')
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
            invalidate_user_workflows(linked_user.id)
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
    lock_employee_identity_writes(db.session)
    db.session.refresh(e, with_for_update=True)
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
    if e.deleted_at is not None:
        flash('الموظف مخفي إداريًا بالفعل؛ لم يتم تكرار العملية.')
        return redirect(url_for('employees.employees'))
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
    if not (can('view_reports') or can('manage_employees')):
        abort(403)
    # سجل الموظفين المستقيلين للقراءة العامة. إعادة التفعيل فقط تبقى مقيدة بمحافظة العمل المختارة.
    q = Employee.query.filter(
        Employee.is_active == False,
        Employee.resignation_date.isnot(None) | Employee.deleted_at.isnot(None),
    )
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
    lock_employee_identity_writes(db.session)
    db.session.refresh(e, with_for_update=True)
    if e.resignation_date is None and e.deleted_at is None:
        abort(404)
    if not can_manage_employee(e) or not can('manage_employees'):
        abort(403)
    if e.is_active and e.deleted_at is None:
        flash('الموظف مفعّل بالفعل ولا يحتاج إلى إعادة تعيين.')
        return redirect(url_for('employees.employee_card', i=e.id))
    raw_date = (request.form.get('rehire_date') or '').strip()
    rehire_date = _safe_parse_date(raw_date)
    if not rehire_date:
        flash('يجب تحديد تاريخ إعادة التعيين.')
        return redirect(url_for('employees.resigned_employees'))
    if e.resignation_date and rehire_date < e.resignation_date:
        flash('تاريخ إعادة التعيين يجب أن يكون في أو بعد تاريخ الاستقالة.')
        return redirect(url_for('employees.resigned_employees'))

    # Re-activation makes an old identity eligible for selection again. Verify
    # code variants, aliases, name/email and the current branch before changing it.
    branch = Branch.query.filter_by(id=e.branch_id).populate_existing().one_or_none()
    parent = (
        Governorate.query.filter_by(id=branch.governorate_id).populate_existing().one_or_none()
        if branch else None
    )
    if not branch or not branch.is_active or not parent or not parent.is_active:
        flash('لا يمكن إعادة تفعيل الموظف لأن فرعه أو محافظته غير نشطين؛ صحح التعيين أولًا.')
        return redirect(url_for('employees.resigned_employees'))
    if employee_name_conflict(e.full_name, e.branch_id, exclude_employee_id=e.id):
        flash('لا يمكن إعادة التفعيل لأن الاسم يتعارض مع سجل أو صيغة بديلة لموظف آخر.')
        return redirect(url_for('employees.resigned_employees'))
    for code_value in (e.employee_code, e.job_code):
        if code_value and conflicting_employee_code(code_value, exclude_employee_id=e.id):
            flash('لا يمكن إعادة التفعيل لأن الكود أو إحدى صِيَغه البديلة مستخدمة لموظف آخر.')
            return redirect(url_for('employees.resigned_employees'))
    email = (e.email or '').strip().lower()
    if email and Employee.query.filter(
        Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == email,
        Employee.id != e.id,
    ).populate_existing().first():
        flash('لا يمكن إعادة التفعيل لأن البريد الإلكتروني مستخدم لموظف آخر.')
        return redirect(url_for('employees.resigned_employees'))
    if email and User.query.filter(
        User.email.isnot(None), func.lower(func.trim(User.email)) == email,
        User.id != (e.user_id or -1),
    ).populate_existing().first():
        flash('لا يمكن إعادة التفعيل لأن البريد الإلكتروني مرتبط بحساب آخر.')
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
    # All official authenticated roles share read access to movement history across
    # governorates. Mutation actions still use separate role and work-scope checks.
    can_read_movement_details = can('view_reports')

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
        # المستخدم الذي لا يملك صلاحية التقارير يرى بيانات الموظف العامة فقط؛
        # لا نحسب الحالة الحالية من حركات لا يحق له قراءتها.
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

