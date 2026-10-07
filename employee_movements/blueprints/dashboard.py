"""Home dashboard and live employee status."""

from datetime import date, timedelta

from flask import abort, Blueprint, redirect, render_template, request, url_for

from ..access import actual_roles, bids, branch_ok, delegated_gov_ids, gids, has_role, me, req, roles, scope_governorate_id, user_gov_ids
from ..assignments import (
    employees_effectively_in_branches,
    organizational_entries_for_supervisor,
    organizational_entry_for_employee,
    resolve_current_movement,
    supervisor_for_entry,
)
from ..constants import LEAVE_TYPES, MOVEMENT_TYPES
from ..extensions import db
from ..models import (
    Branch,
    Employee,
    EntryAssignment,
    EntryAssignmentBranch,
    Governorate,
    Movement,
    User,
    UserBranch,
    UserGovernorate,
)

bp = Blueprint('dashboard', __name__)


def current_employee_status_rows(branch_ids, today):
    """Build the live status board with one employee query and one movement query.

    Priority is: leave -> dated assignment -> open assignment -> today's permission.
    Employees without a current movement are intentionally omitted from this board.
    """
    if not branch_ids:
        return []

    employees = employees_effectively_in_branches(branch_ids, today)
    if not employees:
        return []

    employee_ids = [e.id for e in employees]
    moves = (
        Movement.query.filter(Movement.employee_id.in_(employee_ids), Movement.is_active == True)
        .order_by(Movement.created_at.desc(), Movement.id.desc())
        .all()
    )
    by_employee = {}
    for movement in moves:
        by_employee.setdefault(movement.employee_id, []).append(movement)

    rows = []
    for e in employees:
        employee_moves = by_employee.get(e.id, [])
        current = resolve_current_movement(employee_moves, today)
        state = None
        place = e.branch.name if e.branch else '—'
        until = None
        detail = ''
        display_branch = e.branch

        if current and current.movement_type == 'إجازة':
            state = 'إجازة'
            place = current.leave_type or 'إجازة'
            until = current.to_date
            detail = 'من {} إلى {}'.format(current.from_date.strftime('%d/%m/%Y'), current.to_date.strftime('%d/%m/%Y'))
        elif current and current.movement_type == 'انتداب' and current.to_date is not None:
            state = 'انتداب'
            place = current.destination.name if current.destination else 'جهة الانتداب غير محددة'
            until = current.to_date
            detail = 'من {} إلى {}'.format(current.from_date.strftime('%d/%m/%Y'), current.to_date.strftime('%d/%m/%Y'))
            display_branch = current.destination or e.branch
        elif current and current.movement_type == 'انتداب':
            state = 'انتداب مفتوح'
            place = current.destination.name if current.destination else 'جهة الانتداب غير محددة'
            detail = 'من {} — مفتوح'.format(current.from_date.strftime('%d/%m/%Y'))
            display_branch = current.destination or e.branch
        elif current and current.movement_type == 'إذن':
            state = 'إذن'
            place = e.branch.name if e.branch else '—'
            until = current.permission_date
            detail = 'بتاريخ {}'.format(current.permission_date.strftime('%d/%m/%Y'))

        if current is None:
            continue

        remaining = (until - today).days if until else None
        rows.append(
            {
                'employee': e,
                'state': state,
                'place': place,
                'until': until,
                'detail': detail,
                'remaining': remaining,
                'movement': current,
                'ending_notice': bool(until and until <= today + timedelta(days=1)),
                'from_date': (
                    current.from_date
                    if current and current.movement_type in ('إجازة', 'انتداب')
                    else current.permission_date if current else None
                ),
                'to_date': (
                    current.to_date
                    if current and current.movement_type in ('إجازة', 'انتداب')
                    else None
                ),
                'display_branch': display_branch,
            },
        )

    def status_rank(r):
        order = {'إجازة': 1, 'انتداب': 2, 'انتداب مفتوح': 3, 'إذن': 4}
        return order.get(r['state'], 9)

    rows.sort(key=lambda r: (status_rank(r), r['until'] or date.max, r['employee'].full_name))
    return rows


