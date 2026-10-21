"""Assistant read-action authorization and dispatch boundary.

Specialized read handlers live in focused modules; this module preserves the
public API and performs the capability checks before dispatch.
"""

from ..access import can
from .read_helpers import (
    _latest_current_movements as _latest_current_movements,
    _load_candidate_records as _load_candidate_records,
    _movement_status_text as _movement_status_text,
    _visible_branch as _visible_branch,
    employee_status_text as employee_status_text,
    render_branch_entry as render_branch_entry,
)
from .read_movement_handlers import (
    handle_employee_movements,
    handle_employee_status,
    handle_governorate_assignments_today,
    handle_movement_people_today,
)
from .read_directory_handlers import (
    handle_branch_status,
    handle_employee_info,
    handle_governorate_employees,
)


def render_read(a):
    """Authorize and dispatch one read-only assistant intent."""
    intent = a.get('intent')
    # Read actions enforce their own capability at the service boundary. A user
    # reaching the assistant endpoint is not, by itself, authorized to inspect
    # status, histories, branch occupancy, or report-level operational details.
    report_intents = {
        'employee_status', 'employee_movements', 'branch_status', 'branch_info',
        'branch_entry', 'governorate_employees', 'governorate_assignments_today',
        'movement_people_today',
    }
    if intent in report_intents and not can('view_reports'):
        return {'title': 'الصلاحيات', 'error': 'لا تملك صلاحية عرض التقارير والحالة التشغيلية.'}
    if intent == 'employee_info' and not (can('manage_employees') or can('view_reports')):
        return {'title': 'الصلاحيات', 'error': 'لا تملك صلاحية دليل الموظفين أو التقارير.'}

    handlers = {
        'movement_people_today': handle_movement_people_today,
        'governorate_assignments_today': handle_governorate_assignments_today,
        'governorate_employees': handle_governorate_employees,
        'employee_status': handle_employee_status,
        'employee_info': handle_employee_info,
        'employee_movements': handle_employee_movements,
    }
    handler = handlers.get(intent)
    if handler is not None:
        return handler(a)
    if intent in ('branch_status', 'branch_info'):
        return handle_branch_status(a, intent)

    # لا تعرض أمثلة محفوظة عند تعذر التصنيف؛ اترك المساعد يطلب التوضيح بصورة طبيعية.
    return {'title': 'المساعد الذكي', 'answer': 'ما زلت أحتاج إلى تحديد المقصود من طلبك.'}
