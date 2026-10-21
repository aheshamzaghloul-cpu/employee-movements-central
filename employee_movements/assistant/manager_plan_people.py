"""Employee lifecycle and first-entry assignment plan handlers."""

from sqlalchemy import func

from ..access import actual_roles, user_gov_ids
from ..extensions import db
from ..models import Branch, Employee, EntryAssignment, User
from ..validation import parse_date, valid_email
from ..services.entity_matching import (
    conflicting_employee_code, employee_write_snapshot,
)
from ..services.entity_integrity import employee_name_conflict
from .directory import find_branch, find_employee
from .manager_resolvers import resolve_active_supervisor_by_name


def plan_employee_create(a, intent):
    name = (a.get('employee_name') or a.get('full_name') or '').strip()
    raw_branch_id = a.get('branch_id')
    branch_id = None
    if isinstance(raw_branch_id, int) and not isinstance(raw_branch_id, bool) and raw_branch_id > 0:
        branch_id = raw_branch_id
    elif isinstance(raw_branch_id, str) and raw_branch_id.isdigit() and int(raw_branch_id) > 0:
        branch_id = int(raw_branch_id)
    branch = db.session.get(Branch, branch_id) if branch_id else None
    if not branch and a.get('branch_name'):
        branch, matches = find_branch(a['branch_name'])
        if not branch and matches:
            return {'title': 'تحديد الفرع', 'choices': matches, 'error': 'وجدت أكثر من فرع مطابق.'}
    if not name or not branch:
        return {'title': 'إضافة موظف', 'error': 'أحتاج اسم الموظف والفرع.'}
    if not branch.is_active:
        return {'title': 'إضافة موظف', 'error': 'الفرع غير نشط.'}
    if len(name) > 250:
        return {'title': 'إضافة موظف', 'error': 'اسم الموظف يتجاوز 250 حرفًا.'}
    if employee_name_conflict(name, branch.id):
        return {'title': 'إضافة موظف', 'error': 'يوجد اسم مطابق داخل الفرع أو صيغة بديلة مؤكدة مرتبطة بموظف آخر.'}
    job_title = (a.get('job_title') or '').strip()
    job_code = (a.get('job_code') or '').strip()
    hire_date = (a.get('hire_date') or '').strip()
    if not job_title or len(job_title) > 200 or not job_code or len(job_code) > 100:
        return {'title': 'إضافة موظف', 'error': 'أحتاج المسمى الوظيفي والكود الوظيفي ضمن الحدود المسموحة.'}
    if not hire_date or not parse_date(hire_date):
        return {'title': 'إضافة موظف', 'error': 'أحتاج تاريخ تعيين صحيحًا قبل إعداد خطة الإضافة.'}
    email = (a.get('email') or '').strip().lower() or None
    if email and not valid_email(email):
        return {'title': 'إضافة موظف', 'error': 'البريد الإلكتروني غير صحيح.'}
    if email and Employee.query.filter(Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == email).first():
        return {'title': 'إضافة موظف', 'error': 'البريد الإلكتروني مستخدم بالفعل لموظف آخر.'}
    code = (a.get('employee_code') or '').strip() or None
    job_code = job_code or None
    if code and conflicting_employee_code(code):
        return {'title': 'إضافة موظف', 'error': 'كود الموظف أو أحد بدائله الرقمية مستخدم بالفعل.'}
    if job_code and conflicting_employee_code(job_code):
        return {'title': 'إضافة موظف', 'error': 'الكود الوظيفي أو أحد بدائله الرقمية مستخدم بالفعل.'}
    return {'title': 'تأكيد إضافة موظف', 'plan': {'kind': intent, 'name': name, 'branch_id': branch.id,
            'email': email, 'employee_code': code, 'job_title': job_title, 'job_code': job_code,
            'hire_date': hire_date, 'company_phone': a.get('company_phone'), 'personal_phone': a.get('personal_phone')},
            'preview': f'إضافة الموظف «{name}» إلى فرع «{branch.name}»'}


