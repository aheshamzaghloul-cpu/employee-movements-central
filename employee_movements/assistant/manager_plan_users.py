"""User-account and role confirmation-plan handlers for the assistant manager."""

from ..access import actual_roles, me
from sqlalchemy import func
from ..extensions import db
from ..models import Branch, Employee, Governorate, User, UserRole
from ..constants import LOGIN_ROLES
from ..validation import valid_email
from .directory import find_branch, find_employee
from .manager_resolvers import resolve_governorate as _match_gov


def plan_user_action(a, intent):
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
    if intent == 'user_set_branches':
        # This legacy role-scoped endpoint is not allowed to change branch
        # assignments; the canonical workflow is the Home entry-assignment tool.
        return {'title': 'فروع المستخدم', 'error': 'تعديل فروع مسؤول الإدخال يتم من الصفحة الرئيسية، ولا يمكن استخدام المسار القديم.'}
    if intent == 'user_create':
        username = (a.get('username') or '').strip()
        full = (a.get('full_name') or a.get('employee_name') or '').strip()
        email = (a.get('email') or '').strip().lower()
        job_title = (a.get('job_title') or '').strip()
        job_code = (a.get('job_code') or '').strip()
        # Temporary credentials are always generated locally after confirmation;
        # never validate or retain a password supplied in a chat/model payload.
        role = (a.get('role') or '').strip()
        requested_roles = [r for r in (a.get('roles') or []) if r in LOGIN_ROLES]
        if role in LOGIN_ROLES and role not in requested_roles:
            requested_roles.append(role)
        if not requested_roles or not username or not full or not email or not job_title or not job_code:
            return {'title': 'إنشاء حساب', 'error': 'أحتاج اسم المستخدم والاسم والبريد والوظيفة والكود الوظيفي ودورًا واحدًا على الأقل.'}
        if User.query.filter(
            (User.username == username)
            | (func.lower(func.trim(User.email)) == email)
        ).first():
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
        return {'title': 'فروع المستخدم', 'error': 'تعديل فروع مسؤول الإدخال يتم من الصفحة الرئيسية، ولا يمكن استخدام المسار القديم.'}
    if intent == 'user_password_reset':
        return {'title': 'تأكيد تغيير كلمة المرور', 'plan': {'kind': intent, 'id': u.id},
                'preview': f'تغيير كلمة مرور الحساب «{u.username}» — سيُولّد النظام كلمة مرور مؤقتة ويعرضها بعد التنفيذ.'}
    updates = {k: (a.get(k) or '').strip() for k in ('full_name','email','job_title','job_code') if a.get(k)}
    if not updates:
        return {'title': 'تعديل الحساب', 'error': 'اذكر البيان الذي تريد تعديله.'}
    if 'email' in updates and updates['email'] and not valid_email(updates['email']):
        return {'title': 'تعديل الحساب', 'error': 'البريد الإلكتروني غير صحيح.'}
    if 'email' in updates and updates['email']:
        updates['email'] = updates['email'].lower()
        other = User.query.filter(func.lower(func.trim(User.email)) == updates['email'], User.id != u.id).first()
        if other:
            return {'title': 'تعديل الحساب', 'error': 'البريد الإلكتروني مستخدم بالفعل لحساب آخر.'}
    return {'title': 'تأكيد تعديل الحساب', 'plan': {'kind': intent, 'id': u.id, 'updates': updates},
            'preview': f'تعديل حساب «{u.username}»: ' + '، '.join(f'{k}={v}' for k,v in updates.items())}


def plan_role_action(a, intent):
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
