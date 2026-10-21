"""Home dashboard and live employee status."""

from datetime import date, timedelta

from flask import abort, Blueprint, redirect, render_template, request, url_for
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import joinedload

from ..access import actual_roles, bids, branch_ok, can, can_view_movement, delegated_gov_ids, gids, has_role, me, readable_branch_ids, req, roles, scope_governorate_id, user_gov_ids
from ..assignments import (
    employees_effectively_in_branches,
    organizational_entries_for_supervisor,
    organizational_entry_for_employee,
    entry_responsible_names_by_branch,
    entry_responsible_label,
    latest_assignment_summaries,
    supervisor_for_entry,
)
from ..constants import LEAVE_TYPES, MOVEMENT_TYPES
from ..extensions import db
from ..movement_state import assignment_open_filter
from ..search import normalize_search_text
from ..services.entity_matching import (
    employee_search_filter, rank_scoped_employee_suggestions,
    resolve_scoped_employee_identity,
)
from ..models import (
    Branch,
    BranchNameAlias,
    Employee,
    EmployeeNameAlias,
    TicketEmployeeCodeAlias,
    EntryAssignment,
    EntryAssignmentBranch,
    Governorate,
    GovernorateNameAlias,
    Movement,
    User,
    UserBranch,
    UserGovernorate,
)

bp = Blueprint('dashboard', __name__)


