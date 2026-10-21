"""Unified operational follow-up and notification center.

The notification APIs return only a bounded, priority-ordered slice. Totals and
severity metrics are aggregated in SQL so a large history does not need to be
loaded into each request merely to paint the header badge.
"""

import math
from datetime import date, timedelta

from flask import abort, Blueprint, render_template, request, url_for
from sqlalchemy import and_, case, func, or_
from sqlalchemy.orm import joinedload

from ..access import bids, can, movement_is_closed, readable_branch_ids, req, roles, scope_governorate_id
from ..constants import ASSIGNMENT_ALERT_DAYS
from ..models import Branch, Employee, Governorate, Movement
from ..pagination import safe_page_number
from ..movement_state import assignment_closed_filter, assignment_open_filter

bp = Blueprint('notifications', __name__)


def _followup_query():
    """Return a cross-governorate read query and severity expressions."""
    branch_ids = readable_branch_ids()
    if not branch_ids:
        return None, None, None

    today = date.today()
    limit = today + timedelta(days=ASSIGNMENT_ALERT_DAYS)
    closed = assignment_closed_filter(Movement)
    open_state = assignment_open_filter(Movement)
    overdue = and_(open_state, Movement.to_date.is_not(None), Movement.to_date < today)
    near_end = and_(open_state, Movement.to_date >= today, Movement.to_date <= limit)
    open_ended = and_(open_state, Movement.to_date.is_(None))
    missing_destination = and_(open_state, Movement.destination_branch_id.is_(None))
    missing_start = and_(open_state, Movement.from_date.is_(None))
    reversed_dates = and_(Movement.from_date.is_not(None), Movement.to_date.is_not(None), Movement.from_date > Movement.to_date)
    closed_missing_end = and_(closed, Movement.to_date.is_(None))

    needs_attention = or_(
        overdue,
        near_end,
        open_ended,
        missing_destination,
        missing_start,
        reversed_dates,
        closed_missing_end,
    )
    severity = case(
        (or_(overdue, reversed_dates, closed_missing_end), 0),
        (or_(missing_destination, missing_start, near_end), 1),
        (open_ended, 2),
        else_=3,
    )
    query = (
        Movement.query
        .join(Employee, Employee.id == Movement.employee_id)
        .join(Branch, Branch.id == Employee.branch_id)
        .join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(
            Employee.branch_id.in_(branch_ids),
            Employee.is_active == True,
            Branch.is_active == True,
            Governorate.is_active == True,
            Movement.is_active == True,
            Movement.movement_type == 'انتداب',
            needs_attention,
        )
    )
    expressions = {
        'today': today,
        'limit': limit,
        'closed': closed,
        'open_state': open_state,
        'overdue': overdue,
        'near_end': near_end,
        'open_ended': open_ended,
        'missing_destination': missing_destination,
        'missing_start': missing_start,
        'reversed_dates': reversed_dates,
        'closed_missing_end': closed_missing_end,
        'severity': severity,
    }
    return query, severity, expressions


def _followup_stats(query, severity):
    stats = {'total': 0, 'urgent': 0, 'warning': 0, 'info': 0}
    if query is None:
        return stats
    # One grouped aggregate replaces fetching every row to calculate the badge.
    for level, count in query.order_by(None).with_entities(
        severity.label('severity'), func.count(Movement.id)
    ).group_by(severity).all():
        if level == 0:
            stats['urgent'] = int(count)
        elif level == 1:
            stats['warning'] = int(count)
        elif level == 2:
            stats['info'] = int(count)
        stats['total'] += int(count)
    return stats


def _followup_item(m, expressions, *, can_edit=False):
    today = expressions['today']
    limit = expressions['limit']
    closed = movement_is_closed(m)
    if m.from_date and m.to_date and m.from_date > m.to_date:
        level, label, detail = 'urgent', 'تعارض تواريخ', 'تاريخ البداية بعد تاريخ النهاية. راجع السجل وصحح البيانات قبل الاعتماد.'
    elif closed and m.to_date is None:
        level, label, detail = 'urgent', 'تاريخ نهاية مفقود', 'المأمورية مغلقة دون تاريخ نهاية؛ أرسل طلب تعديل إلى الـManager لمعالجة البيانات.'
    elif m.to_date is not None and m.to_date < today and not closed:
        level, label, detail = 'urgent', 'منتهية', f'انتهت في {m.to_date}. راجع الحالة واتخذ الإجراء المناسب.'
    elif m.destination_branch_id is None:
        level, label, detail = 'warning', 'جهة انتداب غير محددة', 'لا توجد جهة انتداب موثقة. راجع سجل الحركة وحدد الجهة الصحيحة.'
    elif m.from_date is None:
        level, label, detail = 'warning', 'تاريخ بداية مفقود', 'تاريخ بداية المأمورية غير مسجل؛ راجع البيانات قبل الاعتماد أو الطباعة.'
    elif m.to_date is not None and m.to_date <= limit and not closed:
        level, label, detail = 'warning', 'قرب الانتهاء', f'تنتهي في {m.to_date}. راجع الحالة قبل انتهاء المدة.'
    else:
        level, label, detail = 'info', 'انتداب مفتوح', 'لا يوجد تاريخ نهاية مسجل. راجع الحالة وحدد الإجراء المناسب عند الحاجة.'

    employee = m.employee
    if can_edit:
        action_label = 'مراجعة وتصحيح الحركة'
        action_url = f'/movements/{m.id}/edit'
    elif can('view_reports'):
        action_label = 'عرض المأمورية'
        action_url = f'/reports/assignments/print-mission/{m.id}'
    else:
        action_label = 'فتح سجل الحركات'
        action_url = '/movements#movement-log'

    return {
        'id': f'assignment-{m.id}',
        'movement_id': m.id,
        'employee': employee,
        'level': level,
        'title': f'{label}: {employee.full_name if employee else "موظف غير محدد"}',
        'label': label,
        'detail': detail,
        'action_label': action_label,
        'action_url': action_url,
        'employee_url': f'/employee/{employee.id}' if employee else '/employees',
        'date': m.to_date,
        'sort': {'urgent': 0, 'warning': 1, 'info': 2}.get(level, 3),
    }


