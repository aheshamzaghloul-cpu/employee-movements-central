"""Shared, read-only helpers for assistant record rendering."""

from datetime import date

from ..access import can
from ..extensions import db
from ..models import Branch, EntryAssignment, EntryAssignmentBranch, Movement
from ..movement_state import assignment_open_filter



def _load_candidate_records(model, candidate_ids):
    """Load candidate records in one query while preserving candidate order."""
    ids = []
    seen = set()
    for value in candidate_ids or []:
        try:
            item_id = int(value)
        except (TypeError, ValueError):
            continue
        if item_id not in seen:
            seen.add(item_id)
            ids.append(item_id)
    if not ids:
        return []
    records = model.query.filter(model.id.in_(ids)).all()
    by_id = {record.id: record for record in records}
    return [by_id[item_id] for item_id in ids if item_id in by_id]


def _latest_current_movements(employee_ids, on_date=None):
    """Return one latest current movement per employee without loading duplicates."""
    ids = {int(value) for value in (employee_ids or []) if value is not None}
    if not ids:
        return {}
    today = on_date or date.today()
    current_filter = db.or_(
        (
            (Movement.movement_type == 'إجازة')
            & (Movement.from_date <= today)
            & (Movement.to_date >= today)
        ),
        (
            (Movement.movement_type == 'انتداب')
            & assignment_open_filter(Movement)
            & (Movement.from_date <= today)
            & (db.or_(Movement.to_date == None, Movement.to_date >= today))
        ),
        (Movement.movement_type == 'إذن') & (Movement.permission_date == today),
    )
    latest_ids = (
        db.session.query(db.func.max(Movement.id).label('movement_id'))
        .filter(
            Movement.employee_id.in_(ids),
            Movement.is_active == True,
            current_filter,
        )
        .group_by(Movement.employee_id)
        .subquery()
    )
    rows = Movement.query.filter(Movement.id.in_(db.select(latest_ids.c.movement_id))).all()
    return {movement.employee_id: movement for movement in rows}


def _visible_branch(b):
    # Read-only branch facts are global; all mutation actions re-check work scope.
    governorate = getattr(b, 'governorate', None) if b else None
    return bool(b and b.is_active and governorate and governorate.is_active and can('view_reports'))


def render_branch_entry(a):
    br = db.session.get(Branch, a.get('branch_id')) if a.get('branch_id') else None
    if not br:
        matches = _load_candidate_records(Branch, a.get('candidate_ids', []))
        if len(matches) == 1:
            br = matches[0]
        elif matches:
            return {
                'title': 'تحديد الفرع',
                'error': 'وجدت أكثر من فرع مطابق. اختر الفرع المقصود.',
                'choices': matches,
            }
        else:
            return {
                'title': 'تحديد الفرع',
                'error': 'لم أجد فرعًا مطابقًا. اكتب اسم الفرع بصورة أوضح.',
            }
    link = (
        EntryAssignmentBranch.query.join(EntryAssignment)
        .filter(EntryAssignmentBranch.branch_id == br.id, EntryAssignment.is_active == True)
        .first()
    )
    if not link or not link.assignment or (not link.assignment.employee):
        return {
            'title': 'مسؤول إدخال الفرع',
            'answer': f'الفرع: {br.name} — لا يوجد مسؤول إدخال مكلف حاليًا بهذا الفرع.',
        }
    e = link.assignment.employee
    return {
        'title': 'مسؤول إدخال الفرع',
        'answer': f'الفرع: {br.name}\nمسؤول الإدخال: {e.full_name}\nالمشرف: {(link.assignment.supervisor.full_name if link.assignment.supervisor else 'غير محدد')}',
    }


def _movement_status_text(m):
    if not m:
        return 'لا توجد حركة حالية'
    if m.movement_type == 'إجازة':
        return f'إجازة — {m.leave_type or ''} — حتى {m.to_date}'
    if m.movement_type == 'انتداب':
        return (
            f'انتداب مفتوح — {(m.destination.name if m.destination else 'غير محدد')}'
            if m.to_date is None
            else f'انتداب — {(m.destination.name if m.destination else 'غير محدد')} — حتى {m.to_date}'
        )
    return 'إذن اليوم'


def employee_status_text(e):
    today = date.today()
    active = (
        Movement.query.filter_by(employee_id=e.id, is_active=True)
        .filter(
            (
                (
                    (Movement.movement_type == 'إجازة')
                    & (Movement.from_date <= today)
                    & (Movement.to_date >= today)
                )
                | (
                    (Movement.movement_type == 'انتداب')
                    & assignment_open_filter(Movement)
                    & (Movement.from_date <= today)
                    & ((Movement.to_date == None) | (Movement.to_date >= today))
                )
                | (Movement.movement_type == 'إذن') & (Movement.permission_date == today)
            ),
        )
        .order_by(Movement.id.desc())
        .first()
    )
    return _movement_status_text(active)
