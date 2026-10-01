"""Input parsing and movement validation helpers."""

from datetime import datetime

from .access import branch_ok, me
from .constants import LEAVE_TYPES, MOVEMENT_TYPES
from .extensions import db
from .models import Lookup, Movement, MovementHistory


def active_movement_types():
    vals = [
        x.name
        for x in Lookup.query.filter_by(kind='movement', is_active=True).order_by(Lookup.name).all()
    ]
    return vals or MOVEMENT_TYPES


def active_leave_types():
    vals = [
        x.name
        for x in Lookup.query.filter_by(kind='leave', is_active=True).order_by(Lookup.name).all()
    ]
    return vals or LEAVE_TYPES


def valid_email(v):
    import re
    v = (v or '').strip()
    return bool(re.fullmatch('[^@\\s]+@[^@\\s]+\\.[^@\\s]+', v))


def valid_password(p):
    return len(p) >= 8 and any((c.isalpha() for c in p)) and any((c.isdigit() for c in p))


def record_movement_history(m, old_status, new_status, action, reason=''):
    db.session.add(
        MovementHistory(
            movement_id=m.id,
            from_status=old_status,
            to_status=new_status,
            action=action,
            reason=reason,
            user_id=me().id if me() else None,
        ),
    )


def parse_date_value(v):
    return parse_date(v) if v else None


def movement_overlaps(employee_id, mt, fd, td, pd, exclude_id=None):
    q = Movement.query.filter(Movement.employee_id == employee_id, Movement.is_active == True)
    if exclude_id:
        q = q.filter(Movement.id != exclude_id)
    start = parse_date_value(fd)
    end = parse_date_value(td)
    day = parse_date_value(pd)
    for x in q.all():
        if mt == 'إذن':
            if day and x.movement_type == 'إذن' and (x.permission_date == day):
                return 'يوجد إذن آخر للموظف في نفس التاريخ.'
            if day and x.from_date and x.to_date and (x.from_date <= day <= x.to_date):
                return 'تاريخ الإذن يتعارض مع حركة أخرى للموظف.'
        elif start:
            if (
                x.movement_type == 'انتداب'
                and x.assignment_state != 'مغلق'
                and x.from_date
                and x.to_date is None
            ):
                if end is None or end >= x.from_date:
                    return 'يوجد انتداب مفتوح للموظف؛ أغلقه أو عدّل مدته قبل تسجيل حركة متعارضة.'
            if (
                x.from_date
                and x.to_date
                and (end is None or start <= x.to_date)
                and (end is None or end >= x.from_date)
            ):
                return 'فترة الحركة تتعارض مع حركة أخرى للموظف.'
            if (
                x.movement_type == 'إذن'
                and x.permission_date
                and (
                    end is None and x.permission_date >= start
                    or end is not None and start <= x.permission_date <= end
                )
            ):
                return 'فترة الحركة تتعارض مع إذن للموظف.'
    return None


def validate_movement_fields(mt, leave_type, dest, fd, td, pd):
    if mt not in active_movement_types():
        return 'نوع الحركة غير صحيح.'
    if mt == 'إجازة':
        if not leave_type or leave_type not in active_leave_types():
            return 'نوع الإجازة غير صحيح أو غير محدد.'
        if not fd or not td:
            return 'حدد تاريخ البداية والنهاية.'
    elif mt == 'انتداب':
        if not dest or not branch_ok(dest):
            return 'فرع الانتداب غير مسموح.'
        if not fd:
            return 'حدد تاريخ بداية الانتداب.'
    elif mt == 'إذن':
        if not pd:
            return 'حدد تاريخ الإذن.'
    if fd and td and (fd > td):
        return 'من لا يجوز أن يكون بعد إلى.'
    return None


def parse_date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('التاريخ غير صحيح')