def plan_entry_action(a, intent):
    e = db.session.get(Employee, int(a['employee_id'])) if a.get('employee_id') else None
    if not e and a.get('employee_name'):
        e, matches = find_employee(a['employee_name'])
        if not e and matches:
            return {'title': 'تحديد الموظف', 'choices': matches, 'error': 'حدد الموظف المقصود.'}
    if not e:
        return {'title': 'مسؤول إدخال الفروع', 'error': 'لم أجد الموظف المطلوب.'}
    active = EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first()
    if intent == 'entry_remove':
        if not active:
            return {'title': 'مسؤول إدخال الفروع', 'error': 'لا يوجد تكليف إدخال نشط لهذا الموظف.'}
        return {'title': 'تأكيد إزالة تكليف الإدخال', 'plan': {'kind': intent, 'id': active.id},
                'preview': f'إزالة تكليف مسؤول إدخال الفروع من «{e.full_name}»'}
    if intent == 'entry_assign':
        if active:
            return {'title': 'مسؤول إدخال الفروع', 'error': 'الموظف لديه تكليف إدخال نشط بالفعل.'}
        branches = []
        for bid in (a.get('branch_ids') or []):
            try:
                b = db.session.get(Branch, int(bid))
            except (TypeError, ValueError):
                b = None
            if b:
                branches.append(b)
        if not branches and a.get('branch_id'):
            try:
                b = db.session.get(Branch, int(a['branch_id']))
            except (TypeError, ValueError):
                b = None
            if b:
                branches.append(b)
        if not branches and a.get('branch_names'):
            for name in a.get('branch_names'):
                b, matches = find_branch(name)
                if not b:
                    if matches:
                        return {'title': 'تحديد الفروع', 'choices': matches, 'error': 'وجدت أكثر من فرع مطابق؛ حدد الفروع بشكل أوضح.'}
                    return {'title': 'تحديد الفروع', 'error': f'لم أجد الفرع «{name}».'}
                branches.append(b)
        if not branches and a.get('branch_name'):
            b, matches = find_branch(a['branch_name'])
            if not b and matches:
                return {'title': 'تحديد الفرع', 'choices': matches, 'error': 'حدد فرع المسؤولية.'}
            if b:
                branches.append(b)
        if not branches:
            branches = [e.branch]
        # لا تسمح بإسناد فرع غير نشط أو فرع خارج محافظة المشرف.
        if any((not b.is_active) for b in branches):
            return {'title': 'مسؤول إدخال الفروع', 'error': 'كل الفروع المختارة يجب أن تكون نشطة.'}
        branches = list({b.id: b for b in branches}.values())
        sup = db.session.get(User, int(a['supervisor_id'])) if a.get('supervisor_id') else None
        if not sup and a.get('supervisor_name'):
            sup = resolve_active_supervisor_by_name(a['supervisor_name'])
        if not sup:
            return {'title': 'مسؤول إدخال الفروع', 'error': 'اذكر مشرف المحافظة المسؤول عن التكليف باسمه.'}
        if 'مشرف محافظة' not in actual_roles(sup) or not sup.is_active:
            return {'title': 'مسؤول إدخال الفروع', 'error': 'مشرف المحافظة المسؤول غير صالح.'}
        if any(b.governorate_id not in user_gov_ids(sup) for b in branches):
            return {'title': 'مسؤول إدخال الفروع', 'error': 'كل الفروع يجب أن تقع داخل المحافظات المسندة إلى المشرف.'}
        return {'title': 'تأكيد تكليف مسؤول إدخال الفروع', 'plan': {'kind': intent, 'employee_id': e.id, 'supervisor_id': sup.id, 'branch_ids': [b.id for b in branches]},
                'preview': f'تكليف «{e.full_name}» بمسؤولية الإدخال، والمشرف «{sup.full_name}»، والفروع: {"، ".join(b.name for b in branches)}'}
    old = active
    new = db.session.get(Employee, int(a['new_employee_id'])) if a.get('new_employee_id') else None
    if not new and a.get('new_employee_name'):
        new, matches = find_employee(a['new_employee_name'])
        if not new and matches:
            return {'title': 'تحديد الموظف البديل', 'choices': matches, 'error': 'وجدت أكثر من موظف مطابق.'}
    if not new:
        return {'title': 'استبدال مسؤول إدخال الفروع', 'error': 'اذكر الموظف البديل.'}
    if EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first():
        return {'title': 'استبدال مسؤول إدخال الفروع', 'error': 'الموظف البديل لديه تكليف إدخال نشط بالفعل.'}
    return {'title': 'تأكيد استبدال مسؤول إدخال الفروع', 'plan': {'kind': intent, 'assignment_id': old.id, 'new_employee_id': new.id},
            'preview': f'استبدال «{e.full_name}» بالموظف «{new.full_name}» مع نقل التكليف.'}


