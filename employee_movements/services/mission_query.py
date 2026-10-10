"""Read-only query services for assignment missions."""

from ..constants import STATUSES
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement, MissionEditRequest
from ..validation import parse_optional_iso_date


def build_mission_report_context(*, roles, allowed_bids, args):
    """Build the mission report query and all filter/display data.

    This service is deliberately read-only. Authorization decisions remain in the
    Blueprint; the service only applies the already-resolved scope to the query.
    """
    global_actor = bool({'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'} & set(roles))
    allowed_bids = set(allowed_bids)

    q = (
        Movement.query.join(Employee).filter(
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
        )
        if global_actor
        else (
            Movement.query.join(Employee).filter(
                Movement.is_active == True,
                Movement.movement_type == 'انتداب',
                Employee.branch_id.in_(allowed_bids),
            )
            if allowed_bids else Movement.query.filter(False)
        )
    )

    gov = args.get('governorate_id', '').strip()
    branch = args.get('branch_id', '').strip()
    destination_gov = args.get('destination_governorate_id', '').strip()
    destination_branch = args.get('destination_branch_id', '').strip()
    employee = args.get('employee_id', '').strip()
    status = args.get('status', '').strip()
    mission_state = args.get('mission_state', '').strip()
    date_from = args.get('date_from', '').strip()
    date_to = args.get('date_to', '').strip()
    duration = args.get('duration', '').strip()

    govs = Governorate.query.filter(
        Governorate.is_active == True
    ).order_by(Governorate.name.asc()).all()
    # Filter choices by both branch and parent-governorate status. A branch
    # may remain flagged active after its governorate has been deactivated; it
    # must not appear as a selectable current filter in the global report.
    active_branch_query = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True)
    )
    branches = (
        active_branch_query.order_by(Governorate.name.asc(), Branch.name.asc()).all()
        if global_actor else (
            active_branch_query.filter(Branch.id.in_(allowed_bids))
            .order_by(Governorate.name.asc(), Branch.name.asc()).all()
            if allowed_bids else []
        )
    )
    destination_governorates = Governorate.query.filter(
        Governorate.is_active == True
    ).order_by(Governorate.name.asc()).all()
    destination_branches = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True)
        .order_by(Governorate.name.asc(), Branch.name.asc()).all()
    )

    selected_gov = None
    if gov.isdigit() and any(g.id == int(gov) for g in govs):
        selected_gov = db.session.get(Governorate, int(gov))
        branches = [b for b in branches if b.governorate_id == selected_gov.id]
        q = q.filter(Employee.branch.has(Branch.governorate_id == selected_gov.id))
    else:
        gov = ''

    selected_destination_governorate = None
    if destination_gov.isdigit() and any(
        g.id == int(destination_gov) for g in destination_governorates
    ):
        selected_destination_governorate = db.session.get(
            Governorate, int(destination_gov)
        )
        destination_branches = [
            b for b in destination_branches
            if b.governorate_id == selected_destination_governorate.id
        ]
        q = q.filter(
            Movement.destination.has(
                Branch.governorate_id == selected_destination_governorate.id
            )
        )
    else:
        destination_gov = ''

    selected_destination_branch = None
    if destination_branch.isdigit() and any(
        b.id == int(destination_branch) for b in destination_branches
    ):
        selected_destination_branch = db.session.get(Branch, int(destination_branch))
        q = q.filter(Movement.destination_branch_id == selected_destination_branch.id)
    else:
        destination_branch = ''

    selected_branch = None
    if branch.isdigit() and any(b.id == int(branch) for b in branches):
        selected_branch = db.session.get(Branch, int(branch))
        q = q.filter(Employee.branch_id == selected_branch.id)
    else:
        branch = ''

    employee_scope_ids = (
        [b.id for b in Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(Branch.is_active == True, Governorate.is_active == True).all()]
        if ('مسؤول التطبيق' in roles or 'مشرف محافظة' in roles or 'Manager Application Support' in roles)
        else list(allowed_bids)
    )
    employees_q = (
        Employee.query.filter(
            Employee.is_active == True,
            Employee.branch_id.in_(employee_scope_ids),
        )
        if employee_scope_ids else Employee.query.filter(False)
    )
    if selected_branch:
        employees_q = employees_q.filter(Employee.branch_id == selected_branch.id)
    elif selected_gov:
        employees_q = employees_q.join(Branch).filter(
            Branch.governorate_id == selected_gov.id
        )
    employees = employees_q.order_by(Employee.full_name.asc()).all()

    if employee.isdigit() and any(e.id == int(employee) for e in employees):
        q = q.filter(Movement.employee_id == int(employee))
    else:
        employee = ''

    if status in STATUSES:
        q = q.filter(Movement.status == status)
    if mission_state in ('تحت التحرير', 'مغلقة'):
        q = q.filter(Movement.mission_state == mission_state)
    elif mission_state:
        mission_state = ''

    if duration == 'open':
        q = q.filter(Movement.to_date.is_(None))
    elif duration == 'dated':
        q = q.filter(Movement.to_date.isnot(None))
    elif duration != '':
        duration = ''

    df = parse_optional_iso_date(date_from)
    dt = parse_optional_iso_date(date_to)
    if df and dt and df > dt:
        df, dt = dt, df
    if df:
        # Include open missions (NULL to_date): they continue beyond the filter start.
        q = q.filter(db.or_(Movement.to_date.is_(None), Movement.to_date >= df))
    if dt:
        q = q.filter(Movement.from_date <= dt)

    rows = q.order_by(Movement.from_date.desc(), Movement.id.desc()).all()

    pending_edit_requests_count = 0
    if 'مسؤول التطبيق' in roles:
        pending_edit_requests_count = MissionEditRequest.query.filter_by(
            status='قيد المراجعة'
        ).count()
    elif 'Manager Application Support' in roles and allowed_bids:
        pending_edit_requests_count = (
            MissionEditRequest.query.filter_by(status='قيد المراجعة')
            .join(Movement)
            .join(Employee, Movement.employee_id == Employee.id)
            .filter(Employee.branch_id.in_(allowed_bids))
            .count()
        )

    return {
        'rows': rows,
        'statuses': STATUSES,
        'report_governorates': govs,
        'report_branches': branches,
        'destination_governorates': destination_governorates,
        'destination_branches': destination_branches,
        'employees': employees,
        'selected_governorate': gov,
        'selected_branch': branch,
        'selected_destination_governorate': destination_gov,
        'selected_destination_branch': destination_branch,
        'selected_employee': employee,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'duration': duration,
        'mission_state': mission_state,
        'pending_edit_requests_count': pending_edit_requests_count,
    }
