"""Safe execution layer for the in-app application manager assistant.

Gemini never receives live records or secrets. It only describes the user's requested
operation; this module resolves records locally, checks permissions, creates a preview,
and performs the mutation only after explicit confirmation.
"""
from datetime import datetime, date
import secrets
import string

from werkzeug.security import generate_password_hash

from ..access import branch_ok, can, log, me, roles, actual_roles, user_gov_ids
from ..extensions import db
from ..models import (Branch, Employee, Governorate, Lookup, User, UserGovernorate, UserRole, UserPermission,
    UserBranch, EntryAssignment, EntryAssignmentBranch, ApprovalDelegation, SupervisorEntry, Movement)
from ..constants import LOGIN_ROLES, PERMISSIONS, ROLE_DEFAULT_PERMISSIONS
from ..validation import parse_date, valid_email, valid_password
from .directory import find_branch, find_employee
from ..assignments import sync_role_accounts

ADMIN_ROLE = 'مسؤول التطبيق'


def is_app_manager():
    return ADMIN_ROLE in roles()


def _match_gov(name):
    if not name:
        return None, []
    q = str(name).strip().lower()
    rows = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
    exact = [g for g in rows if (g.name or '').strip().lower() == q]
    if len(exact) == 1:
        return exact[0], []
    partial = [g for g in rows if q in (g.name or '').strip().lower()]
    return (partial[0], partial[1:]) if len(partial) == 1 else (None, partial[:10])