def _followup_rows(*, page=1, page_size=50):
    """Fetch only one page of alert rows and compute full result totals separately."""
    query, severity, expressions = _followup_query()
    stats = _followup_stats(query, severity)
    total = stats['total']
    page_count = max(1, math.ceil(total / page_size))
    page = safe_page_number(page, page_count)
    if query is None or total == 0:
        return [], stats, page, page_count

    rows = (
        query
        .options(
            joinedload(Movement.employee).joinedload(Employee.branch).joinedload(Branch.governorate),
            joinedload(Movement.destination).joinedload(Branch.governorate),
        )
        .order_by(severity.asc(), Movement.to_date.asc().nullsfirst(), Movement.id.asc())
        .limit(page_size)
        .offset((page - 1) * page_size)
        .all()
    )
    # Resolve the actor's edit scope once per page, not once per alert row.
    # The row-level action is only a convenience; every edit endpoint enforces
    # the same policy again on the server.
    supported_mutation_roles = {'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'}
    can_manage = can('manage_movements') and bool(roles() & supported_mutation_roles)
    selected_governorate = scope_governorate_id() if can_manage else None
    editable_branch_ids = set(bids()) if can_manage and selected_governorate else set()
    items = []
    for movement in rows:
        employee = movement.employee
        branch = employee.branch if employee else None
        governorate = branch.governorate if branch else None
        can_edit = bool(
            can_manage
            and selected_governorate
            and not movement_is_closed(movement)
            and movement.is_active
            and branch
            and branch.is_active
            and governorate
            and governorate.is_active
            and governorate.id == int(selected_governorate)
            and branch.id in editable_branch_ids
        )
        items.append(_followup_item(movement, expressions, can_edit=can_edit))
    return items, stats, page, page_count


@bp.get('/notifications')
@req
def notifications():
    if not (can('view_reports') or can('manage_movements')):
        abort(403)
    raw_page = (request.args.get('page') or '1').strip()
    page = safe_page_number(raw_page)
    items, stats, page, page_count = _followup_rows(page=page, page_size=50)
    query_args = request.args.to_dict()
    query_args['page'] = str(max(1, page - 1))
    previous_page_url = url_for('notifications.notifications', **query_args) if page > 1 else None
    query_args['page'] = str(min(page_count, page + 1))
    next_page_url = url_for('notifications.notifications', **query_args) if page < page_count else None
    return render_template(
        'notifications.html',
        notification_items=items,
        notification_count=stats['total'],
        notification_stats=stats,
        notification_page=page,
        notification_page_count=page_count,
        previous_page_url=previous_page_url,
        next_page_url=next_page_url,
        scope_selected=scope_governorate_id(),
    )


@bp.get('/api/notifications')
@req
def notifications_items():
    """Return the highest-priority eight items and globally aggregated metrics."""
    if not (can('view_reports') or can('manage_movements')):
        abort(403)
    items, stats, _, _ = _followup_rows(page=1, page_size=8)
    return {
        **stats,
        'items': [{
            'id': item['id'],
            'level': item['level'],
            'label': item['label'],
            'title': item['title'],
            'detail': item['detail'],
            'action_label': item['action_label'],
            'action_url': item['action_url'],
            'employee_url': item['employee_url'],
            'branch': item['employee'].branch.name if item['employee'] and item['employee'].branch else '—',
            'code': (item['employee'].job_code or '') if item['employee'] else '',
        } for item in items],
    }


@bp.get('/api/notifications/summary')
@req
def notifications_summary():
    if not (can('view_reports') or can('manage_movements')):
        abort(403)
    query, severity, _ = _followup_query()
    return _followup_stats(query, severity)
