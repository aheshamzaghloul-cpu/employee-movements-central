"""Movement change and close confirmation-plan handler."""

from datetime import date
from ..access import movement_is_closed
from ..extensions import db
from ..models import Branch, Movement
from ..validation import parse_date
from .directory import find_branch, find_employee
from .movement_queries import resolve_movement_for_employee


def plan_movement_action(a, intent):
    movement = db.session.get(Movement, int(a['movement_id'])) if a.get('movement_id') else None
    if not movement and a.get('employee_id'):
        movement, multiple = resolve_movement_for_employee(a['employee_id'], a.get('movement_type'))
        if multiple:
            return {'title': 'تحديد الحركة', 'error': 'يوجد أكثر من حركة مطابقة. اذكر رقم الحركة.'}
    if not movement and a.get('employee_name'):
        e, matches = find_employee(a.get('employee_name'))
        if not e and matches:
            return {'title': 'تحديد الموظف', 'choices': matches, 'error': 'حدد الموظف المقصود.'}
        if e:
            movement, multiple = resolve_movement_for_employee(e.id, a.get('movement_type'))
            if multiple:
                return {'title': 'تحديد الحركة', 'error': 'يوجد أكثر من حركة مطابقة للموظف. اذكر رقم الحركة.'}
    if not movement:
        return {'title': 'إدارة الحركة', 'error': 'لم أجد الحركة المطلوبة.'}
    if intent == 'movement_delete':
        return {'title': 'تأكيد حذف الحركة', 'plan': {'kind': intent, 'id': movement.id},
                'preview': f'إخفاء الحركة رقم {movement.id} الخاصة بالموظف «{movement.employee.full_name}» مع الاحتفاظ بسجلها.'}
    if intent == 'movement_close':
        if movement.movement_type != 'انتداب':
            return {'title': 'إنهاء الانتداب', 'error': 'الحركة المحددة ليست انتدابًا.'}
        close_date = parse_date(a.get('close_date') or '') or date.today()
        if movement.from_date and close_date < movement.from_date:
            return {'title': 'إنهاء الانتداب', 'error': 'تاريخ الإغلاق لا يجوز أن يسبق بداية الانتداب.'}
        return {'title': 'تأكيد إنهاء الانتداب',
                'plan': {'kind': intent, 'id': movement.id, 'close_date': close_date.isoformat(),
                         'reason': a.get('reason') or 'إغلاق الانتداب وعودة الموظف لفرعه الأصلي'},
                'preview': f'إنهاء الانتداب رقم {movement.id} للموظف «{movement.employee.full_name}» بتاريخ {close_date}.'}
    if movement.movement_type == 'انتداب' and movement_is_closed(movement):
        return {'title': 'تعديل الانتداب', 'error': 'الانتداب مغلق. أعد فتحه أولًا قبل تمديد المدة أو تعديل بياناته.'}
    dest = None
    if a.get('destination_branch_id'):
        dest = db.session.get(Branch, int(a['destination_branch_id']))
    elif a.get('destination_name'):
        dest, matches = find_branch(a.get('destination_name'))
        if not dest and matches:
            return {'title': 'تحديد فرع الانتداب', 'choices': matches, 'error': 'حدد فرع الانتداب.'}
    mt = a.get('movement_type') or movement.movement_type
    leave = a.get('leave_type') if a.get('leave_type') is not None else movement.leave_type
    fd = a.get('from_date') or (movement.from_date.isoformat() if movement.from_date else None)
    td = None if a.get('open_assignment') else (a.get('to_date') or (movement.to_date.isoformat() if movement.to_date else None))
    pd = a.get('permission_date') or (movement.permission_date.isoformat() if movement.permission_date else None)
    dest_id = dest.id if dest else movement.destination_branch_id
    from ..validation import validate_movement_fields, movement_overlaps
    err = validate_movement_fields(mt, leave, dest_id, fd, td, pd)
    if err:
        return {'title': 'تعديل الحركة', 'error': err}
    if mt == 'انتداب' and (not dest_id or not db.session.get(Branch, dest_id) or not db.session.get(Branch, dest_id).is_active):
        return {'title': 'تعديل الانتداب', 'error': 'فرع الانتداب غير موجود أو غير نشط.'}
    overlap = movement_overlaps(movement.employee_id, mt, fd, td, pd, movement.id)
    if overlap:
        return {'title': 'تعديل الحركة', 'error': overlap}
    updates = {'movement_type': mt, 'leave_type': leave, 'destination_branch_id': dest_id,
               'from_date': fd, 'to_date': td, 'permission_date': pd}
    return {'title': 'تأكيد تعديل الحركة', 'plan': {'kind': intent, 'id': movement.id, 'updates': updates},
            'preview': f'تعديل الحركة رقم {movement.id} للموظف «{movement.employee.full_name}».'}
