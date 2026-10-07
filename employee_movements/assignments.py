"""Domain services: assignments (انتداب), supervisors, organizational entry roles."""

from datetime import date, datetime, timedelta

from .access import actual_roles, bids, branch_ok, me
from .constants import ASSIGNMENT_ALERT_DAYS, LOGIN_ROLES
from .extensions import db
from .models import (
    Branch,
    Employee,
    EntryAssignment,
    EntryAssignmentBranch,
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
    if m.assignment_state == 'مغلق':
        return 'مغلق'
    if not m.to_date:
        return 'انتداب مفتوح'
    today = date.today()
    if m.to_date < today:
        return 'انتهت المدة'
    if m.to_date <= today + timedelta(days=ASSIGNMENT_ALERT_DAYS):
        return 'قرب الانتهاء'
    return 'ساري'


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
                       and m.assignment_state != 'مغلق'
                       and m.from_date and m.from_date <= on_date
                       and m.to_date is not None and on_date <= m.to_date), None)
    open_assignment = next((m for m in moves if m.movement_type == 'انتداب'
                            and m.assignment_state != 'مغلق'
                            and m.from_date and m.from_date <= on_date
                            and m.to_date is None), None)
    permission = next((m for m in moves if m.movement_type == 'إذن'
                       and m.permission_date == on_date), None)
    return leave or assignment or open_assignment or permission


def current_assignment_for_employee(employee_id, on_date=None):
    on_date = on_date or date.today()
    moves = (
        Movement.query.filter_by(employee_id=employee_id, is_active=True, movement_type='انتداب')
        .filter(Movement.assignment_state != 'مغلق')
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
        for row in db.session.query(Movement.employee_id).filter(Movement.is_active == True, Movement.movement_type == 'انتداب', Movement.assignment_state != 'مغلق', Movement.from_date != None, Movement.from_date <= today, db.or_(Movement.to_date == None, Movement.to_date >= today), Movement.destination_branch_id.in_(ids)).all()
    }

    q = (
        Employee.query.filter(
            Employee.is_active == True,
            db.or_(Employee.branch_id.in_(ids), Employee.id.in_(assigned_employee_ids)),
        )
        .order_by(Employee.full_name.asc())
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
            Movement.assignment_state != 'مغلق',
            Movement.to_date != None,
            Movement.to_date <= limit,
        )
        .order_by(Movement.to_date.asc())
        .all()
    )


def organizational_entries_for_supervisor(supervisor, gid=None):
    if not supervisor:
        return []
    q = EntryAssignment.query.filter_by(supervisor_id=supervisor.id, is_active=True)
    out = []
    for a in q.order_by(EntryAssignment.id.asc()).all():
        if not a.employee or not a.employee.is_active:
            continue
        branch_ids = {
            x.branch_id
            for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).all()
        }
        branches = (
            (
                Branch.query.filter(Branch.id.in_(branch_ids), Branch.is_active == True)
                .order_by(Branch.name)
                .all()
            )
            if branch_ids
            else []
        )
        if gid:
            branches = [b for b in branches if b.governorate_id == gid]
        if branches or not gid:
            out.append((a, branches))
    return out


def organizational_entry_for_employee(e):
    if not e:
        return None
    return EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first()


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
        # المدخل الأول دور تنظيمي للموظف وليس حساب دخول مستقلًا.
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
