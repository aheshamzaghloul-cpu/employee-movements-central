"""System governance and organizational structure routes.

First-level entry operations are intentionally exposed from the Home page;
this module keeps the underlying endpoints for backward compatibility.
"""

from flask import abort, Blueprint, flash, redirect, render_template, request, url_for

from ..access import (
    actual_roles,
    bids,
    branch_ok,
    has_role,
    log,
    me,
    req,
    roles,
    scope_governorate_id,
    user_gov_ids,
)
from ..assignments import (
    organizational_entry_for_employee,
    sync_role_accounts,
)
from ..constants import ROLE_DEFAULT_PERMISSIONS
from ..services.account_security import invalidate_user_workflows
from ..extensions import db
from ..models import (
    ApprovalDelegation,
    Audit,
    Branch,
    Employee,
    EntryAssignment,
    EntryAssignmentBranch,
    Governorate,
    RoleAccount,
    SupervisorEntry,
    User,
    UserBranch,
    UserGovernorate,
    UserPermission,
    UserRole,
)

bp = Blueprint('structure', __name__)


def _organizational_entry_branch_ids(assignment, employee=None):
    """Return branch links owned by an organizational entry assignment.

    Legacy assignments may predate explicit EntryAssignmentBranch links; their
    employee home branch is then the only defensible fallback.
    """
    branch_ids = {
        link.branch_id
        for link in EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).all()
    } if assignment else set()
    if not branch_ids and employee and employee.branch_id:
        branch_ids.add(employee.branch_id)
    return branch_ids


def _entry_assignment_in_work_scope(assignment, employee=None):
    selected = scope_governorate_id()
    allowed = set(bids())
    current = _organizational_entry_branch_ids(assignment, employee)
    return bool(selected and allowed and current and current.issubset(allowed))


def _employee_is_supervisor_for_work_scope(employee, governorate_id):
    if not employee or not employee.user_id or not governorate_id:
        return False
    user = db.session.get(User, employee.user_id)
    return bool(
        user and user.is_active
        and 'مشرف محافظة' in actual_roles(user)
        and int(governorate_id) in user_gov_ids(user)
    )


