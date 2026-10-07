"""System governance and organizational structure routes.

First-level entry operations are intentionally exposed from the Home page;
this module keeps the underlying endpoints for backward compatibility.
"""

from flask import abort, Blueprint, flash, redirect, render_template, request, session, url_for

from ..access import (
    actual_roles,
    bids,
    delegated_gov_ids,
    branch_ok,
    has_role,
    log,
    me,
    req,
    roles,
    scope_governorate_id,
    user_branch_ids,
    user_gov_ids,
)
from ..assignments import (
    entries_for_supervisor,
    entry_role_exists,
    organizational_entries_for_supervisor,
    organizational_entry_for_employee,
    supervisor_for_governorate,
    sync_role_accounts,
)
from ..constants import ROLE_DEFAULT_PERMISSIONS
from ..extensions import db
from ..models import (
    ApprovalDelegation,
    Audit,
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

bp = Blueprint('structure', __name__)


@bp.get('/structure')
@req
def structure():
    # الإدارة مركز التحكم الخاص بمسؤول التطبيق فقط.
    current = me()
    # صفحة الإدارة تلتزم بالدور النشط؛ الحساب متعدد الأدوار يبدّل الدور من رأس التطبيق.
    effective = roles(current)
    is_admin = 'مسؤول التطبيق' in effective
    is_supervisor = 'مشرف محافظة' in effective
    is_manager_support = 'Manager Application Support' in effective
    is_entry = 'المدخل الأول' in effective
    if not is_admin:
        abort(403)

    # مسؤول التطبيق يرى كل المحافظات، والمشرف يرى محافظاته فقط.
    selected_gov = ''
    if is_admin:
        # الإدارة مركز قيادة شامل على مستوى النظام. لا توجد محافظة عمل
        # ولا بوابة نطاق هنا؛ المحافظة تستخدم كمرشح داخل أدوات الهيكل فقط.
        all_govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        govs = []
    elif is_manager_support:
        allowed_govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if selected_gov.isdigit() and any((g.id == int(selected_gov) for g in allowed_govs)):
            govs = [db.session.get(Governorate, int(selected_gov))]
        else:
            govs = []
            selected_gov = ''
    elif is_supervisor:
        supervisor_gids = list(user_gov_ids(current))
        allowed_govs = (
            (
                Governorate.query.filter(
                    Governorate.id.in_(supervisor_gids),
                    Governorate.is_active == True,
                )
                .order_by(Governorate.name)
                .all()
            )
            if supervisor_gids
            else []
        )
        if selected_gov.isdigit() and any((g.id == int(selected_gov) for g in allowed_govs)):
            govs = [db.session.get(Governorate, int(selected_gov))]
        elif len(allowed_govs) == 1:
            # فتح المحافظة المسجلة للمشرف تلقائيًا إذا كانت له محافظة واحدة.
            govs = [allowed_govs[0]]
            selected_gov = str(allowed_govs[0].id)
        else:
            govs = []
            selected_gov = ''
    else:
        entry_branch_ids = user_branch_ids(current)
        entry_gids = (
            {
                b.governorate_id
                for b in Branch.query.filter(Branch.id.in_(entry_branch_ids), Branch.is_active == True).all()
            }
            if entry_branch_ids
            else set()
        )
        govs = (
            (
                Governorate.query.filter(
                    Governorate.id.in_(entry_gids),
                    Governorate.is_active == True,
                )
                .order_by(Governorate.name)
                .all()
            )
            if entry_gids
            else []
        )
        selected_gov = ''

    tree = []
    # لا نعرض تفاصيل الهيكل قبل اختيار المحافظة صراحةً.
    for g in govs:
        bs = Branch.query.filter_by(governorate_id=g.id, is_active=True).order_by(Branch.name).all()
        supervisors = []
        suids = [x.user_id for x in UserGovernorate.query.filter_by(governorate_id=g.id).all()]
        for u in (
            (
                User.query.filter(User.id.in_(suids), User.is_active == True)
                .order_by(User.full_name)
                .all()
            )
            if suids
            else []
        ):
            if 'مشرف محافظة' not in actual_roles(u):
                continue
            if is_supervisor and (not is_manager_support) and (u.id != current.id):
                continue
            supervisors.append(u)
        entries = []
        # التنظيم الجديد: المدخل الأول موظف/تصنيف إداري فقط، بلا حساب دخول.
        org_entries = []
        if is_admin:
            org_entries = [
                (a, [b for b in Branch.query.join(EntryAssignmentBranch, EntryAssignmentBranch.branch_id == Branch.id).filter(EntryAssignmentBranch.entry_assignment_id == a.id, Branch.is_active == True).all()], a.supervisor)
                for a in EntryAssignment.query.filter_by(is_active=True).all()
                if a.employee and a.employee.is_active
            ]
        elif is_manager_support:
            org_entries = []
            for su in supervisors:
                org_entries.extend(
                    [
                        (a, bs2, a.supervisor)
                        for (a, bs2) in organizational_entries_for_supervisor(su, g.id)
                    ],
                )
        elif is_supervisor:
            org_entries = [
                (a, bs2, a.supervisor)
                for (a, bs2) in organizational_entries_for_supervisor(current, g.id)
            ]
        for (a, scoped, sup) in org_entries:
            if not scoped and g.id:
                continue
            scoped = [b for b in scoped if b.governorate_id == g.id]
            if not scoped:
                continue
            for b in scoped:
                b.employee_items = (
                    Employee.query.filter_by(branch_id=b.id, is_active=True)
                    .order_by(Employee.full_name)
                    .all()
                )
            entries.append((a.employee, scoped, sup, a, None))
        # Legacy account entries kept only for backward compatibility.
        candidate_entries = []
        if is_admin:
            candidate_entries = User.query.filter_by(is_active=True).order_by(User.full_name).all()
        elif is_manager_support:
            candidate_entries = []
            for su in supervisors:
                candidate_entries.extend(entries_for_supervisor(su, g.id))
        elif is_supervisor:
            candidate_entries = entries_for_supervisor(current, g.id)
        else:
            candidate_entries = [current]
        for u in candidate_entries:
            if 'المدخل الأول' not in actual_roles(u):
                continue
            ubids = {x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()}
            scoped = [b for b in bs if b.id in ubids]
            for b in scoped:
                b.employee_items = (
                    Employee.query.filter_by(branch_id=b.id, is_active=True)
                    .order_by(Employee.full_name)
                    .all()
                )
            sup_link = (
                SupervisorEntry.query.filter_by(entry_id=u.id)
                .order_by(SupervisorEntry.id.asc())
                .first()
            )
            sup = sup_link.supervisor if sup_link else None
            if is_supervisor and sup and (sup.id != current.id):
                continue
            if is_entry and u.id != current.id:
                continue
            if not sup and len({b.governorate_id for b in scoped}) == 1:
                sup = supervisor_for_governorate(g.id)
            entries.append((u, scoped, sup, None, Employee.query.filter_by(user_id=u.id).first()))
        counts = {
            b.id: Employee.query.filter_by(branch_id=b.id, is_active=True).count()
            for b in bs
        }
        for b in bs:
            if not hasattr(b, 'employee_items'):
                b.employee_items = (
                    Employee.query.filter_by(branch_id=b.id, is_active=True)
                    .order_by(Employee.full_name)
                    .all()
                )
        tree.append((g, bs, supervisors, entries, counts))
    govs_all = (
        Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if is_admin or is_manager_support
        else govs
    )
    admin_stats = None
    admin_audit = []
    if is_admin or is_manager_support:
        active_gov_count = Governorate.query.filter_by(is_active=True).count()
        active_branch_count = Branch.query.filter_by(is_active=True).count()
        active_employee_count = Employee.query.filter_by(is_active=True).count()
        active_users = User.query.filter_by(is_active=True).all()
        inactive_users = User.query.filter_by(is_active=False).count()
        supervisors_count = sum((1 for u in active_users if 'مشرف محافظة' in actual_roles(u)))
        support_count = sum(
            1
            for u in active_users
            if 'Manager Application Support' in actual_roles(u)
        )
        entry_assignments = EntryAssignment.query.filter_by(is_active=True).all()
        entry_assignment_ids = {a.id for a in entry_assignments}
        assigned_entry_branch_ids = (
            {
                x.branch_id
                for x in EntryAssignmentBranch.query.filter(EntryAssignmentBranch.entry_assignment_id.in_(entry_assignment_ids)).all()
            }
            if entry_assignment_ids
            else set()
        )
        unassigned_branch_count = max(0, active_branch_count - len(assigned_entry_branch_ids))
        role_account_count = RoleAccount.query.count()
        active_delegation_count = ApprovalDelegation.query.filter_by(is_active=True).count()
        entry_with_no_branch_count = sum(
            1 for a in entry_assignments
            if not EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).first()
        )
        supervisors_without_scope_count = sum(
            1 for u in active_users
            if 'مشرف محافظة' in actual_roles(u)
            and not UserGovernorate.query.filter_by(user_id=u.id).first()
        )
        must_change_password_count = sum(1 for u in active_users if u.must_change_password)
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
                'priority': priority, 'title': title, 'detail': detail,
                'action_url': action_url, 'action_label': action_label, 'prompt': prompt,
            })
        if not active_gov_count:
            add_admin_signal('urgent', 'لا توجد محافظات نشطة', 'الهيكل الإداري لا يمكن تشغيله بصورة طبيعية قبل وجود محافظة واحدة على الأقل.', '/governorates', 'إدارة المحافظات', 'راجع حالة المحافظات في النظام')
        if unassigned_branch_count:
            add_admin_signal('urgent', f'{unassigned_branch_count} فرع بلا مدخل أول', 'هناك فروع نشطة لم ترتبط بدور مدخل أول تنظيمي حتى الآن.', '/', 'تنفيذ من الرئيسية', 'ما الفروع التي تحتاج مدخل أول؟')
        if entry_with_no_branch_count:
            add_admin_signal('warning', f'{entry_with_no_branch_count} مدخل أول بلا فروع', 'التكليف موجود، لكن لا توجد له فروع مرتبطة.', '/', 'إدارة من الرئيسية', 'من هم المدخلون الأوائل الذين يحتاجون مراجعة؟')
        if supervisors_without_scope_count:
            add_admin_signal('warning', f'{supervisors_without_scope_count} مشرف بلا نطاق محافظة', 'حساب مشرف نشط موجود بدون محافظة مسندة إليه.', '/users', 'مراجعة المشرفين', 'راجع المشرفين الذين ليس لهم نطاق محافظة')
        if inactive_users:
            add_admin_signal('info', f'{inactive_users} حسابات معطلة', 'ليست مشكلة تشغيلية بحد ذاتها، لكنها تستحق المراجعة الدورية.', '/users', 'إدارة الحسابات', 'ما الحسابات المعطلة؟')
        if must_change_password_count:
            add_admin_signal('info', f'{must_change_password_count} حسابات مطالبة بتغيير كلمة المرور', 'يمكن متابعتها من إدارة الحسابات.', '/users', 'مراجعة الحسابات', 'ما الحسابات التي تحتاج تغيير كلمة المرور؟')
        if not admin_intelligence:
            add_admin_signal('ok', 'الوضع الإداري مستقر', 'لا توجد إشارات إدارية واضحة تحتاج تدخلاً الآن وفق البيانات الحالية.', '/audit', 'فتح سجل التدقيق', 'اعطني ملخصًا سريعًا لحالة النظام')
        if is_admin:
            admin_audit = Audit.query.order_by(Audit.created_at.desc()).limit(8).all()
    # تنفيذ تعيين/تغيير/إزالة المدخل الأول موجود في الرئيسية، لذلك لا
    # نجهز نموذجًا مكررًا داخل الإدارة.
    available_entry_employees = []
    entry_supervisors = [
        u
        for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
        if 'مشرف محافظة' in actual_roles(u)
    ]
    entry_supervisor_admin_choices = entry_supervisors if is_admin else []
    return render_template(
        'structure.html',
        tree=tree,
        is_admin=is_admin,
        is_supervisor=is_supervisor,
        is_manager_support=is_manager_support,
        admin_view=is_admin,
        is_entry=is_entry,
        govs_all=govs_all,
        selected_governorate=selected_gov,
        admin_stats=admin_stats,
        admin_intelligence=admin_intelligence,
        admin_audit=admin_audit,
        available_entry_employees=available_entry_employees,
        entry_supervisors=entry_supervisors,
        entry_supervisor_admin_choices=entry_supervisor_admin_choices,
    )


