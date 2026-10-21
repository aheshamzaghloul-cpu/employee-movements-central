"""Read-oriented movement and mission report handlers for the assistant."""

from datetime import date

from ..access import can, readable_branch_ids
from ..assignments import current_assignment_for_employee
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement
from ..movement_state import assignment_open_filter
from .read_helpers import _load_candidate_records, employee_status_text
from .visibility import visible_employee, visible_movement


def handle_movement_people_today(a):
    mt = a.get('movement_type') or 'إجازة'
    gid = a.get('governorate_id')
    bid = a.get('branch_id')
    gov = db.session.get(Governorate, gid) if gid else None
    branch = db.session.get(Branch, bid) if bid else None
    allowed_gids = {row.id for row in Governorate.query.filter_by(is_active=True).all()}
    allowed_branch_ids = set(readable_branch_ids())
    if gov and (not gov.is_active or gov.id not in allowed_gids):
        return {'title': 'نتيجة البحث', 'error': 'المحافظة غير متاحة أو غير نشطة.'}
    if branch and (not branch.is_active or not branch.governorate or not branch.governorate.is_active or branch.id not in allowed_branch_ids):
        return {'title': 'نتيجة البحث', 'error': 'الفرع غير متاح أو غير نشط.'}
    if not gov and (not branch):
        return {'title': 'نتيجة البحث', 'error': 'لم أجد محافظة أو فرعًا مطابقًا.'}

    today = date.today()
    if branch:
        target_branch_ids = {branch.id}
        location_label = f'فرع {branch.name}'
    elif gov:
        visible_branch_ids = allowed_branch_ids
        bs = (Branch.query
              .filter(Branch.governorate_id == gov.id, Branch.is_active == True, Branch.id.in_(visible_branch_ids))
              .order_by(Branch.name)
              .all()) if visible_branch_ids else []
        target_branch_ids = {b.id for b in bs}
        location_label = f'محافظة {gov.name}'
    else:
        # Search all active branches; this remains a read-only operation.
        target_branch_ids = allowed_branch_ids
        location_label = 'جميع المحافظات'

    rows = []
    if mt == 'إجازة':
        if target_branch_ids:
            latest_ids = (
                db.session.query(db.func.max(Movement.id).label('movement_id'))
                .join(Employee, Movement.employee_id == Employee.id)
                .filter(
                    Employee.is_active == True,
                    Employee.branch_id.in_(target_branch_ids),
                    Movement.is_active == True,
                    Movement.movement_type == 'إجازة',
                    Movement.from_date <= today,
                    Movement.to_date >= today,
                )
                .group_by(Movement.employee_id)
                .subquery()
            )
            moves = (
                Movement.query.join(Employee, Movement.employee_id == Employee.id)
                .filter(Movement.id.in_(db.select(latest_ids.c.movement_id)))
                .order_by(Employee.full_name)
                .all()
            )
            rows.extend((m.employee, m, None) for m in moves)
    elif mt == 'إذن':
        if target_branch_ids:
            latest_ids = (
                db.session.query(db.func.max(Movement.id).label('movement_id'))
                .join(Employee, Movement.employee_id == Employee.id)
                .filter(
                    Employee.is_active == True,
                    Employee.branch_id.in_(target_branch_ids),
                    Movement.is_active == True,
                    Movement.movement_type == 'إذن',
                    Movement.permission_date == today,
                )
                .group_by(Movement.employee_id)
                .subquery()
            )
            moves = (
                Movement.query.join(Employee, Movement.employee_id == Employee.id)
                .filter(Movement.id.in_(db.select(latest_ids.c.movement_id)))
                .order_by(Employee.full_name)
                .all()
            )
            rows.extend((m.employee, None, None) for m in moves)
    else:
        # انتداب: «في المكان» تعني أن الوجهة الحالية داخل المكان.
        if target_branch_ids:
            latest_ids = (
                db.session.query(db.func.max(Movement.id).label('movement_id'))
                .join(Employee, Movement.employee_id == Employee.id)
                .filter(
                    Employee.is_active == True,
                    Movement.is_active == True,
                    Movement.movement_type == 'انتداب',
                    assignment_open_filter(Movement),
                    Movement.from_date <= today,
                    (Movement.to_date == None) | (Movement.to_date >= today),
                    Movement.destination_branch_id.in_(target_branch_ids),
                )
                .group_by(Movement.employee_id)
                .subquery()
            )
            moves = (
                Movement.query.join(Employee, Movement.employee_id == Employee.id)
                .filter(Movement.id.in_(db.select(latest_ids.c.movement_id)))
                .order_by(Employee.full_name)
                .all()
            )
            rows.extend((m, m.employee.branch, m.destination) for m in moves)

    if not rows:
        labels = {'إجازة': 'في إجازة', 'انتداب': 'منتدبين', 'إذن': 'عندهم إذن'}
        return {
            'title': f'{labels[mt]} اليوم — {location_label}',
            'answer': f'لا يوجد موظفون {labels[mt]} اليوم في {location_label}.',
        }

    lines = []
    for (i, (m, origin, dest)) in enumerate(rows, 1):
        e = m.employee
        if mt == 'إجازة':
            detail = f'{m.leave_type or 'إجازة'} — حتى {m.to_date}'
        elif mt == 'إذن':
            detail = f'إذن اليوم — {m.permission_date}'
        else:
            direction = f'{(origin.name if origin else 'غير محدد')} → {(dest.name if dest else 'غير محدد')}'
            detail = f'{direction} — ' + ('مفتوح' if m.to_date is None else f'حتى {m.to_date}')
        branch_name = e.branch.name if e.branch else 'غير محدد'
        lines.append(f'{i}. {e.full_name} — {detail} — فرع التعيين: {branch_name}')
    labels = {
        'إجازة': 'الموظفون في إجازة',
        'انتداب': 'الموظفون المنتدبون',
        'إذن': 'الموظفون لديهم إذن',
    }
    return {
        'title': f'{labels[mt]} اليوم — {location_label}',
        'answer': f'{labels[mt]} اليوم في {location_label}: {len(rows)}\n\n' + '\n'.join(lines),
    }