@bp.get('/')
@req
def home():
    current_user = me()
    effective = roles(current_user)
    is_manager_support = 'Manager Application Support' in effective
    is_scope_user = (
        'مسؤول التطبيق' in effective
        or 'مشرف محافظة' in effective
        or is_manager_support
    )
    selected_manager_gov = scope_governorate_id() if is_scope_user else None
    bs = set(bids())
    today = date.today()
    tomorrow = today + timedelta(days=1)
    # بحث الموظف من الصفحة الرئيسية مستقل عن نطاق العمل: البحث متاح في كل المحافظات.
    movement_governorate_id = request.args.get('movement_governorate_id', '').strip()
    movement_branch_id = request.args.get('movement_branch_id', '').strip()
    movement_name_query = (request.args.get('movement_name') or '').strip()
    movement_employee_id = request.args.get('employee_id', '').strip()
    movement_employee = None
    movement_employee_matches = []
    movement_employee_moves = []
    movement_employee_last = {}
    search_gov_id = int(movement_governorate_id) if movement_governorate_id.isdigit() else None
    # بحث الموظف في الصفحة الرئيسية مستقل تمامًا عن نطاق المشرف: كل المحافظات متاحة للجميع.
    search_branch_id = int(movement_branch_id) if movement_branch_id.isdigit() else None
    if search_gov_id:
        sg = db.session.get(Governorate, search_gov_id)
        if not sg or not sg.is_active:
            search_gov_id = None
    if search_branch_id:
        sb = db.session.get(Branch, search_branch_id)
        if not sb or not sb.is_active or (search_gov_id and sb.governorate_id != search_gov_id):
            search_branch_id = None
        elif not search_gov_id:
            search_gov_id = sb.governorate_id

    # اختيار المحافظة يحدد سياق العمل فقط؛ لا يبدأ بحث الموظفين تلقائيًا.
    # البحث الفعلي يبدأ عند إدخال اسم/كود أو اختيار فرع والضغط على بحث.
    search_branch_ids = set()
    if search_gov_id:
        search_branch_ids = {
            b.id
            for b in Branch.query.filter_by(governorate_id=search_gov_id, is_active=True).all()
        }
    if search_branch_id:
        search_branch_ids = {search_branch_id}
    candidates = []
    if movement_name_query or search_branch_id:
        q = Employee.query.filter(Employee.is_active == True)
        if search_branch_ids:
            q = q.filter(Employee.branch_id.in_(search_branch_ids))
        if movement_name_query:
            nq = f'%{movement_name_query}%'
            q = q.filter(db.or_(Employee.full_name.ilike(nq), Employee.job_code.ilike(nq)))
        candidates = q.order_by(Employee.full_name.asc()).limit(50).all()
        movement_employee_matches = candidates

    if movement_employee_id.isdigit():
        candidate = db.session.get(Employee, int(movement_employee_id))
        if candidate and candidate.is_active:
            if (
                (
                    not search_gov_id
                    or candidate.branch and candidate.branch.governorate_id == search_gov_id
                )
                and (not search_branch_id or candidate.branch_id == search_branch_id)
            ):
                movement_employee = candidate
    elif len(movement_employee_matches) == 1:
        movement_employee = movement_employee_matches[0]
    movement_employee_in_scope = bool(movement_employee and branch_ok(movement_employee.branch_id)) if movement_employee else False

    if movement_employee:
        movement_employee_moves = (
            Movement.query.filter_by(employee_id=movement_employee.id, is_active=True)
            .order_by(Movement.id.desc())
            .all()
        )
        movement_employee_last = {
            k: next((m for m in movement_employee_moves if m.movement_type == k), None)
            for k in MOVEMENT_TYPES
        }
    pending = []
    ending = []
    approved_count = 0
    current_status_rows = []
    current_status_summary = {
        'present': 0,
        'leave': 0,
        'assignment': 0,
        'open_assignment': 0,
        'permission': 0,
        'follow_up': 0,
    }

    # Governorates visible to the current effective role.
    visible_govs = (
        (
            Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
            .order_by(Governorate.name.asc())
            .all()
        )
        if gids()
        else []
    )

    # المدخل الأول هنا بند تنظيمي فقط: لا يحتاج حساب دخول.
    entry_rows = []
    entry_directory_branch_ids = set()
    if 'مشرف محافظة' in effective or 'مسؤول التطبيق' in effective or is_manager_support:
        if is_manager_support:
            supervisors = [
                u
                for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
                if 'مشرف محافظة' in actual_roles(u) and any((x.governorate_id in ({int(selected_manager_gov)} if selected_manager_gov else set()) for x in UserGovernorate.query.filter_by(user_id=u.id).all()))
            ]
        else:
            supervisors = (
                [me()]
                if 'مشرف محافظة' in effective and 'مسؤول التطبيق' not in effective
                else [
                    u
                    for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
                    if 'مشرف محافظة' in actual_roles(u)
                ]
            )
            # التفويض يمنح نطاقًا تشغيليًا مؤقتًا فقط. لذلك يرى المشرف البديل
            # تكليفات المدخلين داخل المحافظة المفوضة للمتابعة، لكن ملكية التكليف
            # تظل للمشرف الأصلي ولا تنتقل إليه.
            if 'مشرف محافظة' in effective:
                delegated_ids = delegated_gov_ids(current_user)
                if delegated_ids:
                    owned_ids = {u.id for u in supervisors if u}
                    delegated_branch_ids = {
                        b.id
                        for b in Branch.query.filter(
                            Branch.governorate_id.in_(delegated_ids),
                            Branch.is_active == True,
                        ).all()
                    }
                    delegated_owner_ids = {
                        a.supervisor_id
                        for a in EntryAssignment.query.filter_by(is_active=True).all()
                        for link in EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).all()
                        if link.branch_id in delegated_branch_ids
                    }
                    extra_supervisors = (
                        User.query.filter(
                            User.id.in_(delegated_owner_ids - owned_ids),
                            User.is_active == True,
                        )
                        .order_by(User.full_name.asc())
                        .all()
                    )
                    supervisors = supervisors + extra_supervisors
        seen = set()
        for sup in supervisors:
            for (a, scoped_all) in organizational_entries_for_supervisor(sup):
                scoped = [b for b in scoped_all if b.id in bs]
                if not scoped or a.id in seen:
                    continue
                seen.add(a.id)
                branch_groups = []
                for b in scoped:
                    emps = (
                        Employee.query.filter(
                            Employee.branch_id == b.id,
                            Employee.is_active == True,
                        )
                        .order_by(Employee.full_name.asc())
                        .all()
                    )
                    branch_groups.append({'branch': b, 'employees': emps})
                entry_directory_branch_ids.update((b.id for b in scoped))
                gov_ids_for_entry = {x['branch'].governorate_id for x in branch_groups}
                gov_names = (
                    [
                        gobj.name
                        for gobj in Governorate.query.filter(Governorate.id.in_(gov_ids_for_entry), Governorate.is_active == True).order_by(Governorate.name.asc()).all()
                    ]
                    if gov_ids_for_entry
                    else []
                )
                # بيانات أزرار إدارة الفروع والاستبدال داخل الصفحة الرئيسية.
                allowed_branch_objs = (
                    (
                        Branch.query.filter(Branch.id.in_(bs), Branch.is_active == True)
                        .order_by(Branch.name.asc())
                        .all()
                    )
                    if bs
                    else []
                )
                occupied_branch_ids = set()
                for oa in (
                    EntryAssignment.query.filter(
                        EntryAssignment.is_active == True,
                        EntryAssignment.id != a.id,
                    )
                    .all()
                ):
                    occupied_branch_ids.update(
                        x.branch_id
                        for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=oa.id).all()
                    )
                assignment_branch_ids = {
                    x.branch_id
                    for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).all()
                }
                available_entry_branches = [
                    b
                    for b in allowed_branch_objs
                    if b.id not in occupied_branch_ids or b.id in assignment_branch_ids
                ]
                entry_employee_ids = {
                    x.employee_id
                    for x in EntryAssignment.query.filter_by(is_active=True).all()
                }
                replace_targets = (
                    (
                        Employee.query.filter(
                            Employee.is_active == True,
                            Employee.branch_id.in_(bs),
                        )
                        .order_by(Employee.full_name.asc())
                        .all()
                    )
                    if bs
                    else []
                )
                replace_targets = [
                    x
                    for x in replace_targets
                    if x.id not in entry_employee_ids and x.id != a.employee_id
                ]
                branch_employee_ids = [e.id for bg in branch_groups for e in bg['employees']]
                today_movement_count = (
                    (
                        Movement.query.filter(
                            Movement.employee_id.in_(branch_employee_ids),
                            Movement.is_active == True,
                            db.or_(
                                Movement.permission_date == today,
                                db.and_(
                                    Movement.from_date != None,
                                    Movement.from_date <= today,
                                    db.or_(Movement.to_date == None, Movement.to_date >= today),
                                ),
                            ),
                        )
                        .count()
                    )
                    if branch_employee_ids
                    else 0
                )
                alert_count = (
                    (
                        Movement.query.filter(
                            Movement.employee_id.in_(branch_employee_ids),
                            Movement.is_active == True,
                            Movement.to_date == tomorrow,
                            Movement.movement_type.in_(['إجازة', 'انتداب']),
                        )
                        .count()
                    )
                    if branch_employee_ids
                    else 0
                )
                entry_rows.append(
                    {
                        'assignment': a,
                        'employee': a.employee,
                        'branches': branch_groups,
                        'governorates': gov_names,
                        'supervisor': sup,
                        'available_branches': available_entry_branches,
                        'assignment_branch_ids': assignment_branch_ids,
                        'replace_targets': replace_targets,
                        'employee_count': len(branch_employee_ids),
                        'today_movement_count': today_movement_count,
                        'alert_count': alert_count,
                        # المشرف الأصلي يملك التكليف التنظيمي. المشرف البديل عبر
                        # التفويض يستطيع المتابعة التشغيلية فقط ولا يعدّل الملكية.
                        'can_manage': (
                            'مسؤول التطبيق' in effective
                            or 'Manager Application Support' in effective
                            or (sup.id == current_user.id and a.supervisor_id == current_user.id)
                        ),
                    },
                )
    else:
        # Legacy accounts remain visible only as compatibility records. New organizational entries never create them.
        if 'المدخل الأول' in effective:
            # Legacy account compatibility; not used for new assignments.
            u = me()
            scoped = [
                b
                for b in Branch.query.join(UserBranch, UserBranch.branch_id == Branch.id).filter(UserBranch.user_id == u.id, Branch.is_active == True).order_by(Branch.name).all()
                if b.id in bs
            ]
            if scoped:
                groups = [
                    {'branch': b, 'employees': Employee.query.filter(Employee.branch_id == b.id, Employee.is_active == True).order_by(Employee.full_name).all()}
                    for b in scoped
                ]
                entry_rows = [
                    {
                        'assignment': None,
                        'employee': Employee.query.filter_by(user_id=u.id).first(),
                        'branches': groups,
                        'governorates': [],
                        'supervisor': supervisor_for_entry(u),
                        'employee_count': sum((len(g['employees']) for g in groups)),
                        'today_movement_count': 0,
                        'alert_count': 0,
                    },
                ]

    # فروع لوحة «المدخلون الأوائل» المستخدمة في فلتر البحث بالفرع.
    entry_directory_branches = (
        (
            Branch.query.filter(Branch.id.in_(entry_directory_branch_ids), Branch.is_active == True)
            .order_by(Branch.name.asc())
            .all()
        )
        if entry_directory_branch_ids
        else []
    )

    # بيانات إضافة المدخل الأول التنظيمي في الصفحة الرئيسية يجب أن تُبنى داخل
    # نفس نطاق المستخدم؛ لا تعتمد على متغيرات غير مُمررة للقالب.
    available_entry_employees = []
    available_entry_employee_is_supervisor = {}
    entry_supervisors = []
    available_entry_branches = []
    if 'مسؤول التطبيق' in effective or 'مشرف محافظة' in effective or is_manager_support:
        delegated_only_govs = delegated_gov_ids(current_user) if 'مشرف محافظة' in effective else set()
        permanent_govs = user_gov_ids(current_user) if 'مشرف محافظة' in effective else set()
        delegated_only = bool(
            'مشرف محافظة' in effective
            and selected_manager_gov
            and int(selected_manager_gov) in delegated_only_govs
            and int(selected_manager_gov) not in permanent_govs
        )
        allowed_branch_set = set(bs) if not delegated_only else set()
        if allowed_branch_set:
            candidates = (
                Employee.query.filter(
                    Employee.is_active == True,
                    Employee.branch_id.in_(allowed_branch_set),
                )
                .order_by(Employee.full_name.asc())
                .all()
            )
            # جميع الموظفين النشطين داخل النطاق مؤهلون للتكليف التنظيمي؛ نستبعد فقط من لديه تكليف فعال.
            available_entry_employees = []
            for e in candidates:
                if organizational_entry_for_employee(e):
                    continue
                linked_user = db.session.get(User, e.user_id) if e.user_id else None
                # كل موظف نشط داخل النطاق مؤهل للتكليف التنظيمي؛ لا يحتاج إلى حساب دخول أو دور UserRole.
                available_entry_employees.append(e)
            available_entry_employee_is_supervisor = {
                e.id: bool(e.user_id and 'مشرف محافظة' in actual_roles(db.session.get(User, e.user_id)))
                for e in available_entry_employees
            }
            occupied_entry_branch_ids = set()
            for oa in EntryAssignment.query.filter_by(is_active=True).all():
                occupied_entry_branch_ids.update(
                    x.branch_id
                    for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=oa.id).all()
                )
            available_entry_branches = [
                b
                for b in Branch.query.filter(Branch.id.in_(allowed_branch_set), Branch.is_active == True).order_by(Branch.name.asc()).all()
                if b.id not in occupied_entry_branch_ids
            ]
        if 'مسؤول التطبيق' in effective:
            entry_supervisors = [
                u
                for u in User.query.filter_by(is_active=True).order_by(User.full_name.asc()).all()
                if 'مشرف محافظة' in actual_roles(u)
            ]
        elif is_manager_support:
            entry_supervisors = supervisors
        else:
            entry_supervisors = [me()]
        # لا نعرض إنشاء تكليف جديد في محافظة مفوضة فقط؛ التفويض لا ينقل
        # الملكية التنظيمية للمشرف البديل.
        if 'مشرف محافظة' in effective and delegated_only:
            available_entry_employees = []
            available_entry_branches = []

    if bs:
        # الحركات أصبحت معلومات تشغيلية مباشرة وليست دورة اعتماد.
        if has_role('مشرف محافظة', 'مسؤول التطبيق', 'المدخل الأول', 'Manager Application Support'):
            all_status_rows = current_employee_status_rows(bs, today)
            # الصفحة الرئيسية تعرض الحركات الحالية فقط؛ الموظف المتواجد طبيعيًا لا
            # يظهر في قائمة الحالات التشغيلية حتى لا يطغى على الحالات التي تحتاج متابعة.
            current_status_rows = [
                r for r in all_status_rows
                if r['state'] in ('إجازة', 'انتداب', 'انتداب مفتوح', 'إذن')
            ]
            current_status_summary = {
                'present': 0,
                'leave': sum((1 for r in current_status_rows if r['state'] == 'إجازة')),
                'assignment': sum((1 for r in current_status_rows if r['state'] == 'انتداب')),
                'open_assignment': sum(
                    1 for r in current_status_rows if r['state'] == 'انتداب مفتوح'
                ),
                'permission': sum((1 for r in current_status_rows if r['state'] == 'إذن')),
                'follow_up': sum((1 for r in current_status_rows if r['ending_notice'])),
            }
        # ending_notice is calculated while building the current-status rows.
        # تبقى بيانات الاعتماد القديمة قابلة للعرض في السجلات القديمة، لكن لا تُستخدم
        # لتحديد حالة الموظف الحالية.
        ending = []

    # قوائم الصفحة الرئيسية لا تعرض إلا المحافظات الواقعة ضمن نطاق الدور الحالي.
    home_movement_gov_ids = set(gids())
    home_movement_governorates = (
        (
            Governorate.query.filter(
                Governorate.id.in_(home_movement_gov_ids),
                Governorate.is_active == True,
            )
            .order_by(Governorate.name.asc())
            .all()
        )
        if home_movement_gov_ids
        else []
    )
    # جهة الانتداب قد تكون في محافظة مختلفة؛ هذا الاختيار لا يمنح المستخدم نطاقًا تشغيليًا عليها.
    home_movement_branches = Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()

    # بحث الموظف في الرئيسية متاح لكل المحافظات، حتى لو كان نطاق العمل الحالي محافظة واحدة.
    return render_template(
        'home.html',
        g=len(visible_govs),
        b=len(bs),
        e=(
            Employee.query.filter(Employee.branch_id.in_(bs), Employee.is_active == True).count()
            if bs
            else 0
        ),
        visible_govs=visible_govs,
        entry_rows=entry_rows,
        pending=pending,
        ending=ending,
        approved_count=approved_count,
        current_status_rows=current_status_rows,
        current_status_summary=current_status_summary,
        available_entry_employees=available_entry_employees,
        available_entry_employee_is_supervisor=available_entry_employee_is_supervisor,
        available_entry_branches=available_entry_branches,
        entry_directory_branches=entry_directory_branches,
        entry_supervisors=entry_supervisors,
        today=today,
        tomorrow=tomorrow,
        is_admin=has_role('مسؤول التطبيق'),
        is_manager_support=is_manager_support,
        manager_governorates=(
            Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()
            if is_manager_support
            else []
        ),
        selected_manager_gov=selected_manager_gov,
        movement_search_governorates=(
            Governorate.query.filter_by(is_active=True)
            .order_by(Governorate.name.asc())
            .all()
        ),
        movement_search_branches=(
            (
                Branch.query.filter(
                    Branch.governorate_id == search_gov_id,
                    Branch.is_active == True,
                )
                .order_by(Branch.name.asc())
                .all()
            )
            if search_gov_id
            else []
        ),
        movement_search_all_branches=(
            Branch.query.filter_by(is_active=True)
            .order_by(Branch.name.asc())
            .all()
        ),
        home_movement_governorates=home_movement_governorates,
        home_movement_branches=home_movement_branches,
        movement_search_employees=(
            Employee.query.filter_by(is_active=True)
            .order_by(Employee.full_name.asc())
            .all()
        ),
        movement_employee=movement_employee,
        movement_employee_in_scope=movement_employee_in_scope,
        movement_employee_moves=movement_employee_moves,
        movement_employee_last=movement_employee_last,
        movement_employee_matches=movement_employee_matches,
        movement_governorate_id=movement_governorate_id,
        movement_branch_id=movement_branch_id,
        movement_name_query=movement_name_query,
        movement_employee_id=int(movement_employee_id) if movement_employee_id.isdigit() else None,
        movement_types=MOVEMENT_TYPES,
        leave_types=LEAVE_TYPES,
        is_delegated_supervisor=bool(
            'مشرف محافظة' in effective
            and selected_manager_gov
            and int(selected_manager_gov) in delegated_gov_ids(current_user)
            and int(selected_manager_gov) not in user_gov_ids(current_user)
        ),
    )


@bp.get('/api/entry-ids/<int:gid>')
@req
def entry_ids_for_governorate(gid):
    # لا نكشف أي مدخلين خارج نطاق المستخدم الحالي.
    if gid not in set(gids()):
        abort(403)
    bids_g = {b.id for b in Branch.query.filter_by(governorate_id=gid, is_active=True).all()}
    if not bids_g:
        return {'entry_ids': []}
    ids = {x.user_id for x in UserBranch.query.filter(UserBranch.branch_id.in_(bids_g)).all()}
    return {'entry_ids': sorted(ids)}


@bp.get('/review')
@req
def review():
    return redirect(url_for('movements.movements'))