@bp.post('/entry-role/<int:employee_id>/branches')
@req
def update_organizational_entry_branches(employee_id):
    if not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    e = db.session.get(Employee, employee_id)
    a = (
        EntryAssignment.query.filter_by(employee_id=employee_id, is_active=True).first()
        if e
        else None
    )
    if not e or not a or (not e.is_active):
        abort(404)
    if 'مسؤول التطبيق' not in roles():
        if 'Manager Application Support' in roles():
            if not branch_ok(e.branch_id):
                abort(403)
        elif a.supervisor_id != me().id:
            abort(403)
    allowed = set(bids())
    chosen = {int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & allowed
    if not chosen:
        flash('يجب اختيار فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
        return redirect('/#entry-directory')
    occupied = {}
    for oa in (
        EntryAssignment.query.filter(EntryAssignment.is_active == True, EntryAssignment.id != a.id)
        .all()
    ):
        for link in EntryAssignmentBranch.query.filter_by(entry_assignment_id=oa.id).all():
            occupied[link.branch_id] = oa.employee_id
    conflict = [bid for bid in chosen if bid in occupied]
    if conflict:
        flash('يوجد فرع من الفروع المختارة مسند بالفعل إلى مدخل أول آخر.')
        return redirect('/#entry-directory')
    EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).delete()
    for bid in sorted(chosen):
        db.session.add(EntryAssignmentBranch(entry_assignment_id=a.id, branch_id=bid))
    log('ASSIGN', 'Employee', employee_id, 'تحديث فروع مسؤولية المدخل الأول من الصفحة الرئيسية')
    db.session.commit()
    flash('تم تحديث فروع مسؤولية المدخل الأول بنجاح.')
    return redirect('/#entry-directory')


@bp.post('/entry-role/<int:employee_id>/replace')
@req
def replace_organizational_entry_from_home(employee_id):
    if not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    old = db.session.get(Employee, employee_id)
    a = (
        EntryAssignment.query.filter_by(employee_id=employee_id, is_active=True).first()
        if old
        else None
    )
    new_id = request.form.get('new_entry_employee_id', '').strip()
    new = db.session.get(Employee, int(new_id)) if new_id.isdigit() else None
    if not old or not a or (not old.is_active):
        flash('الموظف المحدد ليس مدخلًا أول تنظيميًا حاليًا.')
        return redirect('/#entry-directory')
    if 'مسؤول التطبيق' not in roles():
        if 'Manager Application Support' in roles():
            if not branch_ok(old.branch_id):
                abort(403)
        elif a.supervisor_id != me().id:
            abort(403)
    if not new or not new.is_active or new.id == old.id or (not branch_ok(new.branch_id)):
        flash('اختر موظفًا بديلًا نشطًا داخل نطاقك.')
        return redirect('/#entry-directory')
    if EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first():
        flash('الموظف البديل لديه بالفعل دور مدخل أول. اختر موظفًا آخر.')
        return redirect('/#entry-directory')
    a.employee_id = new.id
    log(
        'REPLACE',
        'Employee',
        old.id,
        f'استبدال المدخل الأول بالموظف البديل {new.full_name} من الصفحة الرئيسية',
    )
    log(
        'REPLACE',
        'Employee',
        new.id,
        f'استلام دور المدخل الأول بدل {old.full_name} من الصفحة الرئيسية',
    )
    db.session.commit()
    flash(
        f'تم استبدال دور المدخل الأول بالموظف {new.full_name} مع نقل فروع المسؤولية والحفاظ على سجل الموظف القديم.',
    )
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
        flash('استبدال المدخل الأول يتم من الصفحة الرئيسية.')
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
                flash('يجب اختيار مدخل أول حالي وموظف بديل نشط مختلف عنه.')
                return redirect(url_for('structure.replacement', mode='entry'))
            old_a = EntryAssignment.query.filter_by(employee_id=old.id, is_active=True).first()
            new_a = EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first()
            if not old_a:
                flash('الموظف المحدد ليس مدخلًا أول تنظيميًا حاليًا.')
                return redirect(url_for('structure.replacement', mode='entry'))
            if new_a:
                flash('الموظف البديل لديه بالفعل دور مدخل أول. اختر موظفًا آخر.')
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
            log(
                'REPLACE',
                'Employee',
                old.id,
                f'استبدال المدخل الأول بالموظف البديل {new.full_name}',
            )
            log('REPLACE', 'Employee', new.id, f'استلام دور المدخل الأول بدل {old.full_name}')
            db.session.commit()
            flash(
                f'تم استبدال المدخل الأول ونقل الفروع والمسؤولية إلى {new.full_name} مع الحفاظ على سجل الموظف القديم.',
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
    eid = request.form.get('employee_id', '').strip()
    if not eid.isdigit():
        flash('اختر موظفًا مسجلًا أولًا.')
        return redirect('/#entry-directory')
    e = db.session.get(Employee, int(eid))
    if not e or not e.is_active:
        flash('الموظف غير موجود أو غير نشط.')
        return redirect('/#entry-directory')
    # التفويض نطاق تشغيلي مؤقت ولا ينقل ملكية التكليف التنظيمي.
    # لذلك لا يجوز للمشرف البديل إنشاء/إعادة إنشاء تكليف مدخل أول داخل
    # محافظة مفوضة فقط؛ يمكنه متابعة العمل، بينما يظل التغيير الهيكلي
    # للمشرف الأصلي أو مسؤول التطبيق.
    if 'مشرف محافظة' in roles() and 'مسؤول التطبيق' not in roles():
        employee_gid = e.branch.governorate_id if e.branch else None
        if employee_gid in delegated_gov_ids(me()) and employee_gid not in user_gov_ids(me()):
            abort(403)
    existing_entry = EntryAssignment.query.filter_by(employee_id=e.id).first()
    if existing_entry and existing_entry.is_active:
        flash('هذا الموظف لديه بالفعل دور المدخل الأول التنظيمي.')
        return redirect('/#entry-directory')
    if 'مسؤول التطبيق' in roles() or 'Manager Application Support' in roles():
        sup_id = request.form.get('supervisor_id', '').strip()
        sup = db.session.get(User, int(sup_id)) if sup_id.isdigit() else None
        if not sup or 'مشرف محافظة' not in actual_roles(sup) or (not sup.is_active):
            flash('اختر المشرف المسؤول.')
            return redirect('/#entry-directory')
        if 'Manager Application Support' in roles():
            selected = scope_governorate_id()
            if not selected or int(selected) not in user_gov_ids(sup):
                abort(403)
    else:
        sup = me()
        if e.branch.governorate_id not in user_gov_ids(sup):
            abort(403)
    # الموظف نفسه يجب أن يكون داخل نفس النطاق التنظيمي للجهة التي سيُسند إليها؛
    # لا يكفي أن تكون الفروع المختارة داخل نطاق المشرف.
    if 'مسؤول التطبيق' not in roles() and (not e.branch or not branch_ok(e.branch_id)):
        abort(403)

    branch_ids = {int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
    allowed = (
        set(bids())
        if 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles()
        else {b.id for b in Branch.query.filter_by(is_active=True).all()}
    )
    if 'مسؤول التطبيق' in roles() or 'Manager Application Support' in roles():
        if 'Manager Application Support' in roles():
            selected = scope_governorate_id()
            allowed_govs = {int(selected)} if selected else set()
        else:
            allowed_govs = user_gov_ids(sup)
        allowed = {
            b.id
            for b in Branch.query.filter(Branch.id.in_(allowed), Branch.governorate_id.in_(allowed_govs), Branch.is_active == True).all()
        }
    branch_ids &= allowed
    if not branch_ids:
        branch_ids = {e.branch_id} if e.branch_id in allowed else set()
    if not branch_ids:
        flash('اختر فرع مسؤولية واحدًا على الأقل ضمن نطاق المشرف المسؤول.')
        return redirect('/#entry-directory')
    # لا يُسمح بفرع مسؤولية مرتبط بمدخل تنظيمي آخر.
    taken = {
        x.branch_id
        for x in EntryAssignmentBranch.query.join(EntryAssignment).filter(EntryAssignment.is_active == True).all()
    }
    if branch_ids & taken:
        flash('يوجد فرع من الفروع المختارة مسند بالفعل إلى مدخل أول آخر.')
        return redirect('/#entry-directory')
    if existing_entry:
        a = existing_entry
        a.supervisor_id = sup.id
        a.is_active = True
        EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).delete()
    else:
        a = EntryAssignment(employee_id=e.id, supervisor_id=sup.id, is_active=True)
        db.session.add(a)
        db.session.flush()
    for bid in branch_ids:
        db.session.add(EntryAssignmentBranch(entry_assignment_id=a.id, branch_id=bid))
    log('ROLE_CHANGE', 'Employee', e.id, 'إضافة دور المدخل الأول التنظيمي بدون حساب دخول')
    db.session.commit()
    flash('تمت إضافة دور المدخل الأول التنظيمي. لم يتم إنشاء حساب أو اسم مستخدم للمدخل.')
    return redirect('/#entry-directory')


@bp.post('/entry-role/<int:employee_id>/remove')
@req
def remove_organizational_entry_role(employee_id):
    e = db.session.get(Employee, employee_id)
    a = organizational_entry_for_employee(e) if e else None
    if not a:
        abort(404)
    if 'مسؤول التطبيق' not in roles():
        if 'Manager Application Support' in roles():
            if not branch_ok(e.branch_id):
                abort(403)
        elif 'مشرف محافظة' not in roles() or a.supervisor_id != me().id:
            abort(403)
    a.is_active = False
    db.session.commit()
    log('ROLE_CHANGE', 'Employee', employee_id, 'إزالة دور المدخل الأول التنظيمي')
    db.session.commit()
    flash('تمت إزالة دور المدخل الأول التنظيمي، وأصبحت فروع مسؤوليته متاحة لإسنادها من جديد.')
    return redirect('/#entry-directory')
