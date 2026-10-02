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
        'manage_users',
        'manage_structure',
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


# Pages that operate inside a single governorate chosen by the admin/manager.
OPERATIONAL_SCOPE_ENDPOINTS = frozenset(
    {
        'dashboard.home',
        'employees.employees',
        'movements.movements',
        'reports.reports',
        'reports.employee_type_report',
        'reports.reports_missions',
        'missions.mission_print_list',
        'missions.mission_print',
        'missions.mission_print_date',
    }
)
