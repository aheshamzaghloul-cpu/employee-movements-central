"""Domain services: assignments (انتداب), supervisors, organizational entry roles."""

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from .access import actual_roles, bids, branch_ok, me, movement_is_closed
from .constants import ASSIGNMENT_ALERT_DAYS, LOGIN_ROLES
from .extensions import db
from .movement_state import assignment_open_filter
from .models import (
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
)


def assignment_state(m):
    if not m or m.movement_type != 'انتداب':
        return None
    if movement_is_closed(m):
        return 'مغلق'
    if not m.to_date:
        return 'انتداب مفتوح'
    today = date.today()
    if m.to_date < today:
        return 'انتهت المدة'
    if m.to_date <= today + timedelta(days=ASSIGNMENT_ALERT_DAYS):
        return 'قرب الانتهاء'
    return 'ساري'


def latest_assignment_summaries(employee_ids):
    """Return one read-only latest-assignment summary per employee without N+1 queries.

    Results deliberately span governorates. This helper is for directory and home
    search summaries only; it does not grant permission to mutate the movement.
    The window query selects one row per employee instead of loading all historical
    assignments into application memory.
    """
    ids = {int(value) for value in (employee_ids or set()) if value is not None}
    if not ids:
        return {}

    ranked_assignments = (
        db.session.query(
            Movement.id.label('movement_id'),
            func.row_number().over(
                partition_by=Movement.employee_id,
                order_by=(Movement.from_date.desc().nullslast(), Movement.id.desc()),
            ).label('row_rank'),
        )
        .filter(
            Movement.employee_id.in_(ids),
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
        )
        .subquery()
    )
    rows = (
        Movement.query
        .options(joinedload(Movement.destination).joinedload(Branch.governorate))
        .join(ranked_assignments, Movement.id == ranked_assignments.c.movement_id)
        .filter(ranked_assignments.c.row_rank == 1)
        .all()
    )

    summaries = {}
    for movement in rows:
        destination = movement.destination
        governorate = destination.governorate if destination else None
        destination_name = destination.name if destination else 'جهة غير محددة'
        governorate_name = governorate.name if governorate else 'محافظة غير محددة'
        from_text = movement.from_date.strftime('%d/%m/%Y') if movement.from_date else 'غير محدد'
        to_text = movement.to_date.strftime('%d/%m/%Y') if movement.to_date else 'مفتوح'
        if movement_is_closed(movement):
            state_text = 'مغلقة'
        else:
            state_text = assignment_state(movement) or 'غير محددة'
        label = (
            f'{destination_name} — {governorate_name} · من {from_text} إلى {to_text} · {state_text}'
        )
        summaries[movement.employee_id] = {
            'text': label,
            'destination': destination_name,
            'governorate': governorate_name,
            'from_date': from_text,
            'to_date': to_text,
            'state': state_text,
        }
    return summaries


def resolve_current_movement(movements, on_date=None):
    """Resolve one canonical current operational movement from an already-loaded list.

    This is the single status rule used by Home, employee cards, movement preflight
    and employee listings. Closed/deleted movements never become current. Priority
    remains the established product rule: leave -> dated assignment -> open assignment
    -> today's permission.
    """
    on_date = on_date or date.today()
    moves = [m for m in (movements or []) if m and m.is_active]
    # Make the resolver deterministic even when callers provide an unsorted list.
    # Newer records win only when the same movement type has more than one
    # overlapping candidate; the business priority below remains unchanged.
    moves.sort(
        key=lambda m: (
            getattr(m, 'created_at', None) or datetime.min,
            getattr(m, 'id', 0) or 0,
        ),
        reverse=True,
    )

    leave = next((m for m in moves if m.movement_type == 'إجازة'
                  and m.from_date and m.to_date
                  and m.from_date <= on_date <= m.to_date), None)
    assignment = next((m for m in moves if m.movement_type == 'انتداب'
                       and not movement_is_closed(m)
                       and m.from_date and m.from_date <= on_date
                       and m.to_date is not None and on_date <= m.to_date), None)
    open_assignment = next((m for m in moves if m.movement_type == 'انتداب'
                            and not movement_is_closed(m)
                            and m.from_date and m.from_date <= on_date
                            and m.to_date is None), None)
    permission = next((m for m in moves if m.movement_type == 'إذن'
                       and m.permission_date == on_date), None)
    return leave or assignment or open_assignment or permission


def current_assignment_for_employee(employee_id, on_date=None):
    on_date = on_date or date.today()
    moves = (
        Movement.query.filter_by(employee_id=employee_id, is_active=True, movement_type='انتداب')
        .filter(
            assignment_open_filter(Movement),
        )
        .order_by(Movement.id.desc())
        .all()
    )
    for m in moves:
        if not m.from_date or m.from_date > on_date:
            continue
        if m.to_date is None or on_date <= m.to_date:
            return m
    return None