@bp.get('/structure')
@req
def structure():
    """Render the application-admin governance workspace.

    This page is intentionally admin-only and is a summary/navigation workspace.
    Operational entry assignments are managed from Home, so the page should not
    construct a second branch/employee tree or load unused picker data.
    """
    current = me()
    if 'مسؤول التطبيق' not in roles(current):
        abort(403)

    active_gov_count = Governorate.query.filter_by(is_active=True).count()
    active_branch_count = Branch.query.filter_by(is_active=True).count()
    active_employee_count = Employee.query.filter_by(is_active=True).count()
    active_users = User.query.filter_by(is_active=True).all()
    inactive_users = User.query.filter_by(is_active=False).count()

    # Read all active-user roles in one query rather than issuing a UserRole
    # query for every user while computing governance metrics.
    active_user_ids = {user.id for user in active_users}
    role_rows = (
        UserRole.query.with_entities(UserRole.user_id, UserRole.role)
        .filter(UserRole.user_id.in_(active_user_ids)).all()
        if active_user_ids else []
    )
    roles_by_user = {}
    for user_id, role in role_rows:
        roles_by_user.setdefault(user_id, set()).add(role)
    active_supervisor_ids = {
        user.id for user in active_users
        if 'مشرف محافظة' in roles_by_user.get(user.id, set())
    }
    supervisors_count = len(active_supervisor_ids)
    support_count = sum(
        1 for user in active_users
        if 'Manager Application Support' in roles_by_user.get(user.id, set())
    )

    entry_assignments = EntryAssignment.query.filter_by(is_active=True).all()
    entry_assignment_ids = {assignment.id for assignment in entry_assignments}
    # Reuse one link query for branch coverage and missing-assignment counters.
    entry_assignment_links = (
        EntryAssignmentBranch.query.filter(
            EntryAssignmentBranch.entry_assignment_id.in_(entry_assignment_ids)
        ).all()
        if entry_assignment_ids else []
    )
    assigned_entry_branch_ids = {link.branch_id for link in entry_assignment_links}
    entry_assignments_with_branches = {link.entry_assignment_id for link in entry_assignment_links}
    unassigned_branch_count = max(0, active_branch_count - len(assigned_entry_branch_ids))

    role_account_count = RoleAccount.query.count()
    active_delegation_count = ApprovalDelegation.query.filter_by(is_active=True).count()
    entry_with_no_branch_count = sum(
        1 for assignment in entry_assignments
        if assignment.id not in entry_assignments_with_branches
    )
    supervisor_scope_ids = (
        {
            user_id for (user_id,) in UserGovernorate.query.with_entities(UserGovernorate.user_id)
            .filter(UserGovernorate.user_id.in_(active_supervisor_ids)).distinct().all()
        }
        if active_supervisor_ids else set()
    )
    supervisors_without_scope_count = len(active_supervisor_ids - supervisor_scope_ids)
    must_change_password_count = sum(1 for user in active_users if user.must_change_password)
    admin_stats = {
        'governorates': active_gov_count,
        'branches': active_branch_count,
        'employees': active_employee_count,
        'users': len(active_users),
        'inactive_users': inactive_users,
        'supervisors': supervisors_count,
        'support': support_count,
        'entries': len(entry_assignments),
        'entry_branches': len(assigned_entry_branch_ids),
        'unassigned_branches': unassigned_branch_count,
        'entry_without_branches': entry_with_no_branch_count,
        'supervisors_without_scope': supervisors_without_scope_count,
        'must_change_password': must_change_password_count,
        'role_accounts': role_account_count,
        'delegations': active_delegation_count,
    }

    admin_intelligence = []

    def add_admin_signal(priority, title, detail, action_url, action_label, prompt=None):
        admin_intelligence.append({
            'priority': priority,
            'title': title,
            'detail': detail,
            'action_url': action_url,
            'action_label': action_label,
            'prompt': prompt,
        })

    if not active_gov_count:
        add_admin_signal('urgent', 'لا توجد محافظات نشطة', 'الهيكل الإداري لا يمكن تشغيله بصورة طبيعية قبل وجود محافظة واحدة على الأقل.', '/governorates', 'إدارة المحافظات', 'راجع حالة المحافظات في النظام')
    if unassigned_branch_count:
        add_admin_signal('urgent', f'{unassigned_branch_count} فرع بلا مسؤول إدخال', 'هناك فروع نشطة لم يُسند إليها تكليف مسؤول إدخال الفروع حتى الآن.', '/', 'تنفيذ من الرئيسية', 'ما الفروع التي تحتاج إلى تكليف مسؤول إدخال؟')
    if entry_with_no_branch_count:
        add_admin_signal('warning', f'{entry_with_no_branch_count} تكليف إدخال بلا فروع', 'التكليف موجود، لكن لم تُربط به فروع.', '/', 'إدارة من الرئيسية', 'ما تكليفات إدخال الفروع التي تحتاج مراجعة؟')
    if supervisors_without_scope_count:
        add_admin_signal('warning', f'{supervisors_without_scope_count} مشرف بلا نطاق محافظة', 'حساب مشرف نشط موجود بدون محافظة مسندة إليه.', '/users', 'مراجعة المشرفين', 'راجع المشرفين الذين ليس لهم نطاق محافظة')
    if inactive_users:
        add_admin_signal('info', f'{inactive_users} حسابات معطلة', 'ليست مشكلة تشغيلية بحد ذاتها، لكنها تستحق المراجعة الدورية.', '/users', 'إدارة الحسابات', 'ما الحسابات المعطلة؟')
    if must_change_password_count:
        add_admin_signal('info', f'{must_change_password_count} حسابات مطالبة بتغيير كلمة المرور', 'يمكن متابعتها من إدارة الحسابات.', '/users', 'مراجعة الحسابات', 'ما الحسابات التي تحتاج تغيير كلمة المرور؟')
    if not admin_intelligence:
        add_admin_signal('ok', 'الوضع الإداري مستقر', 'لا توجد إشارات إدارية واضحة تحتاج تدخلاً الآن وفق البيانات الحالية.', '/audit', 'فتح سجل التدقيق', 'اعطني ملخصًا سريعًا لحالة النظام')

    admin_audit = Audit.query.order_by(Audit.created_at.desc()).limit(8).all()
    return render_template(
        'structure.html',
        admin_view=True,
        admin_stats=admin_stats,
        admin_intelligence=admin_intelligence,
        admin_audit=admin_audit,
    )


