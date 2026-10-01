"""Capability menu shown in the assistant: only actions the current role may perform."""

from ..access import can


def capability_groups():
    """Return menu groups ``[{'group': str, 'items': [...]}]`` filtered by permissions."""
    groups = [
        {
            'group': 'استعلامات الموظفين',
            'items': [
                {
                    'label': 'حالة موظف',
                    'prompt': 'ما حالة الموظف ؟',
                    'icon': 'person',
                    'kind': 'query',
                },
                {
                    'label': 'سجل حركات موظف',
                    'prompt': 'اعرض سجل حركات الموظف ؟',
                    'icon': '📋',
                    'kind': 'query',
                },
                {
                    'label': 'بيانات موظف',
                    'prompt': 'اعرض بيانات الموظف ؟',
                    'icon': '🪪',
                    'kind': 'query',
                },
            ],
        },
        {
            'group': 'استعلامات الفروع والحركات',
            'items': [
                {'label': 'حالة فرع', 'prompt': 'ما حالة موظفي فرع ؟', 'icon': '🏢', 'kind': 'query'},
                {
                    'label': 'حالة الموظفين الآن',
                    'prompt': 'اعرض حالة الموظفين الآن',
                    'icon': '📊',
                    'kind': 'query',
                },
                {
                    'label': 'الحركات المنتهية قريبًا',
                    'prompt': 'اعرض الحركات التي تنتهي قريبًا',
                    'icon': 'clock',
                    'kind': 'query',
                },
            ],
        },
    ]
    if can('manage_movements'):
        groups.append(
            {
                'group': 'تسجيل الحركات',
                'items': [
                    {
                        'label': 'إجازة',
                        'prompt': 'تسجيل إجازة للموظف ',
                        'icon': '🌿',
                        'kind': 'action',
                    },
                    {
                        'label': 'انتداب',
                        'prompt': 'تسجيل انتداب للموظف ',
                        'icon': 'assignment',
                        'kind': 'action',
                    },
                    {
                        'label': 'إذن',
                        'prompt': 'تسجيل إذن للموظف ',
                        'icon': 'permission',
                        'kind': 'action',
                    },
                ],
            },
        )
    if can('manage_employees'):
        groups.append(
            {
                'group': 'إدارة الموظفين',
                'items': [
                    {
                        'label': 'إضافة موظف',
                        'prompt': 'أريد إضافة موظف',
                        'icon': 'add',
                        'kind': 'action',
                        'url': '/employees',
                    },
                    {
                        'label': 'تعديل موظف',
                        'prompt': 'أريد تعديل بيانات موظف',
                        'icon': 'edit',
                        'kind': 'action',
                        'url': '/employees/edit-data',
                    },
                    {
                        'label': 'حذف موظف',
                        'prompt': 'أريد حذف موظف',
                        'icon': 'delete',
                        'kind': 'action',
                        'url': '/employees',
                    },
                    {
                        'label': 'الموظفون المستقيلون',
                        'prompt': 'اعرض الموظفين المستقيلين',
                        'icon': 'restore',
                        'kind': 'query',
                        'url': '/employees/resigned',
                    },
                ],
            },
        )
    if can('manage_structure'):
        groups.append(
            {
                'group': 'الإدارة التنظيمية',
                'items': [
                    {
                        'label': 'المحافظات',
                        'prompt': 'أريد إدارة المحافظات',
                        'icon': 'map',
                        'kind': 'action',
                        'url': '/governorates',
                    },
                    {
                        'label': 'الفروع',
                        'prompt': 'أريد إدارة الفروع',
                        'icon': '🏬',
                        'kind': 'action',
                        'url': '/branches',
                    },
                    {
                        'label': 'المدخل الأول',
                        'prompt': 'أريد إدارة المدخلين الأوائل',
                        'icon': '👥',
                        'kind': 'action',
                        'url': '/structure',
                    },
                    {
                        'label': 'الاستبدال',
                        'prompt': 'أريد تنفيذ الاستبدال',
                        'icon': '🔁',
                        'kind': 'action',
                        'url': '/replacement',
                    },
                ],
            },
        )
    if can('manage_users'):
        groups.append(
            {
                'group': 'المستخدمون والصلاحيات',
                'items': [
                    {
                        'label': 'المستخدمون',
                        'prompt': 'أريد إدارة المستخدمين',
                        'icon': 'person',
                        'kind': 'action',
                        'url': '/users',
                    },
                    {
                        'label': 'الأدوار والصلاحيات',
                        'prompt': 'أريد إدارة الأدوار والصلاحيات',
                        'icon': '🔐',
                        'kind': 'action',
                        'url': '/users',
                    },
                    {
                        'label': 'تفويض المشرفين',
                        'prompt': 'أريد إدارة تفويضات المشرفين',
                        'icon': 'delegation',
                        'kind': 'action',
                        'url': '/delegations',
                    },
                ],
            },
        )
    if can('delete_movements'):
        groups.append(
            {
                'group': 'حذف الحركات',
                'items': [
                    {
                        'label': 'حذف حركة',
                        'prompt': 'أريد حذف حركة',
                        'icon': 'delete',
                        'kind': 'action',
                        'url': '/movements',
                    },
                ],
            },
        )
    if can('view_reports'):
        groups.append(
            {
                'group': 'التقارير والطباعة',
                'items': [
                    {
                        'label': 'تقرير الإجازات',
                        'prompt': 'أريد تقرير الإجازات',
                        'icon': '🌿',
                        'kind': 'report',
                        'url': '/reports/leaves',
                    },
                    {
                        'label': 'تقرير الانتدابات',
                        'prompt': 'أريد تقرير الانتدابات',
                        'icon': 'assignment',
                        'kind': 'report',
                        'url': '/reports/assignments',
                    },
                    {
                        'label': 'تقرير الأذونات',
                        'prompt': 'أريد تقرير الأذونات',
                        'icon': 'permission',
                        'kind': 'report',
                        'url': '/reports/permissions',
                    },
                    {
                        'label': 'طباعة المأموريات',
                        'prompt': 'أريد طباعة المأموريات',
                        'icon': '🖨️',
                        'kind': 'report',
                        'url': '/reports/assignments/print-missions',
                    },
                ],
            },
        )
    if can('view_audit'):
        groups.append(
            {
                'group': 'المتابعة',
                'items': [
                    {
                        'label': 'سجل العمليات',
                        'prompt': 'أريد سجل العمليات',
                        'icon': '🧾',
                        'kind': 'query',
                        'url': '/audit',
                    },
                    {
                        'label': 'القوائم الأساسية',
                        'prompt': 'أريد إدارة القوائم الأساسية',
                        'icon': 'settings',
                        'kind': 'action',
                        'url': '/lookups',
                    },
                ],
            },
        )
    return groups