def handle_governorate_assignments_today(a):
    gid = a.get('governorate_id')
    gov = db.session.get(Governorate, gid) if gid else None
    allowed_gids = {row.id for row in Governorate.query.filter_by(is_active=True).all()}
    if not gov or not gov.is_active or gov.id not in allowed_gids:
        return {
            'title': 'انتدابات اليوم',
            'error': 'لا توجد محافظة مطابقة أو ليست ضمن نطاق صلاحياتك.',
        }
    visible_branch_ids = set(readable_branch_ids())
    branches = (
        Branch.query
        .filter(Branch.governorate_id == gov.id, Branch.is_active == True, Branch.id.in_(visible_branch_ids))
        .order_by(Branch.name)
        .all()
    ) if visible_branch_ids else []
    branch_ids = {b.id for b in branches}
    rows = []
    # الانتداب الحالي إلى فرع داخل المحافظة — استعلام واحد بدل حركة لكل موظف.
    if branch_ids:
        latest_ids = (
            db.session.query(db.func.max(Movement.id).label('movement_id'))
            .join(Employee, Movement.employee_id == Employee.id)
            .filter(
                Employee.is_active == True,
                Movement.is_active == True,
                Movement.movement_type == 'انتداب',
                assignment_open_filter(Movement),
                Movement.from_date != None,
                Movement.from_date <= date.today(),
                db.or_(Movement.to_date == None, Movement.to_date >= date.today()),
                Movement.destination_branch_id.in_(branch_ids),
            )
            .group_by(Movement.employee_id)
            .subquery()
        )
        moves = (
            Movement.query.join(Employee, Movement.employee_id == Employee.id)
            .filter(Movement.id.in_(db.select(latest_ids.c.movement_id)))
            .order_by(Employee.full_name)
            .all()
        )
        rows.extend((m.employee, m, m.employee.branch, m.destination) for m in moves)
    if not rows:
        return {
            'title': f'منتدبو اليوم في محافظة {gov.name}',
            'answer': f'لا يوجد موظفون منتدبون حاليًا إلى فروع محافظة {gov.name} اليوم.',
        }
    lines = []
    for (i, (e, m, origin, dest)) in enumerate(rows, 1):
        period = 'مفتوح' if m.to_date is None else f'حتى {m.to_date}'
        direction = f'{(origin.name if origin else 'غير محدد')} → {(dest.name if dest else 'غير محدد')}'
        lines.append(
            f'{i}. {e.full_name} — {direction} — من {m.from_date or 'غير محدد'} — {period}',
        )
    return {
        'title': f'منتدبو اليوم في محافظة {gov.name}',
        'answer': f'عدد المنتدبين إلى فروع المحافظة اليوم: {len(rows)}\n\n' + '\n'.join(lines),
    }


def handle_employee_status(a):
    e = db.session.get(Employee, a.get('employee_id')) if a.get('employee_id') else None
    if not visible_employee(e):
        return {
            'title': 'نتيجة البحث',
            'error': 'لم أجد موظفًا واحدًا مطابقًا.',
            'choices': _load_candidate_records(Employee, a.get('candidate_ids', [])),
        }
    cur = current_assignment_for_employee(e.id)
    display_branch = cur.destination if cur and cur.destination else e.branch
    state = employee_status_text(e)
    return {
        'title': 'حالة الموظف',
        'answer': f'الموظف: {e.full_name}\nالفرع الحالي: {(display_branch.name if display_branch else '—')}\nفرع التعيين: {(e.branch.name if e.branch else '—')}\nالمحافظة: {(display_branch.governorate.name if display_branch and display_branch.governorate else '—')}\nالحالة الآن: {state}',
    }


def handle_employee_movements(a):
    if not can('view_reports'):
        return {'title': 'الصلاحيات', 'error': 'لا تملك صلاحية عرض سجل الحركات.'}
    e = db.session.get(Employee, a.get('employee_id')) if a.get('employee_id') else None
    if not visible_employee(e):
        return {
            'title': 'نتيجة البحث',
            'error': 'لم أجد موظفًا واحدًا مطابقًا.',
            'choices': _load_candidate_records(Employee, a.get('candidate_ids', [])),
        }
    candidates = (
        Movement.query.filter_by(employee_id=e.id, is_active=True)
        .order_by(Movement.id.desc()).limit(80).all()
    )
    ms = [m for m in candidates if visible_movement(m)][:30]
    if not ms:
        ans = f'{e.full_name}: لا توجد حركات مسجلة.'
    else:
        lines = []
        for m in ms:
            detail = m.leave_type or (m.destination.name if m.destination else '') or ''
            period = (
                m.permission_date
                or (f'{m.from_date} إلى {m.to_date}' if m.from_date or m.to_date else '')
            )
            lines.append(f'{m.movement_type} — {detail} — {period} — {m.status}')
        ans = f'سجل حركات {e.full_name}:\n' + '\n'.join(lines)
    return {'title': 'سجل حركات الموظف', 'answer': ans}
