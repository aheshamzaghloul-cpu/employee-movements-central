"""Domain constants: roles, permissions, movement types and import headers."""


ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']


LOGIN_ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']

# Bound password input before expensive hash verification and all password writes.
MAX_PASSWORD_LENGTH = 4096


MOVEMENT_TYPES = ['إجازة', 'انتداب', 'إذن']


LEAVE_TYPES = ['سنوية', 'عارضة', 'مصيف', 'وضع']


STATUSES = ['مسجلة']


ASSIGNMENT_ALERT_DAYS = 1


ASSIGNMENT_STATES = ['ساري', 'قرب الانتهاء', 'انتهت المدة']


PERMISSIONS = {
    'manage_users': 'إدارة المستخدمين',
    'manage_structure': 'إدارة المحافظات والفروع',
    'manage_employees': 'إدارة الموظفين',
    'manage_movements': 'تسجيل وتعديل الحركات',
    'view_reports': 'التقارير',
    'view_audit': 'سجل العمليات',
    'delete_movements': 'حذف الحركات',
}


GRANTABLE_BY_SUPERVISOR = {'manage_employees', 'manage_movements', 'view_reports'}


ROLE_DEFAULT_PERMISSIONS = {
    'مسؤول التطبيق': set(PERMISSIONS),
    'مشرف محافظة': {
        'manage_employees',
        'manage_movements',
        'view_reports',
        'delete_movements',
    },
    # نفس الصلاحيات التشغيلية للمشرف، لكن النطاق يُحدد باختيار محافظة العمل ولا يظهر كاسم مشرف.
    # يعمل كنطاق دعم تشغيلي: نفس تشغيل مشرف المحافظة داخل المحافظة المختارة،
    # ولا يفتح إدارة الحسابات/الهيكل الإداري لمسؤول التطبيق.
    'Manager Application Support': {
        'manage_employees', 'manage_movements', 'view_reports', 'delete_movements',
    },
}


# Read-only views that must remain available across all active governorates, even
# before an operational work-governorate is selected. Mixed GET/POST endpoints
# (currently the employee directory) are exempt only for safe HTTP methods; their
# POST handlers remain inside the operational scope gate.
GLOBAL_READ_SCOPE_ENDPOINTS = frozenset(
    {
        'missions.mission_print_list',
        'employees.employee_card',
        'employees.resigned_employees',
        'employees.employees',
        'movements.movements',
        'movements.movement_history',
        'reports.reports',
        'reports.employee_type_report',
        'reports.reports_missions',
        'reports.employee_type_report_xlsx',
        'reports.employee_type_report_csv',
        'reports.report_csv',
        'notifications.notifications',
        'notifications.notifications_items',
        'notifications.notifications_summary',
    }
)


# Pages that operate inside a single governorate chosen by the active operational role.
OPERATIONAL_SCOPE_ENDPOINTS = frozenset(
    {
        'dashboard.home',
        'missions.mission_from_screenshot',
        'missions.mission_from_screenshot_scan',
        'missions.mission_from_screenshot_create',
        'missions.mission_ticket_image_save',
        'missions.mission_edit_request_create',
        'missions.mission_edit_requests',
        'missions.mission_edit_request_review',
        'missions.mission_edit_request_save',
        'structure.add_organizational_entry_role',
        'structure.update_organizational_entry_branches',
        'structure.replace_organizational_entry_from_home',
        'structure.remove_organizational_entry_role',
        'delegations.delegations',
        'delegations.delegation_add',
        'delegations.delegation_revoke',
        'employees.employees',
        # Direct operational actions must inherit the same selected-work-governorate
        # as their parent pages; a direct URL/POST must never bypass the scope gate.
        'employees.employee_edit_data',
        'employees.employee_edit',
        'employees.employee_convert_role',
        'employees.employee_resign',
        'employees.employee_delete',
        'employees.employee_reactivate',
        'movements.movement_employees_api',
        'movements.movement_preflight_api',
        'movements.movements_page_filters_api',
        'movements.movement_create',
        'movements.movement_edit',
        'movements.movement_submit',
        'movements.close_assignment',
        'movements.reopen_assignment',
        'movements.assignment_form',
        'movements.movement_delete',
        'missions.mission_edit',
        'missions.mission_edit_save',
        'missions.mission_close',
        'missions.mission_reopen',
        # Global mission print endpoints intentionally stay outside the
        # operational scope gate. Printing does not grant edit/close rights.
    }
)
