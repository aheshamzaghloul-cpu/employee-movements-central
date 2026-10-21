"""Contextual assistant topic choices, filtered by current capabilities."""

from ..access import can


def topic_options(topic):
    """Return contextual next-step choices for a keyword/topic, filtered by role permissions."""
    if topic == 'leave':
        items = [
            {'label': 'تسجيل إجازة', 'prompt': 'تسجيل إجازة', 'icon': '🌿', 'kind': 'action'},
            {
                'label': 'تقرير الإجازات',
                'prompt': 'أريد تقرير الإجازات',
                'icon': '📊',
                'kind': 'report',
            },
            {
                'label': 'حالة إجازة موظف',
                'prompt': 'ما حالة إجازة الموظف ',
                'icon': 'person',
                'kind': 'query',
            },
            {
                'label': 'سجل إجازات موظف',
                'prompt': 'اعرض سجل حركات الموظف ',
                'icon': '📋',
                'kind': 'query',
            },
        ]
        if not can('manage_movements'):
            items = [x for x in items if x['kind'] != 'action']
        if not can('view_reports'):
            items = [x for x in items if x['label'] not in ('تقرير الإجازات',)]
        return {
            'title': 'خيارات الإجازات',
            'answer': 'اختر ما تريد بخصوص الإجازات، أو اكتب طلبك مباشرة.',
            'topic_items': items,
        }
    if topic == 'assignment':
        items = [
            {
                'label': 'تسجيل انتداب',
                'prompt': 'تسجيل انتداب',
                'icon': 'assignment',
                'kind': 'action',
            },
            {
                'label': 'تقرير الانتدابات',
                'prompt': 'أريد تقرير الانتدابات',
                'icon': '📊',
                'kind': 'report',
            },
            {
                'label': 'حالة انتداب موظف',
                'prompt': 'اعرض حالة انتداب الموظف ',
                'icon': 'person',
                'kind': 'query',
            },
            {
                'label': 'سجل انتدابات موظف',
                'prompt': 'اعرض سجل حركات الموظف ',
                'icon': '📋',
                'kind': 'query',
            },
            {
                'label': 'طباعة المأموريات',
                'prompt': 'أريد طباعة المأموريات',
                'icon': '🖨️',
                'kind': 'report',
            },
        ]
        if not can('manage_movements'):
            items = [x for x in items if x['kind'] != 'action']
        if not can('view_reports'):
            items = [x for x in items if x['kind'] != 'report']
        return {
            'title': 'خيارات الانتداب',
            'answer': 'اختر الإجراء أو الاستعلام المطلوب بخصوص الانتدابات.',
            'topic_items': items,
        }
    if topic == 'permission':
        items = [
            {'label': 'تسجيل إذن', 'prompt': 'تسجيل إذن', 'icon': 'permission', 'kind': 'action'},
            {
                'label': 'تقرير الأذونات',
                'prompt': 'أريد تقرير الأذونات',
                'icon': '📊',
                'kind': 'report',
            },
            {
                'label': 'سجل أذونات موظف',
                'prompt': 'اعرض سجل حركات الموظف ',
                'icon': '📋',
                'kind': 'query',
            },
        ]
        if not can('manage_movements'):
            items = [x for x in items if x['kind'] != 'action']
        if not can('view_reports'):
            items = [x for x in items if x['kind'] != 'report']
        return {
            'title': 'خيارات الأذونات',
            'answer': 'اختر ما تريد بخصوص الأذونات، أو اكتب طلبك مباشرة.',
            'topic_items': items,
        }
    if topic == 'employee':
        items = [
            {
                'label': 'إضافة موظف جديد',
                'prompt': 'إضافة موظف جديد',
                'icon': 'add',
                'kind': 'action',
                'url': '/employees',
            },
            {
                'label': 'تعديل بيانات موظف',
                'prompt': 'تعديل بيانات موظف',
                'icon': 'edit',
                'kind': 'action',
                'url': '/employees/edit-data',
            },
            {
                'label': 'البحث عن موظف',
                'prompt': 'ابحث عن موظف',
                'icon': '🔎',
                'kind': 'query',
                'url': '/employees',
            },
            {
                'label': 'الموظفون المستقيلون',
                'prompt': 'اعرض الموظفين المستقيلين',
                'icon': 'restore',
                'kind': 'query',
                'url': '/employees/resigned',
            },
        ]
        if not can('manage_employees'):
            items = [x for x in items if x['kind'] == 'query']
        return {
            'title': 'خيارات الموظفين',
            'answer': 'ما الذي تريد فعله بخصوص الموظفين؟',
            'topic_items': items,
        }
    if topic == 'entry':
        items = []
        if can('manage_structure'):
            items += [
                {
                    'label': 'تعيين مسؤول إدخال الفروع',
                    'prompt': 'أريد تعيين مسؤول إدخال الفروع',
                    'icon': '👥',
                    'kind': 'action',
                },
                {
                    'label': 'إزالة تكليف مسؤول إدخال الفروع',
                    'prompt': 'أريد إزالة تكليف مسؤول إدخال الفروع',
                    'icon': 'remove-role',
                    'kind': 'action',
                },
                {
                    'label': 'إدارة تكليفات إدخال الفروع',
                    'prompt': 'أريد إدارة تكليفات إدخال الفروع',
                    'icon': 'settings',
                    'kind': 'action',
                },
                {
                    'label': 'الفروع المسندة لمسؤول الإدخال',
                    'prompt': 'اعرض الفروع المسندة لمسؤول إدخال الفروع',
                    'icon': '🏬',
                    'kind': 'query',
                },
                {
                    'label': 'موظفو الفروع المسندة',
                    'prompt': 'اعرض موظفي الفروع المسندة لمسؤول الإدخال',
                    'icon': 'person',
                    'kind': 'query',
                },
            ]
        if not items:
            items = [
                {
                    'label': 'عرض مسؤول إدخال الفروع',
                    'prompt': 'اعرض مسؤول إدخال الفروع',
                    'icon': '👥',
                    'kind': 'query',
                },
            ]
        return {
            'title': 'تكليف مسؤول إدخال الفروع',
            'answer': 'هذه المعلومات تخص تكليف إدخال الفروع، وهو تكليف تنظيمي وليس دور تسجيل دخول.',
            'topic_items': items,
        }
    return {'title': 'المساعد الذكي', 'answer': 'اكتب الموضوع الذي تريد المساعدة فيه.'}