def effective_branch_id_for_employee(employee_id, on_date=None):
    m = current_assignment_for_employee(employee_id, on_date)
    return m.destination_branch_id if m and m.destination_branch_id else None


def employee_is_effectively_in_branch(employee, branch_id, on_date=None):
    assigned = effective_branch_id_for_employee(employee.id, on_date)
    return assigned == branch_id if assigned else employee.branch_id == branch_id


def employee_scope_ok(employee, on_date=None):
    if not employee or not employee.is_active:
        return False
    today = on_date or date.today()
    return (
        branch_ok(employee.branch_id)
        or effective_branch_id_for_employee(employee.id, today) in set(bids())
    )


def employees_effectively_in_branches(branch_ids, on_date=None):
    """Return employees physically in the requested branches without an N+1 query.

    The old implementation executed a movement query for every active employee.
    On the home-page employee search this could become very expensive and, on a
    busy database, surface as a generic Internal Server Error/worker timeout.
    Build the set of employees with a current open assignment in one query, then
    fetch the employees once.
    """
    ids = {int(x) for x in branch_ids or set() if x is not None}
    if not ids:
        return []
    today = on_date or date.today()

    assigned_employee_ids = {
        row[0]
        for row in db.session.query(Movement.employee_id).filter(Movement.is_active == True, Movement.movement_type == 'انتداب', assignment_open_filter(Movement), Movement.from_date != None, Movement.from_date <= today, db.or_(Movement.to_date == None, Movement.to_date >= today), Movement.destination_branch_id.in_(ids)).all()
    }

    q = (
        Employee.query.options(joinedload(Employee.branch).joinedload(Branch.governorate))
        .filter(
            Employee.is_active == True,
            db.or_(Employee.branch_id.in_(ids), Employee.id.in_(assigned_employee_ids)),
        )
        .order_by(Employee.full_name.asc(), Employee.id.asc())
    )
    return q.all()


def supervisor_for_governorate(governorate_id):
    """Return the single active governorate supervisor responsible for a governorate.

    Returns ``None`` when no supervisor, or more than one, is responsible so callers
    never guess between several candidates.
    """
    user_ids = [
        link.user_id for link in UserGovernorate.query.filter_by(governorate_id=governorate_id).all()
    ]
    supervisors = [db.session.get(User, uid) for uid in user_ids]
    supervisors = [
        u for u in supervisors if u and u.is_active and 'مشرف محافظة' in actual_roles(u)
    ]
    return supervisors[0] if len(supervisors) == 1 else None


def supervisor_for_entry(u=None):
    u = u or me()
    if not u or 'المدخل الأول' not in actual_roles(u):
        return None
    # Explicit hierarchy link is preferred.
    link = SupervisorEntry.query.filter_by(entry_id=u.id).order_by(SupervisorEntry.id.asc()).first()
    if (
        link
        and link.supervisor
        and link.supervisor.is_active
        and 'مشرف محافظة' in actual_roles(link.supervisor)
    ):
        return link.supervisor
    # Backward-compatible fallback: infer from the governorate when exactly one supervisor is responsible.
    governorate_ids = {
        b.governorate_id
        for b in Branch.query.join(UserBranch, UserBranch.branch_id == Branch.id)
        .filter(UserBranch.user_id == u.id)
        .all()
    }
    for governorate_id in governorate_ids:
        supervisor = supervisor_for_governorate(governorate_id)
        if supervisor:
            return supervisor
    return None


def entries_for_supervisor(supervisor, gid=None):
    if not supervisor:
        return []
    q = SupervisorEntry.query.filter_by(supervisor_id=supervisor.id)
    links = q.order_by(SupervisorEntry.id.asc()).all()
    out = []
    for link in links:
        u = link.entry
        if not u or not u.is_active or 'المدخل الأول' not in actual_roles(u):
            continue
        if gid:
            ub = [x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()]
            if not any((b.governorate_id == gid for b in Branch.query.filter(Branch.id.in_(ub)).all())):
                continue
        out.append(u)
    return out


def assignment_supervisor(m):
    if not m or not m.employee or (not m.employee.branch):
        return None
    gid = m.employee.branch.governorate_id
    suids = [x.user_id for x in UserGovernorate.query.filter_by(governorate_id=gid).all()]
    for uid in suids:
        u = db.session.get(User, uid)
        if u and u.is_active and ('مشرف محافظة' in actual_roles(u)):
            return u
    return None


def assignment_followups():
    today = date.today()
    limit = today + timedelta(days=ASSIGNMENT_ALERT_DAYS)
    bs = bids()
    if not bs:
        return []
    return (
        Movement.query.join(Employee)
        .filter(
            Employee.branch_id.in_(bs),
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
            assignment_open_filter(Movement),
            Movement.to_date != None,
            Movement.to_date <= limit,
        )
        .order_by(Movement.to_date.asc())
        .all()
    )


