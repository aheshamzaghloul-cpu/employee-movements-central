"""User accounts, roles, permissions and entry management."""

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from ..access import (
    actual_roles,
    allowed_create_user,
    allowed_target_user,
    bids,
    can,
    gids,
    has_role,
    log,
    me,
    only,
    req,
    roles,
    user_branch_ids,
    user_gov_ids,
    user_permissions,
)
from ..assignments import supervisor_for_entry, supervisor_for_governorate, sync_role_accounts
from ..constants import GRANTABLE_BY_SUPERVISOR, LOGIN_ROLES, PERMISSIONS, ROLE_DEFAULT_PERMISSIONS, ROLES
from ..extensions import db
from ..models import (
    Branch,
    Employee,
    EntryAssignment,
    EntryAssignmentBranch,
    Governorate,
    Movement,
    RoleAccount,
    SupervisorEntry,
    User,
    UserBranch,
    UserGovernorate,
    UserPermission,
    UserRole,
)
from ..validation import parse_date, valid_email, valid_password

bp = Blueprint('users', __name__)


@bp.route('/users', methods=['GET', 'POST'])
@req
def users():
    if not can('manage_users') or not has_role('مسؤول التطبيق', 'مشرف محافظة'):
        abort(403)
    u = me()
    visible = (
        User.query.order_by(User.id.desc()).all()
        if 'مسؤول التطبيق' in roles(u)
        else [
            x
            for x in User.query.order_by(User.id.desc()).all()
            if x.id == u.id or allowed_target_user(x)
        ]
    )
    if request.method == 'POST':
        selected_roles = (
            [r for r in request.form.getlist('roles') if r in LOGIN_ROLES]
            or ([request.form.get('role')] if request.form.get('role') in LOGIN_ROLES else [])
        )
        username = request.form.get('username', '').strip()
        full = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        job_title = request.form.get('job_title', '').strip()
        job_code = request.form.get('job_code', '').strip()
        password = request.form.get('password', '')
        if not selected_roles or any((not allowed_create_user(r) for r in selected_roles)):
            abort(403)
        if (
            not username
            or not full
            or not email
            or not valid_email(email)
            or not job_title
            or not job_code
            or not valid_password(password)
            or User.query.filter_by(username=username).first()
            or User.query.filter_by(email=email).first()
        ):
            flash('جميع بيانات الحساب مطلوبة، واسم المستخدم فريد وكلمة المرور 8 أحرف على الأقل.')
        else:
            nu = User(
                username=username,
                full_name=full,
                email=email,
                job_title=job_title,
                job_code=job_code,
                password_hash=generate_password_hash(password),
            )
            db.session.add(nu)
            db.session.flush()
            for role in selected_roles:
                db.session.add(UserRole(user_id=nu.id, role=role))
            # صلاحيات الدور تضاف تلقائيًا عند إنشاء الحساب، ويمكن لمسؤول التطبيق تعديلها لاحقًا بالزيادة أو النقصان.
            selected_perms = {x for x in request.form.getlist('permissions') if x in PERMISSIONS}
            defaults = set()
            for r in selected_roles:
                defaults |= ROLE_DEFAULT_PERMISSIONS.get(r, set())
            if 'مسؤول التطبيق' not in roles(u):
                defaults &= GRANTABLE_BY_SUPERVISOR
                selected_perms &= GRANTABLE_BY_SUPERVISOR
            selected_perms |= defaults
            for perm in selected_perms:
                db.session.add(UserPermission(user_id=nu.id, permission=perm))
            if 'مشرف محافظة' in selected_roles:
                chosen = {int(x) for x in request.form.getlist('governorate_id') if x.isdigit()}
                allowed = (
                    set(gids())
                    if 'مسؤول التطبيق' not in roles(u)
                    else {g.id for g in Governorate.query.filter_by(is_active=True)}
                )
                chosen &= allowed
                if not chosen:
                    db.session.rollback()
                    flash('يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.')
                    return redirect('/users')
                for gid in chosen:
                    db.session.add(UserGovernorate(user_id=nu.id, governorate_id=gid))
            if 'المدخل الأول' in selected_roles and 'مشرف محافظة' not in selected_roles:
                chosen = (
                    {int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
                    & set(bids())
                )
                if not chosen:
                    db.session.rollback()
                    flash('يجب إسناد فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
                    return redirect('/users')
                for bid in chosen:
                    db.session.add(UserBranch(user_id=nu.id, branch_id=bid))
                # The employee's appointment branch is separate from the branches managed by the first-level user.
                appointment_raw = request.form.get('employee_branch_id', '').strip()
                appointment_bid = int(appointment_raw) if appointment_raw.isdigit() else 0
                appointment_branch = (
                    db.session.get(Branch, appointment_bid)
                    if appointment_bid
                    else None
                )
                if (
                    not appointment_branch
                    or not appointment_branch.is_active
                    or (
                        'مسؤول التطبيق' not in roles(u)
                        and appointment_branch.governorate_id not in set(gids())
                    )
                ):
                    db.session.rollback()
                    flash('يجب اختيار فرع تعيين تابع لمحافظة ضمن نطاقك.')
                    return redirect('/users')
                # Link first-level user to the responsible supervisor automatically.
                gid_values = {
                    db.session.get(Branch, bid).governorate_id
                    for bid in chosen
                    if db.session.get(Branch, bid)
                }
                requested_sup = request.form.get('supervisor_id', '').strip()
                sup = None
                if requested_sup.isdigit():
                    candidate = db.session.get(User, int(requested_sup))
                    if (
                        candidate
                        and 'مشرف محافظة' in actual_roles(candidate)
                        and candidate.is_active
                        and gid_values & user_gov_ids(candidate)
                    ):
                        sup = candidate
                if not sup and 'مسؤول التطبيق' not in roles(u):
                    sup = u if 'مشرف محافظة' in actual_roles(u) else None
                if not sup and len(gid_values) == 1:
                    sup = supervisor_for_governorate(next(iter(gid_values)))
                if sup:
                    db.session.add(SupervisorEntry(supervisor_id=sup.id, entry_id=nu.id))
                # The first-level user is also an employee; employee data is completed in the same registration.
                if 'المدخل الأول' in selected_roles and chosen:
                    hire_date_raw = request.form.get('employee_hire_date', '').strip()
                    company_phone = request.form.get('employee_company_phone', '').strip()
                    personal_phone = request.form.get('employee_personal_phone', '').strip()
                    if (
                        not hire_date_raw
                        or not parse_date(hire_date_raw)
                        or not company_phone
                        or not personal_phone
                    ):
                        db.session.rollback()
                        flash(
                            'بيانات الموظف للمدخل الأول مكتملة إلزاميًا: تاريخ التعيين وهاتف الشركة والهاتف الشخصي.',
                        )
                        return redirect('/structure')
                    employee = Employee.query.filter_by(user_id=nu.id).first()
                    if not employee:
                        employee = Employee(
                            user_id=nu.id,
                            employee_code=None,
                            email=nu.email,
                            full_name=nu.full_name,
                            branch_id=appointment_bid,
                            job_title=nu.job_title,
                            job_code=nu.job_code,
                            hire_date=parse_date(
                                request.form.get('employee_hire_date', '').strip(),
                            ),
                            company_phone=request.form.get('employee_company_phone', '').strip(),
                            personal_phone=request.form.get('employee_personal_phone', '').strip(),
                            is_active=True,
                        )
                        db.session.add(employee)
                    else:
                        employee.full_name = nu.full_name
                        employee.email = nu.email
                        employee.job_title = nu.job_title
                        employee.job_code = nu.job_code
            sync_role_accounts(nu)
            log('ADD', 'User', nu.id, username)
            db.session.commit()
            flash('تم إنشاء الحساب وربطه تلقائيًا بالهيكل.')
    gs = (
        Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True).all()
        if 'مسؤول التطبيق' not in roles(u)
        else Governorate.query.filter_by(is_active=True).all()
    )
    bs = (
        Branch.query.filter(Branch.id.in_(bids()), Branch.is_active == True).all()
        if 'مسؤول التطبيق' not in roles(u)
        else Branch.query.filter_by(is_active=True).all()
    )
    role_default_permissions = {r: sorted(ROLE_DEFAULT_PERMISSIONS.get(r, set())) for r in ROLES}
    # الحساب الوهمي لكل دور محفوظ ككيان RoleAccount مستقل؛ نعرضه للإدارة
    # حتى يكون واضحًا أن كل دور إضافي له حسابه الداخلي المستقل بنفس بيانات الدخول.
    role_accounts_by_user = {
        u.id: RoleAccount.query.filter_by(user_id=u.id).order_by(RoleAccount.role.asc()).all()
        for u in visible
    }
    supervisor_choices = [
        x
        for x in User.query.filter_by(is_active=True).order_by(User.full_name).all()
        if 'مشرف محافظة' in actual_roles(x)
    ]
    # مركز التحكم بالشخص: يجمع الهوية، الأدوار، النطاقات، الحسابات الموازية، وتكليف المدخل الأول في بطاقة واحدة.
    people_control = []
    for person in visible:
        person_roles = actual_roles(person)
        govs_for_person = (
            [g for g in gs if g.id in user_gov_ids(person)]
            if 'مشرف محافظة' in person_roles
            else []
        )
        branches_for_person = (
            [b for b in bs if b.id in user_branch_ids(person)]
            if 'المدخل الأول' in person_roles
            else []
        )
        linked_employee = Employee.query.filter_by(user_id=person.id).first()
        entry_assignment = (
            EntryAssignment.query.filter_by(employee_id=linked_employee.id, is_active=True).first()
            if linked_employee
            else None
        )
        entry_branches = []
        entry_supervisor = None
        if entry_assignment:
            entry_supervisor = entry_assignment.supervisor
            entry_branch_ids = {
                x.branch_id
                for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=entry_assignment.id).all()
            }
            entry_branches = (
                [
                    b
                    for b in Branch.query.filter(Branch.id.in_(entry_branch_ids), Branch.is_active == True).order_by(Branch.name).all()
                ]
                if entry_branch_ids
                else []
            )
        people_control.append(
            {
                'user': person,
                'roles': person_roles,
                'governorates': govs_for_person,
                'branches': branches_for_person,
                'employee': linked_employee,
                'entry_assignment': entry_assignment,
                'entry_branches': entry_branches,
                'entry_supervisor': entry_supervisor,
                'role_accounts': role_accounts_by_user.get(person.id, []),
            },
        )
    return render_template(
        'users.html',
        rows=visible,
        gs=gs,
        bs=bs,
        role_default_permissions=role_default_permissions,
        role_accounts_by_user=role_accounts_by_user,
        supervisor_choices=supervisor_choices,
        people_control=people_control,
    )