def current_employee_status_rows(branch_ids, today):
    """Build the live status board without loading every employee's history.

    The database returns one current movement per employee. Ranking matches the
    canonical business priority used by ``resolve_current_movement``: leave,
    dated assignment, open assignment, then today's permission; newest wins only
    within the same priority. This keeps dashboard memory use proportional to
    current rows, not the employee's full historical movement count.
    """
    if not branch_ids:
        return []

    employees = employees_effectively_in_branches(branch_ids, today)
    if not employees:
        return []

    employee_ids = [e.id for e in employees]
    current_candidate = or_(
        and_(
            Movement.movement_type == 'إجازة',
            Movement.from_date.is_not(None),
            Movement.to_date.is_not(None),
            Movement.from_date <= today,
            Movement.to_date >= today,
        ),
        and_(
            Movement.movement_type == 'انتداب',
            assignment_open_filter(Movement),
            Movement.from_date.is_not(None),
            Movement.from_date <= today,
            or_(Movement.to_date.is_(None), Movement.to_date >= today),
        ),
        and_(Movement.movement_type == 'إذن', Movement.permission_date == today),
    )
    current_priority = case(
        (Movement.movement_type == 'إجازة', 1),
        (and_(Movement.movement_type == 'انتداب', Movement.to_date.is_not(None)), 2),
        (Movement.movement_type == 'انتداب', 3),
        else_=4,
    )
    ranked_movements = (
        db.session.query(
            Movement.id.label('movement_id'),
            Movement.employee_id.label('employee_id'),
            func.row_number().over(
                partition_by=Movement.employee_id,
                order_by=(current_priority.asc(), Movement.created_at.desc(), Movement.id.desc()),
            ).label('current_rank'),
        )
        .filter(
            Movement.employee_id.in_(employee_ids),
            Movement.is_active == True,
            current_candidate,
        )
        .subquery()
    )
    current_movements = (
        Movement.query
        .join(ranked_movements, Movement.id == ranked_movements.c.movement_id)
        .filter(ranked_movements.c.current_rank == 1)
        .options(joinedload(Movement.destination).joinedload(Branch.governorate))
        .all()
    )
    current_by_employee = {movement.employee_id: movement for movement in current_movements}

    rows = []
    for e in employees:
        current = current_by_employee.get(e.id)
        if current is None:
            continue

        state = None
        place = e.branch.name if e.branch else '—'
        until = None
        detail = ''
        display_branch = e.branch

        if current.movement_type == 'إجازة':
            state = 'إجازة'
            place = current.leave_type or 'إجازة'
            until = current.to_date
            detail = 'من {} إلى {}'.format(current.from_date.strftime('%d/%m/%Y'), current.to_date.strftime('%d/%m/%Y'))
        elif current.movement_type == 'انتداب' and current.to_date is not None:
            state = 'انتداب'
            place = current.destination.name if current.destination else 'جهة الانتداب غير محددة'
            until = current.to_date
            detail = 'من {} إلى {}'.format(current.from_date.strftime('%d/%m/%Y'), current.to_date.strftime('%d/%m/%Y'))
            display_branch = current.destination or e.branch
        elif current.movement_type == 'انتداب':
            state = 'انتداب مفتوح'
            place = current.destination.name if current.destination else 'جهة الانتداب غير محددة'
            detail = 'من {} — مفتوح'.format(current.from_date.strftime('%d/%m/%Y'))
            display_branch = current.destination or e.branch
        elif current.movement_type == 'إذن':
            state = 'إذن'
            place = e.branch.name if e.branch else '—'
            until = current.permission_date
            detail = 'بتاريخ {}'.format(current.permission_date.strftime('%d/%m/%Y'))

        remaining = (until - today).days if until else None
        rows.append({
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
                if current.movement_type in ('إجازة', 'انتداب')
                else current.permission_date
            ),
            'to_date': current.to_date if current.movement_type in ('إجازة', 'انتداب') else None,
            'display_branch': display_branch,
        })

    def status_rank(row):
        order = {'إجازة': 1, 'انتداب': 2, 'انتداب مفتوح': 3, 'إذن': 4}
        return order.get(row['state'], 9)

    rows.sort(key=lambda row: (status_rank(row), row['until'] or date.max, row['employee'].full_name))
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
    # `bs` is the selected operational work-scope for assignments and writes.
    # Read-only employee/movement summaries use all active branches, regardless
    # of whether an Admin/Manager has picked a work governorate yet.
    bs = set(bids())
    read_branch_ids = set(readable_branch_ids())
    today = date.today()
    tomorrow = today + timedelta(days=1)
    # بحث الموظف من الصفحة الرئيسية مستقل عن نطاق العمل: البحث متاح في كل المحافظات.
    movement_governorate_id = (request.args.get('movement_governorate_id', '') or '').strip()
    movement_branch_id = (request.args.get('movement_branch_id', '') or '').strip()
    movement_name_query = (request.args.get('movement_name') or '').strip()
    movement_employee_id = (request.args.get('employee_id', '') or '').strip()
    movement_employee = None
    movement_employee_matches = []
    movement_employee_match_reasons = {}
    movement_employee_moves = []
    movement_employee_last = {}
    movement_search_invalid = bool(movement_employee_id and not movement_employee_id.isdigit())
    movement_search_error = ''
    search_gov_id = int(movement_governorate_id) if movement_governorate_id.isdigit() else None
    search_branch_id = int(movement_branch_id) if movement_branch_id.isdigit() else None

    # Invalid explicit filters must never be ignored, because that would broaden
    # a scoped query into a global one. Homepage identity search itself is global.
    if movement_governorate_id and search_gov_id is None:
        movement_search_invalid = True
    elif search_gov_id:
        sg = db.session.get(Governorate, search_gov_id)
        if not sg or not sg.is_active:
            movement_search_invalid = True
    if movement_branch_id and search_branch_id is None:
        movement_search_invalid = True
    elif search_branch_id:
        sb = db.session.get(Branch, search_branch_id)
        if not sb or not sb.is_active or not sb.governorate or not sb.governorate.is_active:
            movement_search_invalid = True
        elif search_gov_id and sb.governorate_id != search_gov_id:
            movement_search_invalid = True
        else:
            search_gov_id = sb.governorate_id
    normalized_movement_query = normalize_search_text(movement_name_query)
    if len(movement_name_query) > 120:
        movement_search_invalid = True
        movement_search_error = 'عبارة البحث طويلة جدًا؛ الحد الأقصى 120 حرفًا.'
    elif movement_name_query and len(normalized_movement_query) < 2 and not search_branch_id:
        movement_search_invalid = True
        movement_search_error = 'اكتب حرفين على الأقل، أو اختر فرعًا لعرض موظفيه.'
    if movement_search_invalid and not movement_search_error:
        movement_search_error = 'تعذر تطبيق المرشح المحدد. اختر محافظة وفرعًا صالحين ثم أعد البحث.'

    search_branch_ids = set()
    if not movement_search_invalid and search_gov_id:
        search_branch_ids = {
            b.id for b in Branch.query.filter_by(governorate_id=search_gov_id, is_active=True).all()
            if b.governorate and b.governorate.is_active
        }
    if not movement_search_invalid and search_branch_id:
        search_branch_ids = {search_branch_id}

    # Choosing only a governorate is a scope/filter selection, not a request to
    # dump every employee. A name/code or a branch must start the actual search.
    candidates = []
    if not movement_search_invalid and (normalize_search_text(movement_name_query) or search_branch_id):
        q = (
            Employee.query.join(Branch, Employee.branch_id == Branch.id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(
                Employee.is_active == True,
                Branch.is_active == True,
                Governorate.is_active == True,
            )
        )
        if search_branch_ids:
            q = q.filter(Employee.branch_id.in_(search_branch_ids))
        elif search_gov_id:
            q = q.filter(False)
        scoped_employee_query = q
        if movement_name_query:
            q = q.filter(employee_search_filter(movement_name_query, include_contacts=True, include_branch=True))
        candidates = q.order_by(Employee.full_name.asc()).limit(50).all()
        if movement_name_query and not candidates and len(normalized_movement_query) >= 3:
            fallback_query = scoped_employee_query.order_by(Employee.full_name.asc()).limit(2500).all()
            context_branch_name = ''
            context_governorate_name = ''
            if search_branch_id:
                selected_branch = db.session.get(Branch, search_branch_id)
                context_branch_name = selected_branch.name if selected_branch else ''
                context_governorate_name = selected_branch.governorate.name if selected_branch and selected_branch.governorate else ''
            elif search_gov_id:
                selected_governorate = db.session.get(Governorate, search_gov_id)
                context_governorate_name = selected_governorate.name if selected_governorate else ''
            ranked_candidates = rank_scoped_employee_suggestions(
                movement_name_query,
                fallback_query,
                limit=8,
                basic_branch_name=context_branch_name,
                governorate_name=context_governorate_name,
            )
            candidates = [item['employee'] for item in ranked_candidates]
            movement_employee_match_reasons = {
                item['employee'].id: '، '.join(item.get('match_reasons') or [])
                for item in ranked_candidates
                if item.get('match_reasons')
            }
        movement_employee_matches = candidates

    if not movement_search_invalid and movement_employee_id.isdigit():
        candidate = db.session.get(Employee, int(movement_employee_id))
        if (
            candidate and candidate.is_active and candidate.branch
            and candidate.branch.is_active and candidate.branch.governorate
            and candidate.branch.governorate.is_active
        ):
            if (
                (not search_gov_id or candidate.branch.governorate_id == search_gov_id)
                and (not search_branch_id or candidate.branch_id == search_branch_id)
            ):
                movement_employee = candidate
    elif not movement_search_invalid and movement_name_query and movement_employee_matches:
        # Only a unique official/confirmed-alias identity can prefill the result.
        # A single substring/fuzzy result remains a clickable candidate, not an
        # implicit employee selection.
        identity = resolve_scoped_employee_identity(
            movement_name_query,
            movement_employee_matches,
        )
        if identity.get('status') == 'unique_match':
            movement_employee = identity.get('employee')
    movement_employee_in_scope = bool(movement_employee and branch_ok(movement_employee.branch_id)) if movement_employee else False

    # Show the branch's assigned first-entry contact in every homepage search state.
    # The assignment is branch-based, not employee-id based, and comes from the
    # active organizational assignment records without creating login roles.
    visible_search_employees = list(movement_employee_matches or [])
    if movement_employee and all(e.id != movement_employee.id for e in visible_search_employees):
        visible_search_employees.append(movement_employee)
    visible_search_branch_ids = {e.branch_id for e in visible_search_employees if e.branch_id}
    entry_names_by_branch = entry_responsible_names_by_branch(visible_search_branch_ids)
    movement_entry_responsible_map = {
        employee.id: entry_responsible_label(entry_names_by_branch.get(employee.branch_id, []))
        for employee in visible_search_employees
    }
    movement_entry_responsible_status_map = {
        employee.id: (
            'conflict' if len(entry_names_by_branch.get(employee.branch_id, [])) > 1
            else 'assigned' if entry_names_by_branch.get(employee.branch_id, [])
            else 'unassigned'
        )
        for employee in visible_search_employees
    }
    movement_employee_last = latest_assignment_summaries({employee.id for employee in visible_search_employees})

    # Only a compact latest-assignment summary is loaded into search results. Full
    # movement history is displayed on the employee profile and read-only reports.
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

    # Employee/movement reading is global for every official login role.
    # The work governorate remains a separate write/assignment context.
    visible_govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()

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
                today_movement_count = 0
                alert_count = 0
                if branch_employee_ids and can('view_reports'):
                    today_movement_count = (
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
                    alert_count = (
                        Movement.query.filter(
                            Movement.employee_id.in_(branch_employee_ids),
                            Movement.is_active == True,
                            Movement.to_date == tomorrow,
                            Movement.movement_type.in_(['إجازة', 'انتداب']),
                        )
                        .count()
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
            # The admin performs the supervisor's operational task only inside
            # the selected work governorate; never offer supervisors from other
            # governorates in the same assignment form.
            entry_supervisors = [
                u
                for u in User.query.filter_by(is_active=True).order_by(User.full_name.asc()).all()
                if selected_manager_gov
                and 'مشرف محافظة' in actual_roles(u)
                and int(selected_manager_gov) in user_gov_ids(u)
            ]
        elif is_manager_support:
            entry_supervisors = supervisors
        else:
            entry_supervisors = [me()]

        # A governorate supervisor may also act as the operational entry contact.
        # Include the employee record linked to that supervisor even where their
        # personal HR branch differs from the branches they are assigned to cover.
        eligible_supervisor_ids = {u.id for u in entry_supervisors if u and u.is_active}
        if eligible_supervisor_ids:
            active_assignment_employee_ids = {
                row.employee_id for row in EntryAssignment.query.filter_by(is_active=True).all()
            }
            existing_candidate_ids = {e.id for e in available_entry_employees}
            linked_supervisor_employees = (
                Employee.query.filter(
                    Employee.is_active == True,
                    Employee.user_id.in_(eligible_supervisor_ids),
                ).order_by(Employee.full_name.asc()).all()
            )
            for employee in linked_supervisor_employees:
                if employee.id in active_assignment_employee_ids or employee.id in existing_candidate_ids:
                    continue
                if not employee.branch or not employee.branch.is_active or not employee.branch.governorate or not employee.branch.governorate.is_active:
                    continue
                available_entry_employees.append(employee)
                existing_candidate_ids.add(employee.id)

        available_entry_employee_is_supervisor = {
            employee.id: bool(
                employee.user_id
                and (linked := db.session.get(User, employee.user_id))
                and 'مشرف محافظة' in actual_roles(linked)
            )
            for employee in available_entry_employees
        }
        # لا نعرض إنشاء تكليف جديد في محافظة مفوضة فقط؛ التفويض لا ينقل
        # الملكية التنظيمية للمشرف البديل.
        if 'مشرف محافظة' in effective and delegated_only:
            available_entry_employees = []
            available_entry_branches = []

    if read_branch_ids and can('view_reports'):
        # This is a read-only status board: show all active governorates. Any
        # edit/close route opened from a record still rechecks the work scope.
        if has_role('مشرف محافظة', 'مسؤول التطبيق', 'Manager Application Support'):
            all_status_rows = current_employee_status_rows(read_branch_ids, today)
            # لا تعرض حالة حالية إذا لم يكن للمستخدم حق رؤية الحركة التي تحددها.
            all_status_rows = [r for r in all_status_rows if can_view_movement(r['movement'])]
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
    home_movement_branches = Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).order_by(Branch.name.asc()).all()

    # Preload confirmed aliases only for the visible first-entry directory. These
    # are used by client-side progressive search without broadening the data scope.
    entry_directory_employee_ids = {
        employee.id
        for entry_row in entry_rows
        for branch_group in entry_row.get('branches', [])
        for employee in branch_group.get('employees', [])
        if getattr(employee, 'id', None) is not None
    }
    entry_directory_branch_ids = {
        branch_group['branch'].id
        for entry_row in entry_rows
        for branch_group in entry_row.get('branches', [])
        if branch_group.get('branch') is not None
    }
    entry_directory_governorate_ids = {
        branch_group['branch'].governorate_id
        for entry_row in entry_rows
        for branch_group in entry_row.get('branches', [])
        if branch_group.get('branch') is not None
    }
    entry_employee_name_aliases = {}
    entry_employee_code_aliases = {}
    entry_branch_name_aliases = {}
    entry_governorate_name_aliases = {}
    if entry_directory_employee_ids:
        for alias in EmployeeNameAlias.query.filter(EmployeeNameAlias.employee_id.in_(entry_directory_employee_ids)).all():
            entry_employee_name_aliases.setdefault(alias.employee_id, []).append(alias.alias_text)
        for alias in TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.employee_id.in_(entry_directory_employee_ids)).all():
            entry_employee_code_aliases.setdefault(alias.employee_id, []).append(alias.alias_text)
    if entry_directory_branch_ids:
        for alias in BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(entry_directory_branch_ids)).all():
            entry_branch_name_aliases.setdefault(alias.branch_id, []).append(alias.alias_text)
    if entry_directory_governorate_ids:
        for alias in GovernorateNameAlias.query.filter(GovernorateNameAlias.governorate_id.in_(entry_directory_governorate_ids)).all():
            entry_governorate_name_aliases.setdefault(alias.governorate_id, []).append(alias.alias_text)

    available_entry_employee_aliases = {}
    available_entry_ids = [employee.id for employee in available_entry_employees if getattr(employee, 'id', None) is not None]
    if available_entry_ids:
        for alias in EmployeeNameAlias.query.filter(EmployeeNameAlias.employee_id.in_(available_entry_ids)).all():
            available_entry_employee_aliases.setdefault(alias.employee_id, []).append(alias.alias_text)

    # بحث الموظف في الرئيسية متاح لكل المحافظات، حتى لو كان نطاق العمل الحالي محافظة واحدة.
    return render_template(
        'home.html',
        g=len(visible_govs),
        b=len(read_branch_ids),
        e=(
            Employee.query.filter(Employee.branch_id.in_(read_branch_ids), Employee.is_active == True).count()
            if read_branch_ids
            else 0
        ),
        visible_govs=visible_govs,
        entry_rows=entry_rows,
        entry_employee_name_aliases=entry_employee_name_aliases,
        entry_employee_code_aliases=entry_employee_code_aliases,
        entry_branch_name_aliases=entry_branch_name_aliases,
        entry_governorate_name_aliases=entry_governorate_name_aliases,
        available_entry_employee_aliases=available_entry_employee_aliases,
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
            Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(Branch.is_active == True, Governorate.is_active == True)
            .order_by(Governorate.name.asc(), Branch.name.asc())
            .all()
        ),
        home_movement_governorates=home_movement_governorates,
        # وجهات الانتداب متاحة عبر جميع المحافظات النشطة، بصرف النظر عن نطاق العمل الحالي.
        home_assignment_governorates=(
            Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()
        ),
        home_movement_branches=home_movement_branches,
        movement_employee=movement_employee,
        movement_employee_in_scope=movement_employee_in_scope,
        movement_employee_moves=movement_employee_moves,
        movement_employee_last=movement_employee_last,
        movement_search_invalid=movement_search_invalid,
        movement_search_error=movement_search_error,
        movement_employee_matches=movement_employee_matches,
        movement_employee_match_reasons=movement_employee_match_reasons,
        movement_entry_responsible_map=movement_entry_responsible_map,
        movement_entry_responsible_status_map=movement_entry_responsible_status_map,
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