def organizational_entries_for_supervisor(supervisor, gid=None):
    """Return active entry assignments and covered branches in two bounded queries.

    The former implementation queried branches once per assignment and lazily
    loaded each employee. On a supervisor with many branch assignments this made
    the homepage query count grow linearly with the number of assignments.
    """
    if not supervisor:
        return []
    assignments = (
        EntryAssignment.query
        .options(joinedload(EntryAssignment.employee))
        .filter_by(supervisor_id=supervisor.id, is_active=True)
        .order_by(EntryAssignment.id.asc())
        .all()
    )
    if not assignments:
        return []

    assignment_ids = [assignment.id for assignment in assignments]
    branch_rows = (
        db.session.query(EntryAssignmentBranch.entry_assignment_id, Branch)
        .join(Branch, Branch.id == EntryAssignmentBranch.branch_id)
        .join(Governorate, Governorate.id == Branch.governorate_id)
        .options(joinedload(Branch.governorate))
        .filter(
            EntryAssignmentBranch.entry_assignment_id.in_(assignment_ids),
            Branch.is_active == True,
            Governorate.is_active == True,
        )
        .order_by(Branch.name.asc(), Branch.id.asc())
        .all()
    )
    branches_by_assignment = {}
    for assignment_id, branch in branch_rows:
        if gid and branch.governorate_id != gid:
            continue
        branches_by_assignment.setdefault(assignment_id, []).append(branch)

    out = []
    for assignment in assignments:
        if not assignment.employee or not assignment.employee.is_active:
            continue
        branches = branches_by_assignment.get(assignment.id, [])
        if branches or not gid:
            out.append((assignment, branches))
    return out


def organizational_entry_for_employee(e):
    if not e:
        return None
    return EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first()


def entry_responsible_names_by_branch(branch_ids):
    """Return active operational entry contacts grouped by the branches they cover.

    An EntryAssignment.employee_id is the person assigned to handle data entry;
    EntryAssignmentBranch.branch_id is the branch they are responsible for. Do not
    match an employee to themselves by employee_id when showing the responsible
    contact for an ordinary employee. The one-query lookup also avoids N+1 queries
    in homepage and directory search results.
    """
    ids = {int(branch_id) for branch_id in (branch_ids or []) if branch_id is not None}
    if not ids:
        return {}

    rows = (
        db.session.query(EntryAssignmentBranch.branch_id, Employee.id, Employee.full_name)
        .join(EntryAssignment, EntryAssignment.id == EntryAssignmentBranch.entry_assignment_id)
        .join(Employee, Employee.id == EntryAssignment.employee_id)
        .filter(
            EntryAssignment.is_active == True,
            EntryAssignmentBranch.branch_id.in_(ids),
            Employee.is_active == True,
        )
        .order_by(EntryAssignmentBranch.branch_id.asc(), Employee.full_name.asc(), Employee.id.asc())
        .all()
    )
    grouped = {}
    seen_employee_ids = {}
    for branch_id, employee_id, full_name in rows:
        name = (full_name or '').strip()
        if not name:
            continue
        seen = seen_employee_ids.setdefault(branch_id, set())
        if employee_id in seen:
            continue
        seen.add(employee_id)
        grouped.setdefault(branch_id, []).append(name)
    return grouped


def entry_responsible_label(names):
    """Format the entry contact clearly and make duplicate branch assignments visible."""
    clean_names = [(name or '').strip() for name in (names or []) if (name or '').strip()]
    if not clean_names:
        return 'غير محدد'
    if len(clean_names) == 1:
        return clean_names[0]
    # Keep repeated names if they belong to different employee records; do not
    # conceal duplicate active assignments merely because names happen to match.
    return 'تعارض تكليفات: ' + '، '.join(clean_names)


def entry_role_exists(e):
    return bool(organizational_entry_for_employee(e))


def sync_role_accounts(u):
    if not u:
        return
    real = actual_roles(u) - {'المدخل الأول'}
    existing = {x.role: x for x in RoleAccount.query.filter_by(user_id=u.id).all()}
    for role in list(existing):
        if role not in real:
            db.session.delete(existing[role])
    for role in real:
        # تكليف إدخال الفروع محفوظ في EntryAssignment ولا ينشئ دور دخول مستقلًا.
        if role not in LOGIN_ROLES:
            continue
        x = existing.get(role)
        if not x:
            db.session.add(
                RoleAccount(
                    user_id=u.id,
                    role=role,
                    username=u.username,
                    password_hash=u.password_hash,
                ),
            )
        else:
            x.username = u.username
            x.password_hash = u.password_hash


def branch_entry(b):
    # التكليف التنظيمي EntryAssignment هو المصدر الوحيد للحالة الحالية.
    link = (
        EntryAssignmentBranch.query.join(EntryAssignment)
        .filter(EntryAssignmentBranch.branch_id == b.id, EntryAssignment.is_active == True)
        .first()
    )
    if link and link.assignment and link.assignment.employee:
        return link.assignment.employee
    return None