@bp.post('/entry-role/<int:employee_id>/branches')
@req
def update_organizational_entry_branches(employee_id):
    if not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    employee = db.session.get(Employee, employee_id)
    assignment = (
        EntryAssignment.query.filter_by(employee_id=employee_id, is_active=True).first()
        if employee else None
    )
    selected_gid = scope_governorate_id()
    allowed = set(bids())
    if not employee or not assignment or not employee.is_active:
        abort(404)
    if not selected_gid or not allowed or not _entry_assignment_in_work_scope(assignment, employee):
        abort(403)
    if 'مشرف محافظة' in roles() and 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles():
        if assignment.supervisor_id != me().id or int(selected_gid) not in user_gov_ids(me()):
            abort(403)

    raw_ids = request.form.getlist('branch_id')
    if any(not str(raw).isdigit() for raw in raw_ids):
        flash('توجد قيمة فرع غير صحيحة.')
        return redirect('/#entry-directory')
    chosen_raw = {int(raw) for raw in raw_ids}
    if not chosen_raw or not chosen_raw.issubset(allowed):
        flash('اختر فرعًا واحدًا على الأقل من فروع محافظة العمل المختارة فقط.')
        return redirect('/#entry-directory')

    occupied = {}
    for other in EntryAssignment.query.filter(EntryAssignment.is_active == True, EntryAssignment.id != assignment.id).all():
        for link in EntryAssignmentBranch.query.filter_by(entry_assignment_id=other.id).all():
            occupied[link.branch_id] = other.employee_id
    if chosen_raw & set(occupied):
        flash('يوجد فرع من الفروع المختارة مسند بالفعل إلى مسؤول إدخال آخر.')
        return redirect('/#entry-directory')

    EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).delete()
    for branch_id in sorted(chosen_raw):
        db.session.add(EntryAssignmentBranch(entry_assignment_id=assignment.id, branch_id=branch_id))
    log('ASSIGN', 'Employee', employee_id, 'تحديث فروع مسؤول إدخال الفروع داخل محافظة العمل المختارة')
    db.session.commit()
    flash('تم تحديث فروع مسؤول إدخال الفروع بنجاح.')
    return redirect('/#entry-directory')

@bp.post('/entry-role/<int:employee_id>/replace')
@req
def replace_organizational_entry_from_home(employee_id):
    if not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    old = db.session.get(Employee, employee_id)
    assignment = (
        EntryAssignment.query.filter_by(employee_id=employee_id, is_active=True).first()
        if old else None
    )
    raw_new_id = (request.form.get('new_entry_employee_id') or '').strip()
    new = db.session.get(Employee, int(raw_new_id)) if raw_new_id.isdigit() else None
    selected_gid = scope_governorate_id()
    if not old or not assignment or not old.is_active:
        flash('الموظف المحدد ليس مسؤول إدخال فروع نشطًا.')
        return redirect('/#entry-directory')
    if not selected_gid or not _entry_assignment_in_work_scope(assignment, old):
        abort(403)
    if 'مشرف محافظة' in roles() and 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles():
        if assignment.supervisor_id != me().id or int(selected_gid) not in user_gov_ids(me()):
            abort(403)
    valid_new = bool(
        new and new.is_active and new.id != old.id
        and (branch_ok(new.branch_id) or _employee_is_supervisor_for_work_scope(new, selected_gid))
    )
    if not valid_new:
        flash('اختر موظفًا نشطًا من محافظة العمل، أو سجل الموظف المرتبط بمشرفها المسؤول.')
        return redirect('/#entry-directory')
    if EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first():
        flash('الموظف البديل لديه بالفعل تكليف إدخال نشط. اختر موظفًا آخر.')
        return redirect('/#entry-directory')
    assignment.employee_id = new.id
    log('REPLACE', 'Employee', old.id, f'استبدال مسؤول إدخال الفروع بالموظف {new.full_name} داخل محافظة العمل')
    log('REPLACE', 'Employee', new.id, f'استلام تكليف مسؤول إدخال الفروع بدل {old.full_name}')
    db.session.commit()
    flash(f'تم استبدال مسؤول إدخال الفروع بالموظف {new.full_name} مع الاحتفاظ بالتكليفات والفروع وسجل الموظف السابق.')
    return redirect('/#entry-directory')

