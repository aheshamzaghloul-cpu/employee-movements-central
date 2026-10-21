"""Deterministic parsing for administrative and structure-management requests.

This module classifies messages only. Authorization, validation against current
records, and execution remain in the assistant route/manager layer.
"""

import re
from collections.abc import Callable
from typing import Any


def parse_management_intent(
    text: str,
    has_any: Callable[..., bool],
) -> dict[str, Any] | None:
    """Return the first matching management intent in the legacy rule order."""
    t = text

    if has_any('عدل حساب', 'عدّل حساب', 'تعديل حساب'):
        return {'intent': 'user_edit'}
    if has_any('أنشئ حساب', 'انشئ حساب', 'أضف حساب', 'اضف حساب', 'إنشاء حساب', 'انشاء حساب'):
        return {'intent': 'user_create', 'username': None, 'employee_name': None, 'role': None}
    if has_any('احذف حساب', 'حذف حساب', 'اوقف حساب نهائيا', 'أوقف حساب نهائيًا'):
        match = re.search(r'(?:احذف|حذف|اوقف|أوقف)\s+(?:الحساب\s+)?(.+)$', t, re.I)
        return {'intent': 'user_delete', 'employee_name': match.group(1).strip() if match else None}
    if has_any('غيّر محافظات المستخدم', 'غير محافظات المستخدم', 'حدد محافظات المستخدم', 'عيّن محافظات المستخدم'):
        return {'intent': 'user_set_governorates'}
    if has_any('غيّر فروع المستخدم', 'غير فروع المستخدم', 'حدد فروع المستخدم', 'عيّن فروع المستخدم'):
        return {'intent': 'user_set_branches'}
    if has_any('اضف نوع اجازة', 'أضف نوع إجازة', 'إضافة نوع إجازة'):
        match = re.search(
            r'(?:اضف|أضف|إضافة)\s+(?:نوع\s+)?(?:إجازة|اجازة)\s+(.+)$',
            t,
            re.I,
        )
        return {
            'intent': 'lookup_create',
            'lookup_kind': 'leave',
            'lookup_name': match.group(1).strip() if match else None,
        }
    if has_any('اضف نوع حركة', 'أضف نوع حركة', 'إضافة نوع حركة'):
        match = re.search(r'(?:اضف|أضف|إضافة)\s+(?:نوع\s+)?حركة\s+(.+)$', t, re.I)
        return {
            'intent': 'lookup_create',
            'lookup_kind': 'movement',
            'lookup_name': match.group(1).strip() if match else None,
        }
    if has_any('عطل حساب', 'عطّل حساب', 'أوقف حساب', 'اوقف حساب', 'فعّل حساب', 'فعل حساب'):
        match = re.search(r'(?:عطل|عطّل|أوقف|اوقف|فعّل|فعل)\s+الحساب\s+(.+)$', t, re.I)
        return {'intent': 'user_toggle', 'employee_name': match.group(1).strip() if match else None}
    if has_any('غير كلمة مرور', 'غيّر كلمة المرور', 'تغيير كلمة المرور', 'اعادة كلمة المرور', 'إعادة كلمة المرور'):
        # Never accept a password from chat text. The executor generates a
        # temporary credential locally after explicit confirmation.
        match = re.search(
            r'(?:غيّر|غير|تغيير|اعادة|إعادة)\s+(?:كلمة\s+)?(?:المرور|مرور)\s+'
            r'(?:(?:للحساب|للمستخدم|للموظف|الحساب|المستخدم|الموظف)\s+)+'
            r'(.+?)(?:\s+(?:إلى|الى|to)\s+.+)?$',
            t,
            re.I,
        )
        if not match:
            match = re.search(
                r'(?:غيّر|غير|تغيير|اعادة|إعادة)\s+(?:كلمة\s+)?(?:المرور|مرور)\s+'
                r'(.+?)(?:\s+(?:إلى|الى|to)\s+.+)?$',
                t,
                re.I,
            )
        target = match.group(1).strip(' \t:،,؛;') if match else None
        return {'intent': 'user_password_reset', 'employee_name': target}
    if has_any(
        'عين مدخل أول', 'عيّن مدخل أول', 'اضف مدخل أول', 'أضف مدخل أول',
        'اجعل الموظف مدخل أول', 'أضف دور المدخل الأول', 'اضف دور المدخل الاول',
        'عيّن مسؤول إدخال الفروع', 'تعيين مسؤول إدخال الفروع',
        'أريد تعيين مسؤول إدخال الفروع', 'كلف مسؤول إدخال الفروع',
        'تكليف مسؤول إدخال الفروع',
    ):
        match = re.search(
            r'(?:مسؤول إدخال الفروع|مسؤول إدخال|مدخل أول|مدخل الاول)\s+'
            r'(.+?)(?:\s+(?:على|لفروع|للفروع)\s+(.+))?$',
            t,
            re.I,
        )
        return {
            'intent': 'entry_assign',
            'employee_name': match.group(1).strip() if match else None,
            'branch_name': match.group(2).strip() if match and match.group(2) else None,
        }
    if has_any(
        'ازالة مدخل أول', 'إزالة مدخل أول', 'أزل دور المدخل الأول',
        'شيل دور المدخل الأول', 'إزالة تكليف مسؤول إدخال الفروع',
        'أزل تكليف مسؤول إدخال الفروع', 'إزالة تكليف الإدخال',
    ):
        match = re.search(r'(?:مسؤول إدخال الفروع|مسؤول إدخال|مدخل أول|المدخل الأول)\s+(.+)$', t, re.I)
        return {'intent': 'entry_remove', 'employee_name': match.group(1).strip() if match else None}
    if has_any('اعمل تفويض', 'أنشئ تفويض', 'انشئ تفويض', 'أضف تفويض', 'اضف تفويض'):
        return {'intent': 'delegation_create'}
    if has_any('اضف محافظة', 'أضف محافظة', 'إضافة محافظة', 'انشئ محافظة', 'أنشئ محافظة'):
        match = re.search(r'(?:اضف|أضف|إضافة|انشئ|أنشئ)\s+محافظة\s+(.+)$', t, re.I)
        return {'intent': 'governorate_create', 'governorate_name': match.group(1).strip() if match else None}
    if has_any('عطل المحافظة', 'عطّل المحافظة', 'الغاء تفعيل المحافظة', 'إلغاء تفعيل المحافظة', 'فعل المحافظة', 'فعّل المحافظة'):
        match = re.search(
            r'(?:عطل|عطّل|الغاء تفعيل|إلغاء تفعيل|فعل|فعّل)\s+(?:المحافظة\s+)?(.+)$',
            t,
            re.I,
        )
        return {'intent': 'governorate_toggle', 'governorate_name': match.group(1).strip() if match else None}
    if has_any('عدل محافظة', 'عدّل محافظة', 'تعديل محافظة'):
        match = re.search(r'(?:عدل|عدّل|تعديل)\s+محافظة\s+(.+?)\s+(?:الى|إلى)\s+(.+)$', t, re.I)
        return {
            'intent': 'governorate_edit',
            'governorate_name': match.group(1).strip() if match else None,
            'new_name': match.group(2).strip() if match else None,
        }
    if has_any('اضف فرع', 'أضف فرع', 'إضافة فرع', 'انشئ فرع', 'أنشئ فرع'):
        match = re.search(
            r'(?:اضف|أضف|إضافة|انشئ|أنشئ)\s+فرع\s+(.+?)'
            r'(?:\s+(?:في|بمحافظة|بمحافظه|تابع لمحافظة|تابع لمحافظه)\s+)(.+)$',
            t,
            re.I,
        )
        if match:
            return {
                'intent': 'branch_create',
                'branch_name': match.group(1).strip(),
                'governorate_name': match.group(2).strip(),
            }
    if has_any('عطل الفرع', 'عطّل الفرع', 'فعل الفرع', 'فعّل الفرع'):
        match = re.search(r'(?:عطل|عطّل|فعل|فعّل)\s+الفرع\s+(.+)$', t, re.I)
        return {'intent': 'branch_toggle', 'branch_name': match.group(1).strip() if match else None}
    if has_any('احذف الموظف', 'حذف الموظف', 'اخفي الموظف', 'أخفي الموظف'):
        match = re.search(r'(?:احذف|حذف|اخفي|أخفي)\s+(?:الموظف\s+)?(.+)$', t, re.I)
        return {'intent': 'employee_delete', 'employee_name': match.group(1).strip() if match else None}
    if has_any('استرجع الموظف', 'استعادة الموظف', 'اعادة الموظف', 'إعادة الموظف'):
        match = re.search(r'(?:استرجع|استعادة|اعادة|إعادة)\s+(?:الموظف\s+)?(.+)$', t, re.I)
        return {'intent': 'employee_restore', 'employee_name': match.group(1).strip() if match else None}

    return None
