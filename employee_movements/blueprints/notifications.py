"""Unified operational follow-up and notification center."""

from datetime import date, timedelta

from flask import Blueprint, render_template

from ..access import bids, req, scope_governorate_id
from ..constants import ASSIGNMENT_ALERT_DAYS
from ..extensions import db
from ..models import Employee, Movement

bp = Blueprint('notifications', __name__)


def _followup_rows():
    """Build deterministic, permission-scoped operational attention items."""
    branch_ids = bids()
    if not branch_ids:
        return []

    today = date.today()
    limit = today + timedelta(days=ASSIGNMENT_ALERT_DAYS)
    rows = (
        Movement.query
        .join(Employee)
        .filter(
            Employee.branch_id.in_(branch_ids),
            Employee.is_active == True,
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
            Movement.assignment_state != 'مغلق',
        )
        .order_by(Movement.to_date.asc().nullsfirst(), Movement.id.asc())
        .all()
    )

    items = []
    for m in rows:
        if not m.employee:
            continue
        if m.to_date is None:
            items.append({
                'id': f'open-{m.id}',
                'movement_id': m.id,
                'employee': m.employee,
                'level': 'info',
                'label': 'انتداب مفتوح',
                'title': f'انتداب مفتوح يحتاج مراجعة: {m.employee.full_name}',
                'detail': 'لا يوجد تاريخ نهاية مسجل. راجع الحالة وحدد الإجراء المناسب عند الحاجة.',
                'action_label': 'فتح الحركة',
                'action_url': f'/movements/{m.id}/edit',
                'employee_url': f'/employee/{m.employee.id}',
                'date': None,
                'sort': 3,
            })
            continue

        if m.to_date < today:
            level, label, sort = 'urgent', 'منتهية', 0
            detail = f'انتهت في {m.to_date}. يلزم مراجعة الحركة وإغلاقها أو اتخاذ الإجراء المناسب.'
        elif m.to_date <= limit:
            level, label, sort = 'warning', 'قرب الانتهاء', 1
            detail = f'تنتهي في {m.to_date}. راجع الحالة قبل انتهاء المدة.'
        else:
            continue

        items.append({
            'id': f'assignment-{m.id}',
            'movement_id': m.id,
            'employee': m.employee,
            'level': level,
            'label': label,
            'title': f'{label}: {m.employee.full_name}',
            'detail': detail,
            'action_label': 'مراجعة الحركة',
            'action_url': f'/movements/{m.id}/edit',
            'employee_url': f'/employee/{m.employee.id}',
            'date': m.to_date,
            'sort': sort,
        })

    items.sort(key=lambda x: (x['sort'], x['date'] or date.max, x['movement_id']))
    return items


@bp.get('/notifications')
@req
def notifications():
    items = _followup_rows()
    return render_template(
        'notifications.html',
        notification_items=items,
        notification_count=len(items),
        scope_selected=scope_governorate_id(),
    )


@bp.get('/api/notifications')
@req
def notifications_items():
    """Return the scoped operational items for the header notification center."""
    items = _followup_rows()
    return {
        'count': len(items),
        'items': [{
            'id': item['id'],
            'level': item['level'],
            'label': item['label'],
            'title': item['title'],
            'detail': item['detail'],
            'action_label': item['action_label'],
            'action_url': item['action_url'],
            'employee_url': item['employee_url'],
            'branch': item['employee'].branch.name if item['employee'].branch else '—',
            'code': item['employee'].job_code or '',
        } for item in items]
    }


@bp.get('/api/notifications/summary')
@req
def notifications_summary():
    items = _followup_rows()
    return {
        'count': len(items),
        'urgent': sum(1 for x in items if x['level'] == 'urgent'),
        'warning': sum(1 for x in items if x['level'] == 'warning'),
        'info': sum(1 for x in items if x['level'] == 'info'),
    }