@bp.route('/replacement', methods=['GET', 'POST'])
@req
def replacement():
    if 'مسؤول التطبيق' not in roles():
        abort(403)
    mode = (
        request.form.get('mode', '')
        if request.method == 'POST'
        else request.args.get('mode', 'supervisor')
    )
    if mode == 'entry':
        flash('استبدال مسؤول إدخال الفروع يتم من الصفحة الرئيسية.')
        return redirect('/#entry-directory')
    if request.method == 'POST':
        if mode == 'supervisor':
            old_id = request.form.get('old_supervisor_id', '').strip()
            new_id = request.form.get('new_supervisor_id', '').strip()
            old = db.session.get(User, int(old_id)) if old_id.isdigit() else None
            new = db.session.get(User, int(new_id)) if new_id.isdigit() else None
            if not old or not new or old.id == new.id or (not old.is_active) or (not new.is_active):
                flash('يجب اختيار مشرف حالي وبديل نشط مختلف عنه.')
                return redirect(url_for('structure.replacement', mode='supervisor'))
            if 'مشرف محافظة' not in actual_roles(old):
                flash('الشخص المحدد للاستبدال ليس مشرف محافظة حاليًا.')
                return redirect(url_for('structure.replacement', mode='supervisor'))
            # Target receives the supervisor role and its default permissions; existing target roles remain intact.
            if 'مشرف محافظة' not in actual_roles(new):
                db.session.add(UserRole(user_id=new.id, role='مشرف محافظة'))
                for perm in ROLE_DEFAULT_PERMISSIONS['مشرف محافظة']:
                    if not UserPermission.query.filter_by(user_id=new.id, permission=perm).first():
                        db.session.add(UserPermission(user_id=new.id, permission=perm))
            # Move governorate scope and subordinate entry relationships.
            old_govs = UserGovernorate.query.filter_by(user_id=old.id).all()
            moved = 0
            for link in old_govs:
                if not UserGovernorate.query.filter_by(user_id=new.id, governorate_id=link.governorate_id).first():
                    db.session.add(
                        UserGovernorate(user_id=new.id, governorate_id=link.governorate_id),
                    )
                moved += 1
            UserGovernorate.query.filter_by(user_id=old.id).delete()
            for rel in SupervisorEntry.query.filter_by(supervisor_id=old.id).all():
                exists = (
                    SupervisorEntry.query.filter_by(supervisor_id=new.id, entry_id=rel.entry_id)
                    .first()
                )
                if exists:
                    db.session.delete(rel)
                else:
                    rel.supervisor_id = new.id
            # Active approval delegations tied to the outgoing supervisor follow the replacement.
            for d in ApprovalDelegation.query.filter_by(supervisor_id=old.id, is_active=True).all():
                d.supervisor_id = new.id
            # Remove only the replaced role from the old user; preserve other roles and employee history.
            UserRole.query.filter_by(user_id=old.id, role='مشرف محافظة').delete()
            sync_role_accounts(old)
            sync_role_accounts(new)
            if not actual_roles(old):
                old.is_active = False
            invalidate_user_workflows(old.id)
            invalidate_user_workflows(new.id)
            log(
                'REPLACE',
                'User',
                old.id,
                f'استبدال مشرف محافظة بالبديل {new.full_name} — نقل {moved} ارتباط محافظة',
            )
            log('REPLACE', 'User', new.id, f'استلام دور ونطاق مشرف المحافظة بدل {old.full_name}')
            db.session.commit()
            flash(
                f'تم استبدال المشرف ونقل نطاقه وارتباطاته إلى {new.full_name} دون حذف الموظف أو تاريخه.',
            )
            return redirect(url_for('structure.replacement', mode='supervisor'))
        if mode == 'entry':
            old_id = request.form.get('old_entry_employee_id', '').strip()
            new_id = request.form.get('new_entry_employee_id', '').strip()
            old = db.session.get(Employee, int(old_id)) if old_id.isdigit() else None
            new = db.session.get(Employee, int(new_id)) if new_id.isdigit() else None
            if not old or not new or old.id == new.id or (not old.is_active) or (not new.is_active):
                flash('اختر مسؤول إدخال حاليًا وموظفًا بديلًا نشطًا مختلفًا عنه.')
                return redirect(url_for('structure.replacement', mode='entry'))
            old_a = EntryAssignment.query.filter_by(employee_id=old.id, is_active=True).first()
            new_a = EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first()
            if not old_a:
                flash('الموظف المحدد لا يملك تكليف إدخال نشطًا.')
                return redirect(url_for('structure.replacement', mode='entry'))
            if new_a:
                flash('الموظف البديل لديه بالفعل تكليف إدخال نشط. اختر موظفًا آخر.')
                return redirect(url_for('structure.replacement', mode='entry'))
            # Transfer the same assignment object to preserve branch responsibility and supervisor link.
            old_a.employee_id = new.id
            # Legacy compatibility: if the old entry still has an account role, transfer its branch/supervisor links too.
            if old.user_id and new.user_id:
                old_u = db.session.get(User, old.user_id)
                new_u = db.session.get(User, new.user_id)
                if old_u and new_u:
                    for link in UserBranch.query.filter_by(user_id=old_u.id).all():
                        if not UserBranch.query.filter_by(user_id=new_u.id, branch_id=link.branch_id).first():
                            db.session.add(UserBranch(user_id=new_u.id, branch_id=link.branch_id))
                    UserBranch.query.filter_by(user_id=old_u.id).delete()
                    for rel in SupervisorEntry.query.filter_by(entry_id=old_u.id).all():
                        if not SupervisorEntry.query.filter_by(supervisor_id=rel.supervisor_id, entry_id=new_u.id).first():
                            rel.entry_id = new_u.id
                        else:
                            db.session.delete(rel)
                    UserRole.query.filter_by(user_id=old_u.id, role='المدخل الأول').delete()
                    sync_role_accounts(old_u)
                    sync_role_accounts(new_u)
                    if not actual_roles(old_u):
                        old_u.is_active = False
                    invalidate_user_workflows(old_u.id)
                    invalidate_user_workflows(new_u.id)
            log(
                'REPLACE',
                'Employee',
                old.id,
                f'استبدال مسؤول إدخال الفروع بالموظف البديل {new.full_name}',
            )
            log('REPLACE', 'Employee', new.id, f'استلام تكليف مسؤول إدخال الفروع بدل {old.full_name}')
            db.session.commit()
            flash(
                f'تم استبدال مسؤول إدخال الفروع ونقل الفروع والمسؤولية إلى {new.full_name} مع الحفاظ على سجل الموظف القديم.',
            )
            return redirect(url_for('structure.replacement', mode='entry'))
        flash('نوع الاستبدال غير صحيح.')
    supervisors = [
        u
        for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
        if 'مشرف محافظة' in actual_roles(u)
    ]
    supervisor_targets = [
        u
        for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
        if u not in supervisors and u.id != me().id
    ]
    entry_assignments = (
        EntryAssignment.query.filter_by(is_active=True)
        .order_by(EntryAssignment.id.asc())
        .all()
    )
    entry_employees = [a.employee for a in entry_assignments if a.employee and a.employee.is_active]
    entry_ids = {e.id for e in entry_employees}
    entry_targets = (
        Employee.query.filter(
            Employee.is_active == True,
            ~Employee.id.in_(entry_ids) if entry_ids else True,
        )
        .order_by(Employee.full_name)
        .all()
    )
    return render_template(
        'replacement.html',
        mode=mode,
        supervisors=supervisors,
        supervisor_targets=supervisor_targets,
        entry_assignments=entry_assignments,
        entry_employees=entry_employees,
        entry_targets=entry_targets,
    )