@bp.route('/users/<int:i>/edit', methods=['GET', 'POST'])
@req
def user_edit(i):
    target = db.session.get(User, i)
    if not target or not can('manage_users') or (not allowed_target_user(target) and i != me().id):
        abort(403)
    if 'مسؤول التطبيق' not in roles() and 'المدخل الأول' not in roles(target):
        abort(403)
    u = target
    if request.method == 'POST':
        u.full_name = request.form.get('full_name', '').strip() or u.full_name
        email = request.form.get('email', '').strip()
        if not email or not valid_email(email):
            flash('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.')
            return redirect(url_for('users.user_edit', i=i))
        duplicate_email = User.query.filter(User.email == email, User.id != i).first()
        if duplicate_email:
            flash('البريد الإلكتروني مستخدم بالفعل.')
            return redirect(url_for('users.user_edit', i=i))
        u.email = email
        u.job_title = request.form.get('job_title', '').strip() or None
        u.job_code = request.form.get('job_code', '').strip() or None
        if not u.full_name or not u.job_title or (not u.job_code):
            flash('الاسم والوظيفة والكود الوظيفي حقول إجبارية.')
            return redirect(url_for('users.user_edit', i=i))
        if 'مسؤول التطبيق' in roles():
            selected = [r for r in request.form.getlist('roles') if r in LOGIN_ROLES]
            if not selected:
                flash('يجب اختيار دور واحد على الأقل.')
                return redirect(url_for('users.user_edit', i=i))
            if i == me().id and 'مسؤول التطبيق' not in selected:
                flash('لا يمكن إزالة دور مسؤول التطبيق من حسابك هنا.')
                return redirect(url_for('users.user_edit', i=i))
            selected_perm_set = {x for x in request.form.getlist('permissions') if x in PERMISSIONS}
            old_roles = actual_roles(target)
            # عند إضافة دور جديد تُضاف صلاحياته الافتراضية تلقائيًا، أما الصلاحيات الموجودة فيمكن لمسؤول التطبيق زيادتها أو تقليلها.
            newly_added = set(selected) - set(old_roles)
            defaults = set()
            for r in newly_added:
                defaults |= ROLE_DEFAULT_PERMISSIONS.get(r, set())
            if 'مسؤول التطبيق' not in roles():
                defaults &= GRANTABLE_BY_SUPERVISOR
                selected_perm_set &= GRANTABLE_BY_SUPERVISOR
            selected_perm_set |= defaults
            UserRole.query.filter_by(user_id=i).delete()
            UserPermission.query.filter_by(user_id=i).delete()
            for r in selected:
                db.session.add(UserRole(user_id=i, role=r))
            for perm in selected_perm_set:
                db.session.add(UserPermission(user_id=i, permission=perm))
            sync_role_accounts(target)
            # Always clear old scope assignments first so removing a role also removes its old scope.
            UserGovernorate.query.filter_by(user_id=i).delete()
            UserBranch.query.filter_by(user_id=i).delete()
            if 'مشرف محافظة' in selected:
                allowed_govs = (
                    {g.id for g in Governorate.query.filter_by(is_active=True).all()}
                    if 'مسؤول التطبيق' in roles()
                    else set(gids())
                )
                chosen = (
                    {int(x) for x in request.form.getlist('governorate_id') if x.isdigit()}
                    & allowed_govs
                )
                if not chosen:
                    db.session.rollback()
                    flash('يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.')
                    return redirect(url_for('users.user_edit', i=i))
                for gid in chosen:
                    db.session.add(UserGovernorate(user_id=i, governorate_id=gid))
            if 'المدخل الأول' in selected and 'مشرف محافظة' not in selected:
                allowed_branches = (
                    {b.id for b in Branch.query.filter_by(is_active=True).all()}
                    if 'مسؤول التطبيق' in roles()
                    else set(bids())
                )
                chosen = (
                    {int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
                    & allowed_branches
                )
                if not chosen:
                    db.session.rollback()
                    flash('يجب إسناد فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
                    return redirect(url_for('users.user_edit', i=i))
                appointment_raw = request.form.get('employee_branch_id', '').strip()
                appointment_bid = int(appointment_raw) if appointment_raw.isdigit() else 0
                appointment_branch = (
                    db.session.get(Branch, appointment_bid)
                    if appointment_bid
                    else None
                )
                if (
                    not appointment_branch
                    or not appointment_branch.is_active
                    or (
                        'مسؤول التطبيق' not in roles()
                        and appointment_branch.governorate_id not in set(gids())
                    )
                ):
                    db.session.rollback()
                    flash('يجب اختيار فرع تعيين تابع لمحافظة ضمن نطاقك.')
                    return redirect(url_for('users.user_edit', i=i))
                for bid in chosen:
                    db.session.add(UserBranch(user_id=i, branch_id=bid))
            # Explicitly keep the simple hierarchy link: first-level user -> responsible supervisor.
            SupervisorEntry.query.filter_by(entry_id=i).delete()
            if 'المدخل الأول' in selected and 'مشرف محافظة' not in selected:
                chosen_gids = {
                    db.session.get(Branch, bid).governorate_id
                    for bid in chosen
                    if db.session.get(Branch, bid)
                }
                sid = request.form.get('supervisor_id', '').strip()
                sup = db.session.get(User, int(sid)) if sid.isdigit() else None
                if not sup and len(chosen_gids) == 1:
                    sup = supervisor_for_governorate(next(iter(chosen_gids)))
                if (
                    sup
                    and sup.is_active
                    and 'مشرف محافظة' in actual_roles(sup)
                    and chosen_gids & user_gov_ids(sup)
                ):
                    db.session.add(SupervisorEntry(supervisor_id=sup.id, entry_id=i))
                linked_emp = Employee.query.filter_by(user_id=i).first()
                hire_date_raw = request.form.get('employee_hire_date', '').strip()
                company_phone = request.form.get('employee_company_phone', '').strip()
                personal_phone = request.form.get('employee_personal_phone', '').strip()
                if (
                    not hire_date_raw
                    or not parse_date(hire_date_raw)
                    or not company_phone
                    or not personal_phone
                ):
                    db.session.rollback()
                    flash(
                        'بيانات الموظف للمدخل الأول مكتملة إلزاميًا: تاريخ التعيين وهاتف الشركة والهاتف الشخصي.',
                    )
                    return redirect(url_for('users.user_edit', i=i))
                if linked_emp:
                    linked_emp.full_name = u.full_name
                    linked_emp.email = u.email
                    linked_emp.job_title = u.job_title
                    linked_emp.job_code = u.job_code
                    linked_emp.branch_id = appointment_bid
                    linked_emp.hire_date = parse_date(hire_date_raw)
                    linked_emp.company_phone = company_phone
                    linked_emp.personal_phone = personal_phone
                    linked_emp.is_active = True
                elif chosen:
                    db.session.add(
                        Employee(
                            user_id=i,
                            employee_code=None,
                            email=u.email,
                            full_name=u.full_name,
                            branch_id=appointment_bid,
                            job_title=u.job_title,
                            job_code=u.job_code,
                            hire_date=parse_date(hire_date_raw),
                            company_phone=company_phone,
                            personal_phone=personal_phone,
                            is_active=True,
                        ),
                    )
        else:
            # Supervisor may only edit first-level users in his governorate(s).
            selected_perm_set = {
                x
                for x in request.form.getlist('permissions')
                if x in GRANTABLE_BY_SUPERVISOR
            }
            UserPermission.query.filter_by(user_id=i).delete()
            for perm in selected_perm_set:
                db.session.add(UserPermission(user_id=i, permission=perm))
            sync_role_accounts(target)
            chosen = (
                {int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
                & set(bids())
            )
            if not chosen:
                flash('يجب إسناد فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
                return redirect(url_for('users.user_edit', i=i))
            appointment_raw = request.form.get('employee_branch_id', '').strip()
            appointment_bid = int(appointment_raw) if appointment_raw.isdigit() else 0
            appointment_branch = (
                db.session.get(Branch, appointment_bid)
                if appointment_bid
                else None
            )
            if (
                not appointment_branch
                or not appointment_branch.is_active
                or appointment_branch.governorate_id not in set(gids())
            ):
                flash('يجب اختيار فرع تعيين تابع لمحافظة ضمن نطاقك.')
                return redirect(url_for('users.user_edit', i=i))
            UserBranch.query.filter_by(user_id=i).delete()
            for bid in chosen:
                db.session.add(UserBranch(user_id=i, branch_id=bid))
            SupervisorEntry.query.filter_by(entry_id=i).delete()
            chosen_gids = {
                db.session.get(Branch, bid).governorate_id
                for bid in chosen
                if db.session.get(Branch, bid)
            }
            sup = me() if 'مشرف محافظة' in actual_roles(me()) else None
            if sup and sup.is_active and chosen_gids & user_gov_ids(sup):
                db.session.add(SupervisorEntry(supervisor_id=sup.id, entry_id=i))
            linked_emp = Employee.query.filter_by(user_id=i).first()
            hire_date_raw = request.form.get('employee_hire_date', '').strip()
            company_phone = request.form.get('employee_company_phone', '').strip()
            personal_phone = request.form.get('employee_personal_phone', '').strip()
            if (
                not hire_date_raw
                or not parse_date(hire_date_raw)
                or not company_phone
                or not personal_phone
            ):
                flash(
                    'بيانات الموظف للمدخل الأول مكتملة إلزاميًا: تاريخ التعيين وهاتف الشركة والهاتف الشخصي.',
                )
                return redirect(url_for('users.user_edit', i=i))
            if linked_emp:
                linked_emp.full_name = u.full_name
                linked_emp.email = u.email
                linked_emp.job_title = u.job_title
                linked_emp.job_code = u.job_code
                linked_emp.branch_id = appointment_bid
                linked_emp.hire_date = parse_date(hire_date_raw)
                linked_emp.company_phone = company_phone
                linked_emp.personal_phone = personal_phone
                linked_emp.is_active = True
            else:
                db.session.add(
                    Employee(
                        user_id=i,
                        employee_code=None,
                        email=u.email,
                        full_name=u.full_name,
                        branch_id=appointment_bid,
                        job_title=u.job_title,
                        job_code=u.job_code,
                        hire_date=parse_date(hire_date_raw),
                        company_phone=company_phone,
                        personal_phone=personal_phone,
                        is_active=True,
                    ),
                )
        log('EDIT', 'User', i, 'تعديل الحساب والنطاق والصلاحيات')
        db.session.commit()
        flash('تم حفظ التعديلات.')
        return redirect('/users')
    gs = (
        Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True).all()
        if 'مسؤول التطبيق' not in roles()
        else Governorate.query.filter_by(is_active=True).all()
    )
    bs = (
        Branch.query.filter(Branch.id.in_(bids()), Branch.is_active == True).all()
        if 'مسؤول التطبيق' not in roles()
        else Branch.query.filter_by(is_active=True).all()
    )
    linked = SupervisorEntry.query.filter_by(entry_id=i).order_by(SupervisorEntry.id.asc()).first()
    entry_supervisor = linked.supervisor if linked else supervisor_for_entry(u)
    supervisor_choices = []
    if 'المدخل الأول' in actual_roles(u):
        gids_u = {
            b.governorate_id
            for b in Branch.query.filter(Branch.id.in_(user_branch_ids(u))).all()
        }
        if gids_u:
            suids = {
                x.user_id
                for x in UserGovernorate.query.filter(UserGovernorate.governorate_id.in_(gids_u)).all()
            }
            supervisor_choices = (
                [
                    x
                    for x in User.query.filter(User.id.in_(suids), User.is_active == True).order_by(User.full_name).all()
                    if 'مشرف محافظة' in actual_roles(x)
                ]
                if suids
                else []
            )
    linked_emp = Employee.query.filter_by(user_id=i).first()
    return render_template(
        'user_edit.html',
        u=u,
        selected_roles=actual_roles(u),
        selected_permissions=user_permissions(u),
        gs=gs,
        bs=bs,
        entry_supervisor=entry_supervisor,
        supervisor_choices=supervisor_choices,
        linked_emp=linked_emp,
    )


@bp.post('/users/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def user_delete(i):
    if i == me().id:
        flash('لا يمكن حذف الحساب المستخدم حاليًا.')
    else:
        u = db.session.get(User, i)
        if not u:
            abort(404)
        if (
            Movement.query.filter(
                (
                    (Movement.created_by == i)
                    | (Movement.modified_by == i)
                    | (Movement.reviewed_by == i)
                    | (Movement.approved_by == i)
                ),
            )
            .count()
        ):
            flash('لا يمكن حذف المستخدم لوجود حركات مرتبطة به؛ استخدم التعطيل.')
        else:
            db.session.delete(u)
            log('DELETE', 'User', i)
            db.session.commit()
            flash('تم حذف المستخدم.')
    return redirect('/users')


@bp.post('/users/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def user_toggle(i):
    if i == me().id:
        flash('لا يمكن تعطيل الحساب المستخدم حاليًا.')
    else:
        u = db.session.get(User, i)
        u.is_active = not u.is_active
        log('TOGGLE', 'User', i)
        db.session.commit()
    return redirect('/users')


@bp.post('/users/<int:i>/reset')
@req
def user_reset_password(i):
    if not can('manage_users') or not has_role('مسؤول التطبيق', 'مشرف محافظة'):
        abort(403)
    u = db.session.get(User, i)
    if not u:
        abort(404)
    if (
        'مسؤول التطبيق' not in roles()
        and not ('المدخل الأول' in roles(u) and bool(set(gids()) & {b.governorate_id for b in Branch.query.join(UserBranch, UserBranch.branch_id == Branch.id).filter(UserBranch.user_id == i).all()}))
    ):
        abort(403)
    p = request.form.get('password', '')
    if not valid_password(p):
        flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حروف وأرقام.')
    else:
        u.password_hash = generate_password_hash(p)
        u.must_change_password = True
        sync_role_accounts(u)
        log('PASSWORD_RESET', 'User', i)
        db.session.commit()
        flash('تمت إعادة التعيين.')
    return redirect('/users')


@bp.post('/users/<int:i>/govs')
@req
@only('مسؤول التطبيق')
def user_update_governorates(i):
    allowed = {g.id for g in Governorate.query.filter_by(is_active=True)}
    chosen = {int(x) for x in request.form.getlist('governorate_id')}
    UserGovernorate.query.filter_by(user_id=i).delete()
    for gid in chosen & allowed:
        db.session.add(UserGovernorate(user_id=i, governorate_id=gid))
    log('ASSIGN', 'User', i, 'محافظات')
    db.session.commit()
    return redirect('/users')


@bp.post('/users/<int:i>/branches')
@req
@only('مسؤول التطبيق', 'مشرف محافظة')
def user_update_branches(i):
    u = db.session.get(User, i)
    if not u or 'المدخل الأول' not in roles(u):
        abort(400)
    if not allowed_target_user(u):
        abort(403)
    allowed = set(bids())
    chosen = {int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & allowed
    if not chosen:
        flash('يجب إسناد فرع واحد على الأقل للمدخل الأول.')
        return redirect('/users')
    UserBranch.query.filter_by(user_id=i).delete()
    for bid in chosen:
        db.session.add(UserBranch(user_id=i, branch_id=bid))
    linked_emp = Employee.query.filter_by(user_id=i).first()
    if linked_emp:
        # فرع التعيين كموظف مستقل تمامًا عن فروع المسؤولية.
        linked_emp.full_name = u.full_name
        linked_emp.email = u.email
        linked_emp.job_title = u.job_title
        linked_emp.job_code = u.job_code
        linked_emp.is_active = True
    else:
        # لا ننشئ سجل موظف ناقصًا من شاشة إدارة فروع المسؤولية؛ إنشاء المدخل الأول ينشئ الموظف كاملًا.
        flash(
            'تم تحديث فروع المسؤولية. سجل الموظف غير مكتمل، يرجى فتح تعديل المدخل لاستكمال بيانات الموظف.',
        )
    log('ASSIGN', 'User', i, 'فروع المسؤولية')
    db.session.commit()
    return redirect('/structure')


@bp.post('/users/<int:i>/grant-entry-role')
@req
@only('مسؤول التطبيق')
def grant_entry_role(i):
    u = db.session.get(User, i)
    if not u or not u.is_active:
        abort(404)
    if 'مشرف محافظة' not in actual_roles(u):
        flash('يمكن منح أهلية المدخل الأول من خلال هذا الإجراء للمشرفين فقط.')
        return redirect('/users')
    linked = Employee.query.filter_by(user_id=u.id, is_active=True).first()
    if not linked:
        flash('لا يمكن منح الدور للمشرف قبل وجود سجل موظف مرتبط بحسابه.')
        return redirect(url_for('users.user_edit', i=i))
    if 'المدخل الأول' not in actual_roles(u):
        db.session.add(UserRole(user_id=u.id, role='المدخل الأول'))
        log('ROLE_CHANGE', 'User', i, 'منح أهلية دور المدخل الأول للمشرف')
        db.session.commit()
        flash(
            f'تم منح {u.full_name} أهلية دور المدخل الأول. سيظهر الآن في خانة الموظف عند إضافة مدخل أول من الرئيسية.',
        )
    else:
        flash(f'{u.full_name} لديه بالفعل أهلية دور المدخل الأول.')
    return redirect('/structure')


@bp.post('/users/<int:i>/revoke-entry-role')
@req
@only('مسؤول التطبيق')
def revoke_entry_role(i):
    u = db.session.get(User, i)
    if not u:
        abort(404)
    if 'المدخل الأول' in actual_roles(u):
        if (
            EntryAssignment.query.join(Employee, EntryAssignment.employee_id == Employee.id)
            .filter(Employee.user_id == u.id, EntryAssignment.is_active == True)
            .first()
        ):
            flash('لا يمكن إزالة أهلية الدور أثناء وجود تكليف مدخل أول فعال. أزل التكليف أولًا.')
            return redirect('/structure')
        UserRole.query.filter_by(user_id=i, role='المدخل الأول').delete()
        log('ROLE_CHANGE', 'User', i, 'إزالة أهلية دور المدخل الأول للمشرف')
        db.session.commit()
        flash(f'تمت إزالة أهلية دور المدخل الأول من {u.full_name}.')
    return redirect('/structure')


@bp.route('/users/<int:i>/entry-management', methods=['GET', 'POST'])
@req
def entry_management(i):
    u = db.session.get(User, i)
    if not u or 'المدخل الأول' not in actual_roles(u):
        abort(404)
    if not allowed_target_user(u):
        abort(403)
    if 'مسؤول التطبيق' not in roles() and 'مشرف محافظة' not in roles():
        abort(403)
    current_ids = user_branch_ids(u)
    allowed_branch_objs = (
        (
            Branch.query.filter(
                Branch.is_active == True,
                Branch.governorate_id.in_(
                    (
                        gids()
                        if 'مسؤول التطبيق' not in roles()
                        else [g.id for g in Governorate.query.filter_by(is_active=True).all()]
                    ),
                ),
            )
            .order_by(Branch.name.asc())
            .all()
        )
        if gids() or 'مسؤول التطبيق' in roles()
        else []
    )
    # الفرع المتاح للمدخل = غير مرتبط بمدخل أول آخر، أو مرتبط بالمدخل الحالي.
    available = []
    for b in allowed_branch_objs:
        owners = [
            x.user_id
            for x in UserBranch.query.filter_by(branch_id=b.id).all()
            if x.user_id != u.id
        ]
        occupied = False
        for oid in owners:
            ou = db.session.get(User, oid)
            if ou and ou.is_active and ('المدخل الأول' in actual_roles(ou)):
                occupied = True
                break
        if not occupied or b.id in current_ids:
            available.append(b)
    if request.method == 'POST':
        action = request.form.get('action', 'branches')
        if action == 'branches':
            chosen = {int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
            allowed_ids = {b.id for b in available}
            chosen &= allowed_ids
            if not chosen:
                flash('يجب اختيار فرع واحد على الأقل للمدخل الأول.')
                return redirect(url_for('users.entry_management', i=i))
            UserBranch.query.filter_by(user_id=i).delete()
            for bid in sorted(chosen):
                db.session.add(UserBranch(user_id=i, branch_id=bid))
            log('ASSIGN', 'User', i, 'تحديث فروع مسؤولية المدخل الأول')
            db.session.commit()
            flash('تم تحديث فروع مسؤولية المدخل الأول بنجاح.')
            return redirect(url_for('users.entry_management', i=i))
        if action == 'remove_role':
            if 'مسؤول التطبيق' not in roles():
                abort(403)
            linked = Employee.query.filter_by(user_id=u.id).first()
            UserRole.query.filter_by(user_id=u.id, role='المدخل الأول').delete()
            UserBranch.query.filter_by(user_id=u.id).delete()
            SupervisorEntry.query.filter_by(entry_id=u.id).delete()
            remaining = actual_roles(u) - {'المدخل الأول'}
            if not remaining:
                u.is_active = False
            if linked:
                linked.user_id = None
            log('ROLE_CHANGE', 'User', i, 'إزالة دور المدخل الأول')
            db.session.commit()
            flash('تمت إزالة دور المدخل الأول مع الاحتفاظ بسجل الموظف وحركاته.')
            return redirect('/')
    return render_template(
        'entry_management.html',
        u=u,
        branches=available,
        current_ids=current_ids,
        linked_emp=Employee.query.filter_by(user_id=u.id).first(),
        supervisors=[
            s
            for s in User.query.all()
            if s.is_active and 'مشرف محافظة' in actual_roles(s)
        ],
        is_admin='مسؤول التطبيق' in roles(),
    )