def plan_employee_action(a, intent):
    e = db.session.get(Employee, int(a['employee_id'])) if a.get('employee_id') else None
    if not e and a.get('employee_name'):
        e, matches = find_employee(a['employee_name'])
        if not e and matches:
            return {'title': 'تحديد الموظف', 'choices': matches, 'error': 'وجدت أكثر من موظف مطابق.'}
    if not e:
        return {'title': 'تحديد الموظف', 'error': 'لم أجد الموظف المطلوب.'}
    if intent == 'employee_delete':
        if not e.is_active:
            return {'title': 'الموظف', 'error': 'الموظف غير نشط بالفعل.'}
        return {'title': 'تأكيد إخفاء الموظف', 'plan': {'kind': intent, 'id': e.id, 'identity_snapshot': employee_write_snapshot(e)},
                'preview': f'إخفاء الموظف «{e.full_name}» إداريًا مع الاحتفاظ بسجله وحركاته'}
    if intent == 'employee_restore':
        return {'title': 'تأكيد استعادة الموظف', 'plan': {'kind': intent, 'id': e.id, 'identity_snapshot': employee_write_snapshot(e)},
                'preview': f'استعادة الموظف «{e.full_name}»'}
    updates = {k: a.get(k) for k in ('full_name','email','employee_code','job_title','job_code','company_phone','personal_phone') if a.get(k) is not None}
    if a.get('hire_date'):
        updates['hire_date'] = a.get('hire_date')
    if a.get('branch_name') or a.get('branch_id'):
        b = db.session.get(Branch, int(a['branch_id'])) if a.get('branch_id') else None
        if not b and a.get('branch_name'):
            b, matches = find_branch(a['branch_name'])
            if not b and matches:
                return {'title': 'تحديد الفرع', 'choices': matches, 'error': 'حدد فرع الموظف.'}
        if not b:
            return {'title': 'تحديد الفرع', 'error': 'لم أجد الفرع المطلوب.'}
        updates['branch_id'] = b.id
    if not updates:
        return {'title': 'تعديل الموظف', 'error': 'اذكر البيان الذي تريد تعديله.'}
    if 'email' in updates and updates['email'] and not valid_email(updates['email']):
        return {'title': 'تعديل الموظف', 'error': 'البريد الإلكتروني غير صحيح.'}
    if 'full_name' in updates or 'branch_id' in updates:
        target_branch_id = updates.get('branch_id', e.branch_id)
        target_name = updates.get('full_name', e.full_name)
        if employee_name_conflict(target_name, target_branch_id, exclude_employee_id=e.id):
            return {'title': 'تعديل الموظف', 'error': 'يوجد اسم مطابق داخل الفرع المستهدف أو صيغة بديلة مؤكدة مرتبطة بموظف آخر.'}
    if 'email' in updates and updates['email']:
        other = Employee.query.filter(
            Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == str(updates['email']).strip().lower(), Employee.id != e.id,
        ).first()
        if other:
            return {'title': 'تعديل الموظف', 'error': 'البريد الإلكتروني مستخدم بالفعل لموظف آخر.'}
    for code_field in ('employee_code', 'job_code'):
        if code_field in updates and updates[code_field]:
            if conflicting_employee_code(updates[code_field], exclude_employee_id=e.id):
                return {'title': 'تعديل الموظف', 'error': 'الكود الوظيفي أو أحد بدائله الرقمية مستخدم بالفعل لموظف آخر.'}
    if 'hire_date' in updates and not parse_date(updates['hire_date']):
        return {'title': 'تعديل الموظف', 'error': 'تاريخ التعيين غير صحيح؛ استخدم YYYY-MM-DD.'}
    return {'title': 'تأكيد تعديل الموظف', 'plan': {'kind': intent, 'id': e.id, 'updates': updates, 'identity_snapshot': employee_write_snapshot(e)},
            'preview': f'تعديل بيانات الموظف «{e.full_name}»: ' + '، '.join(f'{k}={v}' for k,v in updates.items())}