@bp.post('/entry-role/add')
@req
def add_organizational_entry_role():
    if not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    selected_gid = scope_governorate_id()
    allowed_branch_ids = set(bids())
    if not selected_gid or not allowed_branch_ids:
        flash('حدد محافظة العمل أولًا قبل تكليف مسؤول إدخال الفروع.')
        return redirect('/#entry-directory')

    raw_employee_id = (request.form.get('employee_id') or '').strip()
    if not raw_employee_id.isdigit():
        flash('اختر موظفًا مسجلًا أولًا.')
        return redirect('/#entry-directory')
    employee = db.session.get(Employee, int(raw_employee_id))
    if not employee or not employee.is_active:
        flash('الموظف غير موجود أو غير نشط.')
        return redirect('/#entry-directory')
    existing = EntryAssignment.query.filter_by(employee_id=employee.id).first()
    if existing and existing.is_active:
        flash('هذا الموظف لديه بالفعل تكليف مسؤول إدخال الفروع.')
        return redirect('/#entry-directory')

    central_operator = bool({'مسؤول التطبيق', 'Manager Application Support'} & roles())
    if central_operator:
        raw_supervisor_id = (request.form.get('supervisor_id') or '').strip()
        supervisor = db.session.get(User, int(raw_supervisor_id)) if raw_supervisor_id.isdigit() else None
        if (
            not supervisor or not supervisor.is_active
            or 'مشرف محافظة' not in actual_roles(supervisor)
            or int(selected_gid) not in user_gov_ids(supervisor)
        ):
            flash('اختر مشرفًا نشطًا مسؤولًا عن محافظة العمل المختارة.')
            return redirect('/#entry-directory')
    else:
        supervisor = me()
        if int(selected_gid) not in user_gov_ids(supervisor):
            abort(403)

    supervisor_self = bool(
        employee.user_id and int(employee.user_id) == supervisor.id
        and 'مشرف محافظة' in actual_roles(supervisor)
    )
    if not supervisor_self and not branch_ok(employee.branch_id):
        abort(403)

    raw_branch_ids = request.form.getlist('branch_id')
    if any(not str(raw).isdigit() for raw in raw_branch_ids):
        flash('توجد قيمة فرع غير صحيحة.')
        return redirect('/#entry-directory')
    branch_ids = {int(raw) for raw in raw_branch_ids}
    if not branch_ids:
        branch_ids = {employee.branch_id} if employee.branch_id in allowed_branch_ids else set()
    if not branch_ids or not branch_ids.issubset(allowed_branch_ids):
        flash('اختر فرعًا واحدًا على الأقل من فروع محافظة العمل المختارة فقط.')
        return redirect('/#entry-directory')

    taken = {
        link.branch_id
        for link in EntryAssignmentBranch.query.join(EntryAssignment)
        .filter(EntryAssignment.is_active == True).all()
    }
    if branch_ids & taken:
        flash('يوجد فرع من الفروع المختارة مسند بالفعل إلى مسؤول إدخال آخر.')
        return redirect('/#entry-directory')

    if existing:
        assignment = existing
        assignment.supervisor_id = supervisor.id
        assignment.is_active = True
        EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).delete()
    else:
        assignment = EntryAssignment(employee_id=employee.id, supervisor_id=supervisor.id, is_active=True)
        db.session.add(assignment)
        db.session.flush()
    for branch_id in sorted(branch_ids):
        db.session.add(EntryAssignmentBranch(entry_assignment_id=assignment.id, branch_id=branch_id))
    log('ROLE_CHANGE', 'Employee', employee.id, 'إضافة تكليف مسؤول إدخال للفروع دون حساب دخول')
    db.session.commit()
    flash('تم حفظ تكليف مسؤول إدخال الفروع داخل محافظة العمل المختارة، دون إنشاء دور دخول أو حساب جديد.')
    return redirect('/#entry-directory')

@bp.post('/entry-role/<int:employee_id>/remove')
@req
def remove_organizational_entry_role(employee_id):
    if not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    employee = db.session.get(Employee, employee_id)
    assignment = organizational_entry_for_employee(employee) if employee else None
    if not assignment:
        abort(404)
    selected_gid = scope_governorate_id()
    if not selected_gid or not _entry_assignment_in_work_scope(assignment, employee):
        abort(403)
    if 'مشرف محافظة' in roles() and 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles():
        if assignment.supervisor_id != me().id or int(selected_gid) not in user_gov_ids(me()):
            abort(403)
    assignment.is_active = False
    db.session.commit()
    log('ROLE_CHANGE', 'Employee', employee_id, 'إزالة تكليف مسؤول إدخال الفروع من محافظة العمل المختارة')
    db.session.commit()
    flash('تمت إزالة تكليف مسؤول إدخال الفروع. أصبحت الفروع متاحة لإسناد جديد.')
    return redirect('/#entry-directory')