def plan(a):
    """Resolve an assistant action into a local, confirmation-ready plan."""
    if not is_app_manager():
        return {'error': 'هذه الأوامر الإدارية متاحة لمسؤول التطبيق فقط.'}
    intent = a.get('intent')
    if intent not in {
        'governorate_create', 'governorate_edit', 'governorate_toggle',
        'branch_create', 'branch_edit', 'branch_toggle',
        'employee_create', 'employee_edit', 'employee_delete', 'employee_restore',
        'user_create', 'user_edit', 'user_toggle', 'user_delete', 'user_password_reset',
        'user_set_governorates', 'user_set_branches',
        'role_grant', 'role_revoke',
        'lookup_create', 'lookup_edit', 'lookup_toggle', 'lookup_delete', 'movement_edit', 'movement_delete', 'movement_close', 'movement_reopen', 'entry_assign', 'entry_remove', 'entry_replace',
        'delegation_create', 'delegation_revoke',
    }:
        return None

    if intent == 'employee_create':
        name = (a.get('employee_name') or a.get('full_name') or '').strip()
        branch = db.session.get(Branch, int(a['branch_id'])) if a.get('branch_id') else None
        if not branch and a.get('branch_name'):
            branch, matches = find_branch(a['branch_name'])
            if not branch and matches:
                return {'title': 'تحديد الفرع', 'choices': matches, 'error': 'وجدت أكثر من فرع مطابق.'}
        if not name or not branch:
            return {'title': 'إضافة موظف', 'error': 'أحتاج اسم الموظف والفرع.'}
        if not branch.is_active:
            return {'title': 'إضافة موظف', 'error': 'الفرع غير نشط.'}
        if Employee.query.filter(Employee.full_name == name, Employee.is_active == True).first():
            return {'title': 'إضافة موظف', 'error': 'يوجد موظف نشط بهذا الاسم بالفعل.'}
        email = (a.get('email') or '').strip() or None
        if email and not valid_email(email):
            return {'title': 'إضافة موظف', 'error': 'البريد الإلكتروني غير صحيح.'}
        code = (a.get('employee_code') or '').strip() or None
        if code and Employee.query.filter_by(employee_code=code).first():
            return {'title': 'إضافة موظف', 'error': 'كود الموظف مستخدم بالفعل.'}
        return {'title': 'تأكيد إضافة موظف', 'plan': {'kind': intent, 'name': name, 'branch_id': branch.id,
                'email': email, 'employee_code': code, 'job_title': a.get('job_title'), 'job_code': a.get('job_code'),
                'hire_date': a.get('hire_date'), 'company_phone': a.get('company_phone'), 'personal_phone': a.get('personal_phone')},
                'preview': f'إضافة الموظف «{name}» إلى فرع «{branch.name}»'}

    if intent.startswith('user_'):
        u = None
        if a.get('user_id'):
            u = db.session.get(User, int(a['user_id']))
        if not u and a.get('username'):
            u = User.query.filter_by(username=a['username'].strip()).first()
        if not u and a.get('employee_name'):
            e, matches = find_employee(a['employee_name'])
            if not e and matches:
                return {'title': 'تحديد المستخدم', 'choices': matches, 'error': 'وجدت أكثر من موظف مطابق.'}
            if e and e.user_id:
                u = db.session.get(User, e.user_id)
        if intent == 'user_create':
            username = (a.get('username') or '').strip()
            full = (a.get('full_name') or a.get('employee_name') or '').strip()
            email = (a.get('email') or '').strip()
            job_title = (a.get('job_title') or '').strip()
            job_code = (a.get('job_code') or '').strip()
            password = a.get('password') or ''
            if not password:
                alphabet = string.ascii_letters + string.digits
                password = ''.join(secrets.choice(alphabet) for _ in range(12))
            role = (a.get('role') or '').strip()
            requested_roles = [r for r in (a.get('roles') or []) if r in LOGIN_ROLES]
            if role in LOGIN_ROLES and role not in requested_roles:
                requested_roles.append(role)
            if not requested_roles or not username or not full or not email or not job_title or not job_code or not valid_password(password):
                return {'title': 'إنشاء حساب', 'error': 'أحتاج اسم المستخدم والاسم والبريد والوظيفة والكود الوظيفي وكلمة مرور صحيحة (8 أحرف على الأقل وتحتوي حروفًا وأرقامًا) ودورًا واحدًا على الأقل.'}
            if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
                return {'title': 'إنشاء حساب', 'error': 'اسم المستخدم أو البريد مستخدم بالفعل.'}
            if not valid_email(email):
                return {'title': 'إنشاء حساب', 'error': 'البريد الإلكتروني غير صحيح.'}
            gov_ids = []
            if 'مشرف محافظة' in requested_roles:
                raw_ids = a.get('governorate_ids') or []
                if raw_ids:
                    try:
                        gov_ids = sorted({int(x) for x in raw_ids})
                    except (TypeError, ValueError):
                        gov_ids = []
                elif a.get('governorate_id'):
                    gov_ids = [int(a['governorate_id'])]
                elif a.get('governorate_names'):
                    for gov_name in a.get('governorate_names'):
                        g, gm = _match_gov(gov_name)
                        if not g:
                            return {'title': 'تحديد المحافظات', 'choices': gm, 'error': f'لم أستطع تحديد المحافظة «{gov_name}».' if not gm else f'يوجد أكثر من محافظة مطابقة لـ «{gov_name}».'}
                        gov_ids.append(g.id)
                    gov_ids = sorted(set(gov_ids))
                elif a.get('governorate_name'):
                    g, gm = _match_gov(a['governorate_name'])
                    if not g and gm:
                        return {'title': 'تحديد المحافظة', 'choices': gm, 'error': 'حدد المحافظة التي سيكلف بها المشرف.'}
                    if g:
                        gov_ids = [g.id]
                if not gov_ids:
                    return {'title': 'إنشاء حساب مشرف', 'error': 'اذكر محافظة واحدة على الأقل سيكلف بها مشرف المحافظة.'}
                active_gov_ids = {g.id for g in Governorate.query.filter(Governorate.id.in_(gov_ids), Governorate.is_active == True).all()}
                if set(gov_ids) != active_gov_ids:
                    return {'title': 'إنشاء حساب مشرف', 'error': 'إحدى المحافظات المحددة غير موجودة أو غير نشطة.'}
            return {
                'title': 'تأكيد إنشاء حساب',
                'plan': {'kind': intent, 'username': username, 'full_name': full, 'email': email,
                         'job_title': job_title, 'job_code': job_code, 'roles': requested_roles, 'governorate_ids': gov_ids},
                'preview': f'إنشاء حساب «{username}» باسم «{full}» بالأدوار: {"، ".join(requested_roles)} — سيُولّد النظام كلمة مرور مؤقتة ويعرضها بعد التنفيذ.',
            }
        if not u:
            return {'title': 'إدارة الحساب', 'error': 'لم أجد حساب المستخدم المطلوب.'}
        if intent == 'user_toggle':
            return {'title': 'تأكيد حالة الحساب', 'plan': {'kind': intent, 'id': u.id, 'new_active': not u.is_active},
                    'preview': f"{'تفعيل' if not u.is_active else 'تعطيل'} حساب «{u.username}»"}
        if intent == 'user_delete':
            if u.id == me().id:
                return {'title': 'حذف الحساب', 'error': 'لا يمكن حذف حسابك الحالي.'}
            return {'title': 'تأكيد إيقاف الحساب', 'plan': {'kind': intent, 'id': u.id},
                    'preview': f'إيقاف حساب «{u.username}» مع الاحتفاظ بسجله للتدقيق'}
        if intent == 'user_set_governorates':
            if 'مشرف محافظة' not in actual_roles(u):
                return {'title': 'محافظات المستخدم', 'error': 'تحديد المحافظات بهذا المسار متاح لحساب مشرف محافظة فقط.'}
            names = a.get('governorate_names') or ([] if not a.get('governorate_name') else [a.get('governorate_name')])
            ids = []
            for name in names:
                g, gm = _match_gov(name)
                if not g:
                    return {'title': 'تحديد المحافظات', 'choices': gm, 'error': f'لم أستطع تحديد المحافظة «{name}».' if not gm else f'يوجد أكثر من محافظة مطابقة لـ «{name}».'}
                ids.append(g.id)
            ids = sorted(set(ids))
            if not ids:
                return {'title': 'محافظات المستخدم', 'error': 'اذكر محافظة واحدة على الأقل.'}
            return {'title': 'تأكيد تعديل محافظات المستخدم', 'plan': {'kind': intent, 'id': u.id, 'governorate_ids': ids},
                    'preview': f'تعيين محافظات حساب «{u.username}»: ' + '، '.join(db.session.get(Governorate, i).name for i in ids)}
        if intent == 'user_set_branches':
            if 'المدخل الأول' not in actual_roles(u):
                return {'title': 'فروع المستخدم', 'error': 'تحديد الفروع بهذا المسار مخصص لدور المدخل الأول التنظيمي.'}
            names = a.get('branch_names') or ([] if not a.get('branch_name') else [a.get('branch_name')])
            ids=[]
            for name in names:
                b, bm = find_branch(name)
                if not b:
                    return {'title': 'تحديد الفروع', 'choices': bm, 'error': f'لم أجد الفرع «{name}».' if not bm else f'يوجد أكثر من فرع مطابق لـ «{name}».'}
                ids.append(b.id)
            ids=sorted(set(ids))
            if not ids:
                return {'title': 'فروع المستخدم', 'error': 'اذكر فرعًا واحدًا على الأقل.'}
            return {'title': 'تأكيد تعديل فروع المستخدم', 'plan': {'kind': intent, 'id': u.id, 'branch_ids': ids},
                    'preview': f'تعيين فروع حساب «{u.username}»: ' + '، '.join(db.session.get(Branch, i).name for i in ids)}
        if intent == 'user_password_reset':
            return {'title': 'تأكيد تغيير كلمة المرور', 'plan': {'kind': intent, 'id': u.id},
                    'preview': f'تغيير كلمة مرور الحساب «{u.username}» — سيُولّد النظام كلمة مرور مؤقتة ويعرضها بعد التنفيذ.'}
        updates = {k: (a.get(k) or '').strip() for k in ('full_name','email','job_title','job_code') if a.get(k)}
        if not updates:
            return {'title': 'تعديل الحساب', 'error': 'اذكر البيان الذي تريد تعديله.'}
        if 'email' in updates and updates['email'] and not valid_email(updates['email']):
            return {'title': 'تعديل الحساب', 'error': 'البريد الإلكتروني غير صحيح.'}
        if 'email' in updates and updates['email']:
            other = User.query.filter(User.email == updates['email'], User.id != u.id).first()
            if other:
                return {'title': 'تعديل الحساب', 'error': 'البريد الإلكتروني مستخدم بالفعل لحساب آخر.'}
        return {'title': 'تأكيد تعديل الحساب', 'plan': {'kind': intent, 'id': u.id, 'updates': updates},
                'preview': f'تعديل حساب «{u.username}»: ' + '، '.join(f'{k}={v}' for k,v in updates.items())}

    if intent in ('entry_assign','entry_remove','entry_replace'):
        e = db.session.get(Employee, int(a['employee_id'])) if a.get('employee_id') else None
        if not e and a.get('employee_name'):
            e, matches = find_employee(a['employee_name'])
            if not e and matches:
                return {'title': 'تحديد الموظف', 'choices': matches, 'error': 'حدد الموظف المقصود.'}
        if not e:
            return {'title': 'المدخل الأول', 'error': 'لم أجد الموظف المطلوب.'}
        active = EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first()
        if intent == 'entry_remove':
            if not active:
                return {'title': 'المدخل الأول', 'error': 'الموظف ليس مدخلًا أول حاليًا.'}
            return {'title': 'تأكيد إزالة المدخل الأول', 'plan': {'kind': intent, 'id': active.id},
                    'preview': f'إزالة الدور التنظيمي للمدخل الأول من «{e.full_name}»'}
        if intent == 'entry_assign':
            if active:
                return {'title': 'المدخل الأول', 'error': 'الموظف لديه بالفعل دور المدخل الأول.'}
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
                return {'title': 'المدخل الأول', 'error': 'كل الفروع المختارة يجب أن تكون نشطة.'}
            branches = list({b.id: b for b in branches}.values())
            sup = db.session.get(User, int(a['supervisor_id'])) if a.get('supervisor_id') else None
            if not sup and a.get('supervisor_name'):
                matches = [u for u in User.query.filter_by(is_active=True).all() if a['supervisor_name'].strip().lower() in (u.full_name or '').lower() and 'مشرف محافظة' in actual_roles(u)]
                sup = matches[0] if len(matches) == 1 else None
            if not sup:
                return {'title': 'المدخل الأول', 'error': 'اذكر المشرف المسؤول عن المدخل الأول باسمه.'}
            if 'مشرف محافظة' not in actual_roles(sup) or not sup.is_active:
                return {'title': 'المدخل الأول', 'error': 'المشرف المسؤول غير صالح.'}
            if any(b.governorate_id not in user_gov_ids(sup) for b in branches):
                return {'title': 'المدخل الأول', 'error': 'كل الفروع يجب أن تقع داخل المحافظات المسندة إلى المشرف.'}
            return {'title': 'تأكيد تعيين المدخل الأول', 'plan': {'kind': intent, 'employee_id': e.id, 'supervisor_id': sup.id, 'branch_ids': [b.id for b in branches]},
                    'preview': f'تعيين «{e.full_name}» كمدخل أول، والمشرف «{sup.full_name}»، والفروع: {"، ".join(b.name for b in branches)}'}
        old = active
        new = db.session.get(Employee, int(a['new_employee_id'])) if a.get('new_employee_id') else None
        if not new and a.get('new_employee_name'):
            new, matches = find_employee(a['new_employee_name'])
            if not new and matches:
                return {'title': 'تحديد الموظف البديل', 'choices': matches, 'error': 'وجدت أكثر من موظف مطابق.'}
        if not new:
            return {'title': 'استبدال المدخل الأول', 'error': 'اذكر الموظف البديل.'}
        if EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first():
            return {'title': 'استبدال المدخل الأول', 'error': 'الموظف البديل لديه دور مدخل أول بالفعل.'}
        return {'title': 'تأكيد استبدال المدخل الأول', 'plan': {'kind': intent, 'assignment_id': old.id, 'new_employee_id': new.id},
                'preview': f'استبدال «{e.full_name}» بالموظف «{new.full_name}» مع نقل التكليف.'}

    if intent == 'delegation_create':
        sup = db.session.get(User, int(a['supervisor_id'])) if a.get('supervisor_id') else None
        delegate = db.session.get(User, int(a['delegate_id'])) if a.get('delegate_id') else None
        gov = db.session.get(Governorate, int(a['governorate_id'])) if a.get('governorate_id') else None
        if not gov and a.get('governorate_name'):
            gov, gm = _match_gov(a['governorate_name'])
            if not gov and gm:
                return {'title': 'تحديد المحافظة', 'choices': gm, 'error': 'وجدت أكثر من محافظة مطابقة.'}
        if not sup and a.get('supervisor_name'):
            matches = [u for u in User.query.filter_by(is_active=True).all() if a['supervisor_name'].strip().lower() in u.full_name.lower() and 'مشرف محافظة' in actual_roles(u)]
            sup = matches[0] if len(matches)==1 else None
        if not delegate and a.get('delegate_name'):
            matches = [u for u in User.query.filter_by(is_active=True).all() if a['delegate_name'].strip().lower() in u.full_name.lower() and 'مشرف محافظة' in actual_roles(u)]
            delegate = matches[0] if len(matches)==1 else None
        starts, ends = parse_date(a.get('starts_at')), parse_date(a.get('ends_at'))
        if not sup or not delegate or not gov or not starts or not ends or starts > ends:
            return {'title': 'إنشاء تفويض', 'error': 'أحتاج المشرف الأصلي والمشرف البديل والمحافظة وتاريخ البداية والنهاية.'}
        if 'مشرف محافظة' not in actual_roles(sup) or 'مشرف محافظة' not in actual_roles(delegate) or sup.id == delegate.id:
            return {'title': 'إنشاء تفويض', 'error': 'التفويض يكون بين مشرفين مختلفين.'}
        if gov.id not in user_gov_ids(sup):
            return {'title': 'إنشاء تفويض', 'error': 'المشرف الأصلي يجب أن يكون مكلفًا بالمحافظة.'}
        overlap = ApprovalDelegation.query.filter(ApprovalDelegation.is_active == True, ApprovalDelegation.governorate_id == gov.id, ApprovalDelegation.starts_at <= ends, ApprovalDelegation.ends_at >= starts, db.or_(ApprovalDelegation.supervisor_id == sup.id, ApprovalDelegation.delegate_id == delegate.id)).first()
        if overlap:
            return {'title': 'إنشاء تفويض', 'error': 'يوجد تفويض متداخل في نفس الفترة.'}
        return {'title': 'تأكيد إنشاء التفويض', 'plan': {'kind': intent, 'supervisor_id': sup.id, 'delegate_id': delegate.id, 'governorate_id': gov.id, 'starts_at': starts.isoformat(), 'ends_at': ends.isoformat()},
                'preview': f'تفويض «{sup.full_name}» إلى «{delegate.full_name}» لمحافظة «{gov.name}» من {starts} إلى {ends}'}

    if intent.startswith('governorate_'):
        gov = None
        if a.get('governorate_id'):
            gov = db.session.get(Governorate, int(a['governorate_id']))
        if not gov and a.get('governorate_name'):
            gov, matches = _match_gov(a['governorate_name'])
            if not gov and matches:
                return {'title': 'تحديد المحافظة', 'choices': matches, 'error': 'وجدت أكثر من محافظة مطابقة.'}
        if intent == 'governorate_create':
            name = (a.get('governorate_name') or '').strip()
            if not name:
                return {'title': 'إضافة محافظة', 'error': 'اذكر اسم المحافظة.'}
            if Governorate.query.filter_by(name=name).first():
                return {'title': 'إضافة محافظة', 'error': 'المحافظة موجودة بالفعل.'}
            return {'title': 'تأكيد إضافة محافظة', 'plan': {'kind': intent, 'name': name},
                    'preview': f'إضافة محافظة جديدة باسم «{name}»'}
        if not gov:
            return {'title': 'تحديد المحافظة', 'error': 'لم أجد المحافظة المطلوبة.'}
        if intent == 'governorate_edit':
            new_name = (a.get('new_name') or '').strip()
            if not new_name:
                return {'title': 'تعديل المحافظة', 'error': 'اذكر الاسم الجديد.'}
            if Governorate.query.filter(Governorate.name == new_name, Governorate.id != gov.id).first():
                return {'title': 'تعديل المحافظة', 'error': 'الاسم الجديد مستخدم بالفعل.'}
            return {'title': 'تأكيد تعديل المحافظة', 'plan': {'kind': intent, 'id': gov.id, 'new_name': new_name},
                    'preview': f'تعديل «{gov.name}» إلى «{new_name}»'}
        return {'title': 'تأكيد حالة المحافظة', 'plan': {'kind': intent, 'id': gov.id, 'new_active': not gov.is_active},
                'preview': f"{'تفعيل' if not gov.is_active else 'تعطيل'} المحافظة «{gov.name}»"}

    if intent.startswith('branch_'):
        branch = db.session.get(Branch, int(a['branch_id'])) if a.get('branch_id') else None
        gov = db.session.get(Governorate, int(a['governorate_id'])) if a.get('governorate_id') else None
        if not gov and a.get('governorate_name'):
            gov, matches = _match_gov(a['governorate_name'])
            if not gov and matches:
                return {'title': 'تحديد المحافظة', 'choices': matches, 'error': 'حدد المحافظة المقصودة.'}
        if intent == 'branch_create':
            name, code = (a.get('branch_name') or '').strip(), (a.get('branch_code') or '').strip()
            if not gov:
                return {'title': 'إضافة فرع', 'error': 'اذكر المحافظة التي يتبع لها الفرع.'}
            if not name or not code:
                return {'title': 'إضافة فرع', 'error': 'اذكر اسم الفرع وكوده.'}
            if Branch.query.filter_by(governorate_id=gov.id, name=name).first():
                return {'title': 'إضافة فرع', 'error': 'الفرع موجود بالفعل في هذه المحافظة.'}
            return {'title': 'تأكيد إضافة فرع', 'plan': {'kind': intent, 'governorate_id': gov.id, 'name': name, 'code': code},
                    'preview': f'إضافة فرع «{name}» (كود {code}) إلى محافظة «{gov.name}»'}
        if not branch and a.get('branch_name'):
            branch, matches = find_branch(a['branch_name'])
            if not branch and matches:
                return {'title': 'تحديد الفرع', 'choices': matches, 'error': 'وجدت أكثر من فرع مطابق.'}
        if not branch:
            return {'title': 'تحديد الفرع', 'error': 'لم أجد الفرع المطلوب.'}
        if intent == 'branch_edit':
            name, code = (a.get('new_name') or '').strip(), (a.get('branch_code') or '').strip()
            if not name and not code:
                return {'title': 'تعديل الفرع', 'error': 'اذكر الاسم الجديد أو الكود الجديد.'}
            final_name, final_code = name or branch.name, code or branch.code
            if Branch.query.filter(Branch.governorate_id == branch.governorate_id, Branch.name == final_name, Branch.id != branch.id).first():
                return {'title': 'تعديل الفرع', 'error': 'اسم الفرع مستخدم بالفعل داخل المحافظة.'}
            if final_code and Branch.query.filter(Branch.governorate_id == branch.governorate_id, Branch.code == final_code, Branch.id != branch.id).first():
                return {'title': 'تعديل الفرع', 'error': 'كود الفرع مستخدم بالفعل داخل المحافظة.'}
            return {'title': 'تأكيد تعديل الفرع', 'plan': {'kind': intent, 'id': branch.id, 'new_name': final_name, 'code': final_code},
                    'preview': f'تعديل فرع «{branch.name}» إلى «{name or branch.name}»' + (f'، الكود {code}' if code else '')}
        return {'title': 'تأكيد حالة الفرع', 'plan': {'kind': intent, 'id': branch.id, 'new_active': not branch.is_active},
                'preview': f"{'تفعيل' if not branch.is_active else 'تعطيل'} الفرع «{branch.name}»"}

    if intent.startswith('employee_'):
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
            return {'title': 'تأكيد إخفاء الموظف', 'plan': {'kind': intent, 'id': e.id},
                    'preview': f'إخفاء الموظف «{e.full_name}» إداريًا مع الاحتفاظ بسجله وحركاته'}
        if intent == 'employee_restore':
            return {'title': 'تأكيد استعادة الموظف', 'plan': {'kind': intent, 'id': e.id},
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
        if 'email' in updates and updates['email']:
            other = Employee.query.filter(Employee.email == updates['email'], Employee.id != e.id).first()
            if other:
                return {'title': 'تعديل الموظف', 'error': 'البريد الإلكتروني مستخدم بالفعل لموظف آخر.'}
        if 'employee_code' in updates and updates['employee_code']:
            other = Employee.query.filter(Employee.employee_code == updates['employee_code'], Employee.id != e.id).first()
            if other:
                return {'title': 'تعديل الموظف', 'error': 'كود الموظف مستخدم بالفعل لموظف آخر.'}
        if 'hire_date' in updates and not parse_date(updates['hire_date']):
            return {'title': 'تعديل الموظف', 'error': 'تاريخ التعيين غير صحيح؛ استخدم YYYY-MM-DD.'}
        return {'title': 'تأكيد تعديل الموظف', 'plan': {'kind': intent, 'id': e.id, 'updates': updates},
                'preview': f'تعديل بيانات الموظف «{e.full_name}»: ' + '، '.join(f'{k}={v}' for k,v in updates.items())}

    if intent in ('movement_edit', 'movement_delete', 'movement_close', 'movement_reopen'):
        movement = db.session.get(Movement, int(a['movement_id'])) if a.get('movement_id') else None
        if not movement and a.get('employee_id'):
            q = Movement.query.filter_by(employee_id=int(a['employee_id']), is_active=True)
            if a.get('movement_type'):
                q = q.filter_by(movement_type=a.get('movement_type'))
            rows = q.order_by(Movement.created_at.desc(), Movement.id.desc()).all()
            if len(rows) == 1:
                movement = rows[0]
            elif len(rows) > 1:
                return {'title': 'تحديد الحركة', 'error': 'يوجد أكثر من حركة مطابقة. اذكر رقم الحركة.'}
        if not movement and a.get('employee_name'):
            e, matches = find_employee(a.get('employee_name'))
            if not e and matches:
                return {'title': 'تحديد الموظف', 'choices': matches, 'error': 'حدد الموظف المقصود.'}
            if e:
                q = Movement.query.filter_by(employee_id=e.id, is_active=True)
                if a.get('movement_type'):
                    q = q.filter_by(movement_type=a.get('movement_type'))
                rows = q.order_by(Movement.created_at.desc(), Movement.id.desc()).all()
                if len(rows) == 1:
                    movement = rows[0]
                elif len(rows) > 1:
                    return {'title': 'تحديد الحركة', 'error': 'يوجد أكثر من حركة مطابقة للموظف. اذكر رقم الحركة.'}
        if not movement:
            return {'title': 'إدارة الحركة', 'error': 'لم أجد الحركة المطلوبة.'}
        if intent == 'movement_delete':
            return {'title': 'تأكيد حذف الحركة', 'plan': {'kind': intent, 'id': movement.id},
                    'preview': f'إخفاء الحركة رقم {movement.id} الخاصة بالموظف «{movement.employee.full_name}» مع الاحتفاظ بسجلها.'}
        if intent == 'movement_reopen':
            if movement.movement_type != 'انتداب':
                return {'title': 'إعادة فتح الانتداب', 'error': 'الحركة المحددة ليست انتدابًا.'}
            if movement.assignment_state != 'مغلق':
                return {'title': 'إعادة فتح الانتداب', 'error': 'الانتداب مفتوح بالفعل.'}
            return {'title': 'تأكيد إعادة فتح الانتداب',
                    'plan': {'kind': intent, 'id': movement.id},
                    'preview': f'إعادة فتح الانتداب رقم {movement.id} للموظف «{movement.employee.full_name}» للسماح بالتمديد أو التعديل.'}

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
        if movement.movement_type == 'انتداب' and movement.assignment_state == 'مغلق':
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

    if intent.startswith('lookup_'):
        kind = (a.get('lookup_kind') or a.get('kind') or '').strip()
        if kind not in ('movement', 'leave') and intent != 'lookup_create':
            x = db.session.get(Lookup, int(a['lookup_id'])) if a.get('lookup_id') else None
            if not x:
                return {'title': 'إدارة القائمة', 'error': 'لم أجد عنصر القائمة المطلوب.'}
            kind = x.kind
        if intent == 'lookup_create':
            name=(a.get('lookup_name') or a.get('new_name') or '').strip()
            if kind not in ('movement','leave') or not name:
                return {'title':'إضافة عنصر قائمة','error':'اذكر نوع القائمة (حركة أو إجازة) واسم العنصر.'}
            if Lookup.query.filter_by(kind=kind,name=name).first():
                return {'title':'إضافة عنصر قائمة','error':'العنصر موجود بالفعل.'}
            return {'title':'تأكيد إضافة عنصر قائمة','plan':{'kind':intent,'lookup_kind':kind,'name':name},'preview':f'إضافة «{name}» إلى قائمة {"الحركات" if kind=="movement" else "أنواع الإجازات"}'}
        x = db.session.get(Lookup, int(a['lookup_id'])) if a.get('lookup_id') else None
        if not x and a.get('lookup_name'):
            q=(a.get('lookup_name') or '').strip(); rows=Lookup.query.filter_by(kind=kind).all(); mm=[z for z in rows if q.lower() in z.name.lower()]; x=mm[0] if len(mm)==1 else None
            if not x and mm: return {'title':'تحديد عنصر القائمة','choices':mm,'error':'وجدت أكثر من عنصر مطابق.'}
        if not x: return {'title':'إدارة القائمة','error':'لم أجد عنصر القائمة المطلوب.'}
        if intent == 'lookup_edit':
            new=(a.get('new_name') or '').strip()
            if not new: return {'title':'تعديل عنصر القائمة','error':'اذكر الاسم الجديد.'}
            if Lookup.query.filter(Lookup.kind==x.kind,Lookup.name==new,Lookup.id!=x.id).first(): return {'title':'تعديل عنصر القائمة','error':'الاسم الجديد مستخدم بالفعل.'}
            return {'title':'تأكيد تعديل عنصر القائمة','plan':{'kind':intent,'id':x.id,'new_name':new},'preview':f'تعديل «{x.name}» إلى «{new}»'}
        if intent == 'lookup_toggle':
            return {'title':'تأكيد حالة عنصر القائمة','plan':{'kind':intent,'id':x.id,'new_active':not x.is_active},'preview':f'{"تفعيل" if not x.is_active else "تعطيل"} «{x.name}»'}
        if intent == 'lookup_delete':
            used = (x.kind=='movement' and Movement.query.filter_by(movement_type=x.name).count()) or (x.kind=='leave' and Movement.query.filter_by(leave_type=x.name).count())
            if used: return {'title':'حذف عنصر القائمة','error':'العنصر مستخدم في حركات تاريخية؛ استخدم التعطيل.'}
            return {'title':'تأكيد حذف عنصر القائمة','plan':{'kind':intent,'id':x.id},'preview':f'حذف «{x.name}» نهائيًا'}

    if intent == 'delegation_revoke':
        d = db.session.get(ApprovalDelegation, int(a['delegation_id'])) if a.get('delegation_id') else None
        if not d and a.get('supervisor_name') and a.get('governorate_name'):
            gov, _ = _match_gov(a['governorate_name'])
            if gov:
                sups = [u for u in User.query.filter_by(is_active=True).all() if a['supervisor_name'].strip().lower() in (u.full_name or '').lower()]
                if len(sups) == 1:
                    d = ApprovalDelegation.query.filter_by(supervisor_id=sups[0].id, governorate_id=gov.id, is_active=True).order_by(ApprovalDelegation.id.desc()).first()
        if not d:
            return {'title': 'إلغاء التفويض', 'error': 'لم أجد التفويض المطلوب.'}
        return {'title': 'تأكيد إلغاء التفويض', 'plan': {'kind': intent, 'id': d.id, 'reason': a.get('reason') or 'إلغاء من مدير التطبيق'}, 'preview': 'إلغاء التفويض المحدد'}

    if intent in ('role_grant', 'role_revoke'):
        e = db.session.get(Employee, int(a['employee_id'])) if a.get('employee_id') else None
        if not e and a.get('employee_name'):
            e, matches = find_employee(a['employee_name'])
            if not e and matches:
                return {'title': 'تحديد الموظف', 'choices': matches, 'error': 'حدد الموظف المقصود.'}
        role = (a.get('role') or '').strip()
        allowed = {'مسؤول التطبيق','مشرف محافظة','Manager Application Support'}
        if not e or not e.user_id:
            return {'title': 'إدارة الدور', 'error': 'يجب أن يكون للموظف حساب مستخدم مرتبط أولًا لهذا النوع من الأدوار.'}
        if role not in allowed:
            return {'title': 'إدارة الدور', 'error': 'الدور المطلوب غير متاح عبر المساعد.'}
        u = db.session.get(User, e.user_id)
        exists = UserRole.query.filter_by(user_id=u.id, role=role).first()
        if intent == 'role_grant' and role == 'مشرف محافظة':
            gov_ids = []
            if a.get('governorate_ids'):
                try: gov_ids = sorted({int(x) for x in a.get('governorate_ids')})
                except (TypeError, ValueError): gov_ids = []
            elif a.get('governorate_id'):
                gov_ids = [int(a['governorate_id'])]
            elif a.get('governorate_names'):
                for gov_name in a.get('governorate_names'):
                    g, gm = _match_gov(gov_name)
                    if not g:
                        return {'title': 'تحديد المحافظات', 'choices': gm, 'error': f'لم أستطع تحديد المحافظة «{gov_name}».' if not gm else f'يوجد أكثر من محافظة مطابقة لـ «{gov_name}».'}
                    gov_ids.append(g.id)
                gov_ids = sorted(set(gov_ids))
            elif a.get('governorate_name'):
                g, gm = _match_gov(a.get('governorate_name'))
                if not g and gm:
                    return {'title': 'تحديد المحافظات', 'choices': gm, 'error': 'حدد المحافظة المقصودة.'}
                if g: gov_ids = [g.id]
            if not gov_ids:
                return {'title': 'منح دور مشرف محافظة', 'error': 'اذكر محافظة واحدة على الأقل للمشرف.'}
            active = {g.id for g in Governorate.query.filter(Governorate.id.in_(gov_ids), Governorate.is_active == True).all()}
            if set(gov_ids) != active:
                return {'title': 'منح دور مشرف محافظة', 'error': 'إحدى المحافظات المحددة غير موجودة أو غير نشطة.'}
        else:
            gov_ids = []
        if intent == 'role_grant' and exists:
            return {'title': 'إدارة الدور', 'error': 'الدور موجود بالفعل.'}
        if intent == 'role_revoke' and not exists:
            return {'title': 'إدارة الدور', 'error': 'الدور غير موجود.'}
        plan_data = {'kind': intent, 'user_id': u.id, 'role': role, 'governorate_ids': gov_ids}
        extra = f' للمحافظات: {"، ".join(str(x) for x in gov_ids)}' if gov_ids else ''
        return {'title': 'تأكيد تعديل الدور', 'plan': plan_data,
                'preview': f"{'منح' if intent == 'role_grant' else 'إزالة'} دور «{role}» من «{e.full_name}»{extra}"}
    return None


def execute(plan):
    """Execute a previously previewed plan, reloading all records and rechecking admin role."""
    if not is_app_manager():
        return False, 'لم تعد تملك صلاحية مسؤول التطبيق.'
    kind = plan.get('kind')
    if kind == 'governorate_create':
        if Governorate.query.filter_by(name=plan['name']).first(): return False, 'المحافظة موجودة بالفعل.'
        x = Governorate(name=plan['name'])
        db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Governorate',x.id,x.name)
        message = f'تمت إضافة المحافظة «{x.name}».'
    elif kind == 'governorate_edit':
        x = db.session.get(Governorate, plan['id'])
        if not x: return False, 'المحافظة غير موجودة.'
        if Governorate.query.filter(Governorate.name == plan['new_name'], Governorate.id != x.id).first(): return False, 'الاسم الجديد مستخدم بالفعل.'
        x.name = plan['new_name']; log('AI_MANAGER_EDIT','Governorate',x.id,x.name); message = 'تم تعديل المحافظة.'
    elif kind == 'governorate_toggle':
        x = db.session.get(Governorate, plan['id'])
        if not x: return False, 'المحافظة غير موجودة.'
        x.is_active = bool(plan['new_active']); log('AI_MANAGER_TOGGLE','Governorate',x.id,x.name); message = 'تم تحديث حالة المحافظة.'
    elif kind == 'branch_create':
        g = db.session.get(Governorate, plan['governorate_id'])
        if not g or not g.is_active: return False, 'المحافظة غير موجودة أو غير نشطة.'
        if Branch.query.filter_by(governorate_id=g.id, name=plan['name']).first(): return False, 'الفرع موجود بالفعل في هذه المحافظة.'
        if plan.get('code') and Branch.query.filter_by(governorate_id=g.id, code=plan['code']).first(): return False, 'كود الفرع مستخدم بالفعل في هذه المحافظة.'
        x = Branch(governorate_id=g.id,name=plan['name'],code=plan['code'])
        db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Branch',x.id,x.name); message = f'تمت إضافة الفرع «{x.name}».'
    elif kind in ('branch_edit','branch_toggle'):
        x = db.session.get(Branch, plan['id'])
        if not x: return False, 'الفرع غير موجود.'
        if kind == 'branch_edit':
            gov = db.session.get(Governorate, x.governorate_id)
            if not gov or not gov.is_active: return False, 'محافظة الفرع غير نشطة.'
            if Branch.query.filter(Branch.governorate_id == x.governorate_id, Branch.name == plan['new_name'], Branch.id != x.id).first(): return False, 'اسم الفرع مستخدم بالفعل.'
            if plan.get('code') and Branch.query.filter(Branch.governorate_id == x.governorate_id, Branch.code == plan['code'], Branch.id != x.id).first(): return False, 'كود الفرع مستخدم بالفعل.'
            x.name, x.code = plan['new_name'], plan['code']
        else: x.is_active = bool(plan['new_active'])
        log('AI_MANAGER_EDIT' if kind=='branch_edit' else 'AI_MANAGER_TOGGLE','Branch',x.id,x.name); message='تم تحديث الفرع.'
    elif kind in ('employee_delete','employee_restore','employee_edit'):
        x = db.session.get(Employee, plan['id'])
        if not x: return False, 'الموظف غير موجود.'
        if kind == 'employee_delete': x.is_active=False; x.deleted_at=datetime.utcnow(); x.deleted_by=me().id
        elif kind == 'employee_restore': x.is_active=True; x.deleted_at=None; x.deleted_by=None
        else:
            if 'branch_id' in plan['updates']:
                b=db.session.get(Branch, int(plan['updates']['branch_id']))
                if not b or not b.is_active: return False, 'فرع الموظف الجديد غير موجود أو غير نشط.'
            if 'email' in plan['updates'] and plan['updates']['email']:
                other=Employee.query.filter(Employee.email==plan['updates']['email'], Employee.id!=x.id).first()
                if other: return False, 'البريد الإلكتروني مستخدم بالفعل.'
            if 'employee_code' in plan['updates'] and plan['updates']['employee_code']:
                other=Employee.query.filter(Employee.employee_code==plan['updates']['employee_code'], Employee.id!=x.id).first()
                if other: return False, 'كود الموظف مستخدم بالفعل.'
            for k,v in plan['updates'].items(): setattr(x,k,parse_date(v) if k=='hire_date' else v)
        log('AI_MANAGER_DELETE' if kind=='employee_delete' else 'AI_MANAGER_RESTORE' if kind=='employee_restore' else 'AI_MANAGER_EDIT','Employee',x.id,x.full_name); message='تم تنفيذ العملية على الموظف.'
    elif kind == 'employee_create':
        b=db.session.get(Branch, plan['branch_id'])
        if not b or not b.is_active: return False, 'فرع الموظف غير موجود أو غير نشط.'
        if Employee.query.filter(Employee.full_name == plan['name'], Employee.is_active == True).first():
            return False, 'يوجد موظف نشط بهذا الاسم بالفعل.'
        if plan.get('email') and Employee.query.filter(Employee.email==plan['email']).first(): return False, 'البريد الإلكتروني مستخدم بالفعل.'
        if plan.get('employee_code') and Employee.query.filter(Employee.employee_code==plan['employee_code']).first(): return False, 'كود الموظف مستخدم بالفعل.'
        x = Employee(full_name=plan['name'], branch_id=plan['branch_id'], email=plan.get('email'), employee_code=plan.get('employee_code'),
                     job_title=plan.get('job_title'), job_code=plan.get('job_code'), hire_date=parse_date(plan.get('hire_date')),
                     company_phone=plan.get('company_phone'), personal_phone=plan.get('personal_phone'), is_active=True)
        db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Employee',x.id,x.full_name); message='تمت إضافة الموظف بنجاح.'
    elif kind == 'user_create':
        if User.query.filter_by(username=plan['username']).first() or User.query.filter_by(email=plan['email']).first():
            return False, 'اسم المستخدم أو البريد مستخدم بالفعل.'
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        u = User(username=plan['username'], full_name=plan['full_name'], email=plan['email'], job_title=plan['job_title'], job_code=plan['job_code'], password_hash=generate_password_hash(password), must_change_password=True)
        db.session.add(u); db.session.flush()
        for r in plan['roles']:
            db.session.add(UserRole(user_id=u.id, role=r))
            for perm in ROLE_DEFAULT_PERMISSIONS.get(r, set()):
                db.session.add(UserPermission(user_id=u.id, permission=perm))
        sync_role_accounts(u)
        for gid in plan.get('governorate_ids', []):
            g = db.session.get(Governorate, int(gid))
            if not g or not g.is_active:
                return False, 'المحافظة المحددة للمشرف غير موجودة أو غير نشطة.'
            db.session.add(UserGovernorate(user_id=u.id, governorate_id=g.id))
        log('AI_MANAGER_ADD','User',u.id,u.username); message=f'تم إنشاء الحساب «{u.username}» بنجاح. كلمة المرور المؤقتة: {password}'
    elif kind == 'user_toggle':
        u = db.session.get(User, plan['id'])
        if not u: return False, 'الحساب غير موجود.'
        if u.id == me().id and plan['new_active'] is False: return False, 'لا يمكن تعطيل حسابك الحالي.'
        u.is_active = bool(plan['new_active']); log('AI_MANAGER_TOGGLE','User',u.id,u.username); message='تم تحديث حالة الحساب.'
    elif kind == 'user_delete':
        u=db.session.get(User,plan['id'])
        if not u: return False,'الحساب غير موجود.'
        if u.id==me().id: return False,'لا يمكن إيقاف حسابك الحالي.'
        u.is_active=False; log('AI_MANAGER_DELETE','User',u.id,u.username); message='تم إيقاف الحساب مع الاحتفاظ بسجله.'
    elif kind == 'user_set_governorates':
        u=db.session.get(User,plan['id'])
        if not u or not u.is_active: return False,'الحساب غير موجود أو غير نشط.'
        if 'مشرف محافظة' not in actual_roles(u): return False,'الحساب ليس مشرف محافظة.'
        ids=[int(x) for x in plan.get('governorate_ids',[])]
        active={g.id for g in Governorate.query.filter(Governorate.id.in_(ids),Governorate.is_active==True).all()}
        if set(ids)!=active: return False,'إحدى المحافظات غير موجودة أو غير نشطة.'
        UserGovernorate.query.filter_by(user_id=u.id).delete(); db.session.flush()
        for gid in ids: db.session.add(UserGovernorate(user_id=u.id,governorate_id=gid))
        log('AI_MANAGER_SCOPE','User',u.id,'تحديث محافظات المشرف'); message='تم تحديث محافظات المشرف.'
    elif kind == 'user_set_branches':
        u=db.session.get(User,plan['id'])
        if not u or not u.is_active: return False,'الحساب غير موجود أو غير نشط.'
        if 'المدخل الأول' not in actual_roles(u): return False,'الحساب ليس مدخلًا أولًا.'
        ids=[int(x) for x in plan.get('branch_ids',[])]
        active={b.id for b in Branch.query.filter(Branch.id.in_(ids),Branch.is_active==True).all()}
        if set(ids)!=active: return False,'إحدى الفروع غير موجودة أو غير نشطة.'
        UserBranch.query.filter_by(user_id=u.id).delete(); db.session.flush()
        for bid in ids: db.session.add(UserBranch(user_id=u.id,branch_id=bid))
        log('AI_MANAGER_SCOPE','User',u.id,'تحديث فروع المدخل الأول'); message='تم تحديث فروع المدخل الأول.'
    elif kind == 'user_password_reset':
        u = db.session.get(User, plan['id'])
        if not u: return False, 'الحساب غير موجود.'
        alphabet=string.ascii_letters + string.digits
        password=''.join(secrets.choice(alphabet) for _ in range(12))
        u.password_hash = generate_password_hash(password); u.must_change_password = True; log('AI_MANAGER_PASSWORD','User',u.id,u.username); message=f'تم تغيير كلمة المرور للحساب «{u.username}». كلمة المرور المؤقتة: {password}'
    elif kind == 'user_edit':
        u = db.session.get(User, plan['id'])
        if not u: return False, 'الحساب غير موجود.'
        for k,v in plan['updates'].items(): setattr(u,k,v)
        log('AI_MANAGER_EDIT','User',u.id,u.username); message='تم تعديل بيانات الحساب.'
    elif kind == 'movement_delete':
        x = db.session.get(Movement, plan['id'])
        if not x:
            return False, 'الحركة غير موجودة.'
        if not x.is_active:
            return False, 'الحركة محذوفة بالفعل.'
        from ..models import MovementHistory
        old = x.status
        x.is_active = False
        x.deleted_by = me().id
        x.deleted_at = datetime.utcnow()
        db.session.add(MovementHistory(movement_id=x.id, from_status=old, to_status=old,
                                       action='AI_MANAGER_DELETE', reason='حذف/إخفاء الحركة من مدير التطبيق', user_id=me().id))
        log('AI_MANAGER_DELETE', 'Movement', x.id, f'حذف حركة الموظف {x.employee.full_name}')
        message = 'تم إخفاء الحركة والاحتفاظ بسجلها.'
    elif kind == 'movement_reopen':
        x = db.session.get(Movement, plan['id'])
        if not x or not x.is_active or x.movement_type != 'انتداب':
            return False, 'الانتداب غير موجود أو غير نشط.'
        if x.assignment_state != 'مغلق':
            return False, 'الانتداب مفتوح بالفعل.'
        x.assignment_state = 'ساري'
        x.closed_by = None
        x.closed_at = None
        x.closure_reason = None
        x.modified_by = me().id
        x.modified_at = datetime.utcnow()
        from ..models import MovementHistory
        db.session.add(MovementHistory(movement_id=x.id, from_status=x.status, to_status=x.status,
                                       action='AI_MANAGER_REOPEN_ASSIGNMENT', reason='إعادة فتح الانتداب للتعديل أو التمديد من المساعد', user_id=me().id))
        log('AI_MANAGER_REOPEN', 'Movement', x.id, 'إعادة فتح الانتداب للتعديل أو التمديد')
        message = 'تمت إعادة فتح الانتداب. يمكنك الآن تمديد مدته أو تعديل بياناته.'

    elif kind == 'movement_close':
        x = db.session.get(Movement, plan['id'])
        if not x or x.movement_type != 'انتداب' or not x.is_active:
            return False, 'الانتداب غير موجود أو غير نشط.'
        close_date = parse_date(plan['close_date']) or date.today()
        if x.from_date and close_date < x.from_date:
            return False, 'تاريخ الإغلاق غير صالح.'
        from ..models import MovementHistory
        x.assignment_state = 'مغلق'
        x.to_date = close_date
        x.closed_by = me().id
        x.closed_at = datetime.utcnow()
        x.closure_reason = plan.get('reason') or 'إغلاق الانتداب وعودة الموظف لفرعه الأصلي'
        x.modified_by = me().id
        x.modified_at = datetime.utcnow()
        db.session.add(MovementHistory(movement_id=x.id, from_status=x.status, to_status=x.status,
                                       action='AI_MANAGER_CLOSE_ASSIGNMENT', reason=x.closure_reason, user_id=me().id))
        log('AI_MANAGER_CLOSE', 'Movement', x.id, x.closure_reason)
        message = 'تم إنهاء الانتداب وتسجيل تاريخ الإغلاق.'
    elif kind == 'movement_edit':
        x = db.session.get(Movement, plan['id'])
        if not x or not x.is_active:
            return False, 'الحركة غير موجودة أو غير نشطة.'
        u = plan['updates']
        dest_id = u.get('destination_branch_id')
        dest = db.session.get(Branch, int(dest_id)) if dest_id else None
        if u.get('movement_type') == 'انتداب' and (not dest or not dest.is_active):
            return False, 'فرع الانتداب غير موجود أو غير نشط.'
        from ..validation import validate_movement_fields, movement_overlaps
        err = validate_movement_fields(u.get('movement_type'), u.get('leave_type'), dest_id,
                                       u.get('from_date'), u.get('to_date'), u.get('permission_date'))
        if err:
            return False, err
        overlap = movement_overlaps(x.employee_id, u.get('movement_type'), u.get('from_date'),
                                    u.get('to_date'), u.get('permission_date'), x.id)
        if overlap:
            return False, overlap
        from ..models import MovementHistory
        old = x.status
        for k, v in u.items():
            if k in ('from_date', 'to_date', 'permission_date'):
                setattr(x, k, parse_date(v) if v else None)
            else:
                setattr(x, k, v)
        x.modified_by = me().id
        x.modified_at = datetime.utcnow()
        x.status = 'مسجلة'
        db.session.add(MovementHistory(movement_id=x.id, from_status=old, to_status='مسجلة',
                                       action='AI_MANAGER_EDIT', reason='تعديل الحركة من مدير التطبيق', user_id=me().id))
        log('AI_MANAGER_EDIT', 'Movement', x.id, 'تعديل الحركة من مدير التطبيق')
        message = 'تم تعديل الحركة بنجاح.'
    elif kind == 'lookup_create':
        name=plan['name']; lk=plan['lookup_kind']
        if Lookup.query.filter_by(kind=lk,name=name).first(): return False,'العنصر موجود بالفعل.'
        x=Lookup(kind=lk,name=name,is_active=True); db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Lookup',x.id,name); message='تمت إضافة عنصر القائمة.'
    elif kind == 'lookup_edit':
        x=db.session.get(Lookup,plan['id'])
        if not x: return False,'عنصر القائمة غير موجود.'
        if Lookup.query.filter(Lookup.kind==x.kind,Lookup.name==plan['new_name'],Lookup.id!=x.id).first(): return False,'الاسم الجديد مستخدم بالفعل.'
        x.name=plan['new_name']; log('AI_MANAGER_EDIT','Lookup',x.id,x.name); message='تم تعديل عنصر القائمة.'
    elif kind == 'lookup_toggle':
        x=db.session.get(Lookup,plan['id'])
        if not x: return False,'عنصر القائمة غير موجود.'
        x.is_active=bool(plan['new_active']); log('AI_MANAGER_TOGGLE','Lookup',x.id,x.name); message='تم تحديث حالة عنصر القائمة.'
    elif kind == 'lookup_delete':
        x=db.session.get(Lookup,plan['id'])
        if not x: return False,'عنصر القائمة غير موجود.'
        used=(x.kind=='movement' and Movement.query.filter_by(movement_type=x.name).count()) or (x.kind=='leave' and Movement.query.filter_by(leave_type=x.name).count())
        if used: return False,'العنصر مستخدم في حركات تاريخية؛ استخدم التعطيل.'
        db.session.delete(x); log('AI_MANAGER_DELETE','Lookup',x.id,x.name); message='تم حذف عنصر القائمة.'
    elif kind == 'entry_assign':
        e = db.session.get(Employee, plan['employee_id']); sup = db.session.get(User, plan['supervisor_id'])
        if not e or not e.is_active or not sup or 'مشرف محافظة' not in actual_roles(sup): return False, 'بيانات التكليف غير صالحة.'
        if EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first(): return False, 'الموظف لديه مدخل أول بالفعل.'
        taken = {x.branch_id for x in EntryAssignmentBranch.query.join(EntryAssignment).filter(EntryAssignment.is_active == True).all()}
        if set(plan['branch_ids']) & taken: return False, 'أحد الفروع مسند بالفعل إلى مدخل أول آخر.'
        a = EntryAssignment(employee_id=e.id, supervisor_id=sup.id, is_active=True); db.session.add(a); db.session.flush()
        for bid in plan['branch_ids']: db.session.add(EntryAssignmentBranch(entry_assignment_id=a.id, branch_id=bid))
        log('AI_MANAGER_ROLE','Employee',e.id,'تعيين مدخل أول تنظيمي'); message='تم تعيين المدخل الأول وفروع مسؤوليته.'
    elif kind == 'entry_remove':
        a = db.session.get(EntryAssignment, plan['id'])
        if not a: return False, 'التكليف غير موجود.'
        a.is_active = False; log('AI_MANAGER_ROLE','Employee',a.employee_id,'إزالة دور المدخل الأول'); message='تمت إزالة دور المدخل الأول.'
    elif kind == 'entry_replace':
        a = db.session.get(EntryAssignment, plan['assignment_id']); new = db.session.get(Employee, plan['new_employee_id'])
        if not a or not new or not new.is_active: return False, 'بيانات الاستبدال غير صالحة.'
        if EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first(): return False, 'الموظف البديل لديه دور مدخل أول بالفعل.'
        old = a.employee_id; a.employee_id = new.id; log('AI_MANAGER_REPLACE','Employee',old,f'استبداله بالموظف {new.full_name}'); log('AI_MANAGER_REPLACE','Employee',new.id,'استلام دور المدخل الأول'); message='تم استبدال المدخل الأول ونقل التكليف.'
    elif kind == 'delegation_create':
        sup=db.session.get(User,plan['supervisor_id']); delegate=db.session.get(User,plan['delegate_id']); gov=db.session.get(Governorate,plan['governorate_id']); starts=parse_date(plan['starts_at']); ends=parse_date(plan['ends_at'])
        if not sup or not delegate or not gov or not gov.is_active or not starts or not ends or starts > ends: return False,'بيانات التفويض غير صالحة.'
        if not sup.is_active or not delegate.is_active or sup.id == delegate.id: return False,'المشرفان غير صالحين للتفويض.'
        if 'مشرف محافظة' not in actual_roles(sup) or 'مشرف محافظة' not in actual_roles(delegate): return False,'التفويض يجب أن يكون بين مشرفي محافظات.'
        if gov.id not in user_gov_ids(sup): return False,'المشرف الأصلي يجب أن يكون مكلفًا بالمحافظة.'
        overlap = ApprovalDelegation.query.filter(ApprovalDelegation.is_active == True, ApprovalDelegation.governorate_id == gov.id, ApprovalDelegation.starts_at <= ends, ApprovalDelegation.ends_at >= starts, db.or_(ApprovalDelegation.supervisor_id == sup.id, ApprovalDelegation.delegate_id == delegate.id)).first()
        if overlap: return False,'يوجد تفويض متداخل في نفس الفترة.'
        d=ApprovalDelegation(supervisor_id=sup.id,delegate_id=delegate.id,governorate_id=gov.id,starts_at=starts,ends_at=ends,created_by=me().id); db.session.add(d); db.session.flush(); log('AI_MANAGER_ADD','ApprovalDelegation',d.id,f'{sup.full_name} -> {delegate.full_name}'); message='تم إنشاء التفويض.'
    elif kind == 'delegation_revoke':
        d=db.session.get(ApprovalDelegation,plan['id'])
        if not d: return False,'التفويض غير موجود.'
        if not d.is_active: return False,'التفويض غير ساري بالفعل.'
        d.is_active=False; d.revoked_by=me().id; d.revoked_at=datetime.utcnow(); d.revoke_reason=plan.get('reason') or 'إلغاء من مدير التطبيق'; log('AI_MANAGER_REVOKE','ApprovalDelegation',d.id,d.revoke_reason); message='تم إلغاء التفويض.'
    elif kind in ('role_grant','role_revoke'):
        u = db.session.get(User, plan['user_id'])
        if not u: return False, 'حساب المستخدم غير موجود.'
        role = plan['role']
        if role not in {'مسؤول التطبيق','مشرف محافظة','Manager Application Support'}:
            return False, 'الدور غير متاح عبر هذا المسار.'
        if kind == 'role_grant':
            if UserRole.query.filter_by(user_id=u.id, role=role).first():
                return False, 'الدور موجود بالفعل.'
            db.session.add(UserRole(user_id=u.id, role=role))
            for perm in ROLE_DEFAULT_PERMISSIONS.get(role, set()):
                if not UserPermission.query.filter_by(user_id=u.id, permission=perm).first():
                    db.session.add(UserPermission(user_id=u.id, permission=perm))
            if role == 'مشرف محافظة':
                gov_ids = [int(x) for x in (plan.get('governorate_ids') or [])]
                if not gov_ids: return False, 'لا توجد محافظة مرتبطة بالدور الجديد.'
                for gid in gov_ids:
                    g = db.session.get(Governorate, gid)
                    if not g or not g.is_active: return False, 'إحدى المحافظات المرتبطة غير موجودة أو غير نشطة.'
                    if not UserGovernorate.query.filter_by(user_id=u.id, governorate_id=gid).first():
                        db.session.add(UserGovernorate(user_id=u.id, governorate_id=gid))
        else:
            r=UserRole.query.filter_by(user_id=u.id, role=role).first()
            if not r: return False, 'الدور غير موجود.'
            if u.id == me().id and role == 'مسؤول التطبيق': return False, 'لا يمكن إزالة دورك الحالي من هذا المسار.'
            db.session.delete(r)
            if role == 'مشرف محافظة':
                UserGovernorate.query.filter_by(user_id=u.id).delete()
            db.session.flush()
            remaining_roles = actual_roles(u) - {role}
            keep_perms = set()
            for rr in remaining_roles:
                keep_perms |= ROLE_DEFAULT_PERMISSIONS.get(rr, set())
            for up in UserPermission.query.filter_by(user_id=u.id).all():
                if up.permission in ROLE_DEFAULT_PERMISSIONS.get(role, set()) and up.permission not in keep_perms:
                    db.session.delete(up)
        db.session.flush()
        sync_role_accounts(u)
        log('AI_MANAGER_ROLE','User',u.id,f"{'GRANT' if kind=='role_grant' else 'REVOKE'} {role}"); message='تم تحديث الدور والصلاحيات والنطاق المرتبط به.'
    else:
        return False, 'العملية غير معروفة.'
    db.session.commit()
    return True, message
