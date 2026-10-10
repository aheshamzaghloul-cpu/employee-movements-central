"""Domain constants: roles, permissions, movement types and import headers."""


ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'المدخل الأول', 'Manager Application Support']


LOGIN_ROLES = ['مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support']


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
    },
    'المدخل الأول': {'manage_employees', 'manage_movements', 'view_reports'},
    # نفس الصلاحيات التشغيلية للمشرف، لكن النطاق يُحدد باختيار محافظة العمل ولا يظهر كاسم مشرف.
    # يعمل كنطاق دعم تشغيلي: نفس تشغيل مشرف المحافظة داخل المحافظة المختارة،
    # ولا يفتح إدارة الحسابات/الهيكل الإداري لمسؤول التطبيق.
    'Manager Application Support': {
        'manage_employees', 'manage_movements', 'view_reports',
    },
}


# Pages that operate inside a single governorate chosen by the active operational role.
OPERATIONAL_SCOPE_ENDPOINTS = frozenset(
    {
        'dashboard.home',
        'employees.employees',
        'movements.movements',
        'reports.reports',
        'reports.employee_type_report',
        'reports.reports_missions',
        # Mission search and print are global read workflows; they must not
        # require selecting an operational work-governorate first. Their
        # route-level authorization still checks can_print_mission().
        'notifications.notifications',
        # Direct operational actions must inherit the same selected-work-governorate
        # as their parent pages; a direct URL/POST must never bypass the scope gate.
        'employees.employee_edit_data',
        'employees.employee_edit',
        'employees.employee_convert_role',
        'employees.employee_resign',
        'employees.employee_delete',
        'employees.resigned_employees',
        'employees.employee_reactivate',
        'employees.employee_card',
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
        'movements.movement_history',
        'reports.employee_type_report_xlsx',
        'reports.employee_type_report_csv',
        'reports.report_csv',
        'missions.mission_edit',
        'missions.mission_edit_save',
        'missions.mission_close',
        'missions.mission_reopen',
        # Global mission print endpoints intentionally stay outside the
        # operational scope gate. Printing does not grant edit/close rights.
    }
)
