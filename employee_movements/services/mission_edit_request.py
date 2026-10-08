"""Mission edit-request domain operations.

Keeps creation, queue loading and reviewed-request execution out of the HTTP blueprint.
Authorization and HTTP redirects/flash messages remain in the blueprint.
"""

from ..access import log, me
from ..extensions import db
from ..models import Branch, Employee, Governorate, MissionEditRequest, Movement
from ..validation import movement_overlaps
from .mission_lifecycle import execute_edit_request

PENDING_STATUS = 'قيد المراجعة'

def create_mission_edit_request(movement, reason):
    """Create a pending request after authorization and input validation."""
    pending = MissionEditRequest.query.filter_by(
        movement_id=movement.id, status=PENDING_STATUS
    ).first()
    if pending:
        return None

    snapshot = (
        f'الموظف: {movement.employee.full_name if movement.employee else "—"} | '
        f'من: {movement.from_date} | إلى: {movement.to_date} | '
        f'الوجهة: {movement.destination.name if movement.destination else "—"}'
    )
    row = MissionEditRequest(
        movement_id=movement.id,
        requested_by=me().id,
        reason=reason,
        details_snapshot=snapshot,
        status=PENDING_STATUS,
    )
    db.session.add(row)
    db.session.flush()
    log(
        'MISSION_EDIT_REQUEST',
        'MissionEditRequest',
        row.id,
        f'طلب تعديل مأمورية #{movement.id}: {reason}',
    )
    db.session.commit()
    return row


def list_pending_mission_edit_requests(roles, allowed_branch_ids):
    """Load the pending request queue using the same operational scope as before."""
    q = MissionEditRequest.query.filter_by(status=PENDING_STATUS).join(Movement)
    if 'مسؤول التطبيق' not in roles:
        scoped = set(allowed_branch_ids)
        if not scoped:
            q = q.filter(False)
        else:
            q = q.join(Employee, Movement.employee_id == Employee.id).filter(
                Employee.branch_id.in_(scoped)
            )
    return q.order_by(
        MissionEditRequest.created_at.asc(), MissionEditRequest.id.asc()
    ).all()


def mission_edit_request_review_context(request_row):
    """Load the branch/governorate choices needed by the review page."""
    branches = Branch.query.filter(Branch.is_active == True).order_by(Branch.name.asc()).all()
    govs = Governorate.query.filter(Governorate.is_active == True).order_by(Governorate.name.asc()).all()
    return branches, govs


def validate_and_execute_mission_edit_request(
    request_row,
    movement,
    destination,
    from_date,
    to_date,
    final_state,
    notes,
):
    """Validate the reviewed values and execute the existing lifecycle operation.

    Returns a short Arabic error message, or None when execution succeeds.
    """
    if (
        not destination
        or not destination.is_active
        or not from_date
        or final_state not in ('مغلقة', 'تحت التحرير')
    ):
        return 'أكمل بيانات التعديل واختر الحالة النهائية الصحيحة.'
    if to_date and to_date < from_date:
        return 'تاريخ النهاية لا يجوز أن يسبق البداية.'
    if final_state == 'مغلقة' and not to_date:
        return 'لا يمكن حفظ المأمورية مغلقة بدون تاريخ نهاية.'

    overlap = movement_overlaps(
        movement.employee_id,
        'انتداب',
        from_date,
        to_date,
        None,
        movement.id,
    )
    if overlap:
        return overlap

    execute_edit_request(
        request_row,
        movement,
        destination,
        from_date,
        to_date,
        final_state,
        notes,
    )
    return None
