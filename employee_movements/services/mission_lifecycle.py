"""Mission lifecycle domain operations.

Keeps state-changing mission operations out of the HTTP blueprint.
"""

from datetime import datetime

from ..access import log, me
from ..extensions import db
from ..validation import record_movement_history


def close_mission(movement):
    """Close a validated mission and record the user who performed the closure."""
    actor = me()
    now = datetime.utcnow()
    movement.mission_state = 'مغلقة'
    movement.closed_by = actor.id if actor else None
    movement.closed_at = now
    movement.modified_by = actor.id if actor else None
    movement.modified_at = now
    record_movement_history(
        movement, movement.status, movement.status, 'MISSION_CLOSE',
        'إغلاق المأمورية بعد مراجعة بياناتها',
    )
    log('MISSION_CLOSE', 'Movement', movement.id, 'إغلاق المأمورية')
    db.session.commit()


def reopen_mission(movement):
    """Reopen a validated mission and clear the current closure attribution."""
    actor = me()
    movement.mission_state = 'تحت التحرير'
    movement.closed_by = None
    movement.closed_at = None
    movement.modified_by = actor.id if actor else None
    movement.modified_at = datetime.utcnow()
    record_movement_history(
        movement, movement.status, movement.status, 'MISSION_REOPEN',
        'إعادة فتح المأمورية للتعديل',
    )
    log('MISSION_REOPEN', 'Movement', movement.id, 'إعادة فتح المأمورية')
    db.session.commit()


def apply_mission_edit(movement, destination, from_date, to_date):
    """Apply a validated mission edit and audit it without deciding authorization."""
    old = (movement.destination_branch_id, movement.from_date, movement.to_date)
    movement.destination_branch_id = destination.id
    movement.from_date = from_date
    movement.to_date = to_date
    movement.modified_by = me().id
    movement.modified_at = datetime.utcnow()
    record_movement_history(
        movement, movement.status, movement.status, 'MISSION_EDIT',
        f'تعديل بيانات المأمورية: جهة={destination.name}، من={from_date}، إلى={to_date or "انتداب مفتوح"}',
    )
    log('MISSION_EDIT', 'Movement', movement.id, f'{old} -> {(destination.id, from_date, to_date)}')
    db.session.commit()


def execute_edit_request(request_row, movement, destination, from_date, to_date, final_state, notes):
    """Apply a reviewed edit request, record its resolution, and commit atomically."""
    movement.destination_branch_id = destination.id
    movement.from_date = from_date
    movement.to_date = to_date
    actor = me()
    now = datetime.utcnow()
    movement.mission_state = final_state
    if final_state == 'مغلقة':
        movement.closed_by = actor.id if actor else None
        movement.closed_at = now
    else:
        movement.closed_by = None
        movement.closed_at = None
    movement.modified_by = actor.id if actor else None
    movement.modified_at = now
    request_row.status = 'تم التنفيذ'
    request_row.reviewed_by = me().id
    request_row.reviewed_at = datetime.utcnow()
    request_row.manager_notes = notes
    request_row.final_state = final_state
    record_movement_history(
        movement, movement.status, movement.status, 'MISSION_EDIT_REQUEST_EXECUTED',
        f'تنفيذ طلب تعديل #{request_row.id}; الحالة النهائية={final_state}; السبب={request_row.reason}; ملاحظات={notes}',
    )
    log(
        'MISSION_EDIT_REQUEST_EXECUTED', 'MissionEditRequest', request_row.id,
        f'المأمورية #{movement.id} أصبحت {final_state}',
    )
    db.session.commit()
