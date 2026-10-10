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
    """Return the first movement-overlap validation message without loading all rows."""
    start = parse_date_value(fd)
    end = parse_date_value(td)
    day = parse_date_value(pd)

    def active(q):
        q = q.filter(Movement.employee_id == employee_id, Movement.is_active == True)
        if exclude_id:
            q = q.filter(Movement.id != exclude_id)
        return q

    if mt == 'إذن':
        if day:
            if active(Movement.query.filter(
                Movement.movement_type == 'إذن',
                Movement.permission_date == day,
            )).first():
                return 'يوجد إذن آخر للموظف في نفس التاريخ.'

            if active(Movement.query.filter(
                Movement.from_date.isnot(None),
                Movement.to_date.isnot(None),
                Movement.from_date <= day,
                Movement.to_date >= day,
            )).first():
                return 'تاريخ الإذن يتعارض مع حركة أخرى للموظف.'
        return None

    if not start:
        return None

    open_assignment = active(Movement.query.filter(
        Movement.movement_type == 'انتداب',
        Movement.assignment_state != 'مغلق',
        Movement.from_date.isnot(None),
        Movement.to_date.is_(None),
    ))
    if end is not None:
        open_assignment = open_assignment.filter(Movement.from_date <= end)
    if open_assignment.first():
        return 'يوجد انتداب مفتوح للموظف؛ أغلقه أو عدّل مدته قبل تسجيل حركة متعارضة.'

    dated = active(Movement.query.filter(
        Movement.from_date.isnot(None),
        Movement.to_date.isnot(None),
    ))
    if end is not None:
        dated = dated.filter(
            Movement.from_date <= end,
            Movement.to_date >= start,
        )
    if dated.first():
        return 'فترة الحركة تتعارض مع حركة أخرى للموظف.'

    permission = active(Movement.query.filter(
        Movement.movement_type == 'إذن',
        Movement.permission_date.isnot(None),
    ))
    if end is None:
        permission = permission.filter(Movement.permission_date >= start)
    else:
        permission = permission.filter(
            Movement.permission_date >= start,
            Movement.permission_date <= end,
        )
    if permission.first():
        return 'فترة الحركة تتعارض مع إذن للموظف.'
    return None


def validate_movement_fields(mt, leave_type, dest, fd, td, pd, destination_scope_checked=False):
    if mt not in active_movement_types():
        return 'نوع الحركة غير صحيح.'
    if mt == 'إجازة':
        if not leave_type or leave_type not in active_leave_types():
            return 'نوع الإجازة غير صحيح أو غير محدد.'
        if not fd or not td:
            return 'حدد تاريخ البداية والنهاية.'
    elif mt == 'انتداب':
        # Cross-governorate assignment destinations are allowed only when the
        # calling route has already validated the destination with its role-aware
        # access helper. Other callers retain the default branch-scope check.
        if not dest or (not destination_scope_checked and not branch_ok(dest)):
            return 'فرع الانتداب غير مسموح.'
        if not fd:
            return 'حدد تاريخ بداية الانتداب.'
    elif mt == 'إذن':
        if not pd:
            return 'حدد تاريخ الإذن.'
    if fd and td and (fd > td):
        return 'من لا يجوز أن يكون بعد إلى.'
    return None


def parse_optional_iso_date(v):
    """Parse an optional YYYY-MM-DD filter value without raising."""
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('التاريخ غير صحيح')
