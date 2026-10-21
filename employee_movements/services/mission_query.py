"""Read-only query services for assignment missions."""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement, MissionEditRequest
from ..pagination import safe_page_number
from ..movement_state import assignment_closed_filter, assignment_open_filter
from ..validation import parse_optional_iso_date


def build_mission_report_context(*, roles, allowed_bids, args, paginate=False, include_creator=False, include_total=False):
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
    mission_state = args.get('mission_state', '').strip()
    date_from = args.get('date_from', '').strip()
    date_to = args.get('date_to', '').strip()
    duration = args.get('duration', '').strip()
    follow_up = args.get('follow_up', '').strip()
    filter_error = False

    govs = Governorate.query.filter(
        Governorate.is_active == True
    ).order_by(Governorate.name.asc()).all()
    # This one active-governorate list serves both source and destination filters.
    # Building a second identical list only repeats a database round-trip.
    governorates_by_id = {governorate.id: governorate for governorate in govs}
    # Filter choices by both branch and parent-governorate status. A branch
    # may remain flagged active after its governorate has been deactivated; it
    # must not appear as a selectable current filter in the global report.
    active_branch_query = (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .options(joinedload(Branch.governorate))
        .filter(Branch.is_active == True, Governorate.is_active == True)
    )
    if global_actor:
        # Both dropdowns have the same active branch universe for global readers.
        # Reuse one query result while keeping separate lists because each filter
        # narrows its own list below.
        active_branches = active_branch_query.order_by(
            Governorate.name.asc(), Branch.name.asc()
        ).all()
        branches = list(active_branches)
        destination_branches = list(active_branches)
    else:
        branches = (
            active_branch_query.filter(Branch.id.in_(allowed_bids))
            .order_by(Governorate.name.asc(), Branch.name.asc()).all()
            if allowed_bids else []
        )
        destination_branches = active_branch_query.order_by(
            Governorate.name.asc(), Branch.name.asc()
        ).all()
    # Every active governorate is a valid source and destination filter.
    destination_governorates = govs

    selected_gov = None
    if gov:
        selected_gov = governorates_by_id.get(int(gov)) if gov.isdigit() else None
        if selected_gov:
            branches = [b for b in branches if b.governorate_id == selected_gov.id]
            q = q.filter(Employee.branch.has(Branch.governorate_id == selected_gov.id))
        else:
            filter_error = True
            q = q.filter(False)
            gov = ''

    selected_destination_governorate = None
    if destination_gov:
        selected_destination_governorate = (
            governorates_by_id.get(int(destination_gov)) if destination_gov.isdigit() else None
        )
        if selected_destination_governorate:
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
            filter_error = True
            q = q.filter(False)
            destination_gov = ''

    selected_destination_branch = None
    destination_branches_by_id = {b.id: b for b in destination_branches}
    if destination_branch:
        selected_destination_branch = (
            destination_branches_by_id.get(int(destination_branch))
            if destination_branch.isdigit() else None
        )
        if selected_destination_branch:
            q = q.filter(Movement.destination_branch_id == selected_destination_branch.id)
        else:
            filter_error = True
            q = q.filter(False)
            destination_branch = ''

    selected_branch = None
    branches_by_id = {b.id: b for b in branches}
    if branch:
        selected_branch = branches_by_id.get(int(branch)) if branch.isdigit() else None
        if selected_branch:
            q = q.filter(Employee.branch_id == selected_branch.id)
        else:
            filter_error = True
            q = q.filter(False)
            branch = ''

    # Keep global active-branch scope as a SQL subquery instead of loading every
    # branch ID into Python on each report request. Scoped roles use their already
    # resolved branch IDs. This avoids an extra materialization of the full branch
    # directory while preserving the exact same employee eligibility rules.
    if global_actor:
        employee_branch_scope = (
            select(Branch.id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .where(Branch.is_active == True, Governorate.is_active == True)
        )
        has_employee_scope = True
    else:
        employee_branch_scope = list(allowed_bids)
        has_employee_scope = bool(allowed_bids)
    # Keep the employee filter searchable instead of rendering every employee
    # as an HTML <option> on each report load. Only fetch the explicitly selected
    # employee, and validate it against the same active branch/governorate scope.
    employees_q = (
        Employee.query.options(
            joinedload(Employee.branch).joinedload(Branch.governorate)
        ).filter(
            Employee.is_active == True,
            Employee.branch_id.in_(employee_branch_scope),
        )
        if has_employee_scope else Employee.query.filter(False)
    )
    if selected_branch:
        employees_q = employees_q.filter(Employee.branch_id == selected_branch.id)
    elif selected_gov:
        employees_q = employees_q.join(Branch).filter(
            Branch.governorate_id == selected_gov.id
        )
    selected_employee_object = None
    if employee:
        if employee.isdigit():
            selected_employee_object = employees_q.filter(Employee.id == int(employee)).first()
        if selected_employee_object:
            q = q.filter(Movement.employee_id == selected_employee_object.id)
        else:
            filter_error = True
            q = q.filter(False)
            employee = ''
    employees = [selected_employee_object] if selected_employee_object else []

    if mission_state == 'مغلقة':
        # Current state and older assignment_state values share one meaning.
        q = q.filter(assignment_closed_filter(Movement))
    elif mission_state == 'تحت التحرير':
        q = q.filter(
            db.or_(Movement.mission_state == 'تحت التحرير', Movement.mission_state.is_(None)),
            assignment_open_filter(Movement),
        )
    elif mission_state:
        filter_error = True
        q = q.filter(False)
        mission_state = ''

    if duration == 'open':
        # “Open without an end date” is a lifecycle state, not merely a NULL date.
        # Legacy closed missions may have a missing end date and must not be labeled open.
        q = q.filter(Movement.to_date.is_(None), assignment_open_filter(Movement))
    elif duration == 'dated':
        q = q.filter(Movement.to_date.isnot(None))
    elif duration != '':
        filter_error = True
        q = q.filter(False)
        duration = ''

    if follow_up == '7':
        today = date.today()
        q = q.filter(
            Movement.to_date.isnot(None),
            assignment_open_filter(Movement),
            Movement.to_date >= today,
            Movement.to_date <= today + timedelta(days=7),
        )
    elif follow_up:
        filter_error = True
        q = q.filter(False)
        follow_up = ''

    df = parse_optional_iso_date(date_from)
    dt = parse_optional_iso_date(date_to)
    date_range_error = bool(df and dt and df > dt)
    if date_from and df is None:
        filter_error = True
        q = q.filter(False)
        date_from = ''
    if date_to and dt is None:
        filter_error = True
        q = q.filter(False)
        date_to = ''
    if df and dt:
        date_from, date_to = df.isoformat(), dt.isoformat()
    if date_range_error:
        # Fail closed instead of silently reversing the user's requested period.
        # This keeps HTML and Excel exports consistent and makes correction explicit.
        filter_error = True
        q = q.filter(False)
    if df:
        # Include open missions (NULL to_date): they continue beyond the filter start.
        q = q.filter(db.or_(Movement.to_date.is_(None), Movement.to_date >= df))
    if dt:
        q = q.filter(Movement.from_date <= dt)

    # The HTML report is paginated by the database. Export callers deliberately
    # keep paginate=False so the generated workbook still contains every match.
    # A count is required for HTML pagination but adds an unnecessary full count
    # query to exports, which stream all matching rows independently.
    total_rows = q.order_by(None).count() if (paginate or include_total) else None
    page_size = 50
    page = 1
    page_count = max(1, (total_rows + page_size - 1) // page_size) if total_rows is not None else 1
    if paginate:
        raw_page = str(args.get('page', '1') or '1').strip()
        page = safe_page_number(raw_page, page_count)
    row_load_options = [
        joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate),
        joinedload(Movement.destination).joinedload(Branch.governorate),
    ]
    # Creator data is only needed by document generation; keeping it optional
    # avoids an unnecessary join on the interactive paginated report.
    if include_creator:
        row_load_options.append(joinedload(Movement.creator_user))
    rows_query = q.options(*row_load_options).order_by(Movement.from_date.desc(), Movement.id.desc())
    if paginate:
        rows_query = rows_query.limit(page_size).offset((page - 1) * page_size)
        rows = rows_query.all()
    else:
        # Export consumers iterate this SQLAlchemy query in bounded batches instead
        # of materializing the full result set in application memory.
        rows = rows_query.yield_per(500)
    # Pending requests are normally a small queue. Load only their movement IDs
    # once, avoiding one lookup per row and avoiding huge IN lists for large reports.
    page_movement_ids = [movement.id for movement in rows] if paginate else []
    if paginate and page_movement_ids:
        pending_edit_request_movement_ids = {
            movement_id for (movement_id,) in (
                db.session.query(MissionEditRequest.movement_id)
                .filter(
                    MissionEditRequest.status == 'قيد المراجعة',
                    MissionEditRequest.movement_id.in_(page_movement_ids),
                )
                .all()
            )
        }
    else:
        pending_edit_request_movement_ids = set()

    pending_edit_requests_count = 0
    if paginate and 'مسؤول التطبيق' in roles:
        pending_edit_requests_count = MissionEditRequest.query.filter_by(
            status='قيد المراجعة'
        ).count()
    elif paginate and 'Manager Application Support' in roles and allowed_bids:
        pending_edit_requests_count = (
            MissionEditRequest.query.filter_by(status='قيد المراجعة')
            .join(Movement)
            .join(Employee, Movement.employee_id == Employee.id)
            .filter(Employee.branch_id.in_(allowed_bids))
            .count()
        )

    return {
        'rows': rows,
        'total_rows': total_rows,
        'page': page,
        'page_size': page_size,
        'page_count': page_count,
        'paginated': bool(paginate),
        'report_governorates': govs,
        'report_branches': branches,
        'destination_governorates': destination_governorates,
        'destination_branches': destination_branches,
        'employees': employees,
        'selected_employee_object': selected_employee_object,
        'selected_governorate': gov,
        'selected_branch': branch,
        'selected_destination_governorate': destination_gov,
        'selected_destination_branch': destination_branch,
        'selected_employee': employee,
        'date_from': date_from,
        'date_to': date_to,
        'duration': duration,
        'mission_state': mission_state,
        'follow_up': follow_up,
        'pending_edit_request_movement_ids': pending_edit_request_movement_ids,
        'pending_edit_requests_count': pending_edit_requests_count,
        'filter_error': filter_error,
        'date_range_error': date_range_error,
    }
