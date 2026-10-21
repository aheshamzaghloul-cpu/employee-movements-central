"""Database mutation handlers for confirmed application-manager plans.

This module re-loads entities and re-validates sensitive relationships at execution
time. The public manager wrapper owns the commit/rollback boundary.
"""
from datetime import datetime, date
import secrets
import string

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from werkzeug.security import generate_password_hash

from ..access import CUSTOM_PERMISSION_SET_MARKER, actual_roles, log, me, movement_is_closed, user_gov_ids
from ..extensions import db
from ..models import (
    ApprovalDelegation, Branch, Employee, EntryAssignment, EntryAssignmentBranch,
    Governorate, Lookup, Movement, User, UserGovernorate, UserPermission, UserRole,
)
from ..constants import LOGIN_ROLES, ROLE_DEFAULT_PERMISSIONS
from ..validation import parse_date, valid_email
from ..assignments import sync_role_accounts
from ..services.account_security import can_remove_admin_role, invalidate_user_workflows
from ..services.identity_locks import lock_entity_identity_writes
from ..services.entity_matching import (
    alias_owner_conflict, conflicting_employee_code, employee_write_snapshot,
)
from ..services.entity_integrity import (
    branch_code_conflict,
    branch_name_conflict,
    employee_name_conflict,
    governorate_name_conflict,
    governorate_write_snapshot,
    branch_write_snapshot,
)
from .manager_access import is_app_manager


def _positive_id_list(value):
    """Return deduplicated positive integer IDs, or None for malformed input."""
    if not isinstance(value, (list, tuple)):
        return None
    result = []
    for raw in value:
        if isinstance(raw, bool):
            return None
        if isinstance(raw, int):
            item = raw
        elif isinstance(raw, str) and raw.isdigit():
            item = int(raw)
        else:
            return None
        if item <= 0:
            return None
        result.append(item)
    return list(dict.fromkeys(result))


def _strict_plan_bool(plan, key):
    """Do not coerce strings such as 'false' to True in persisted plans."""
    value = plan.get(key)
    return value if type(value) is bool else None


def execute_plan(plan):
    """Execute a previously previewed plan, reloading records and rechecking admin role."""
    if not isinstance(plan, dict):
        return False, 'خطة التنفيذ غير صالحة. أعد إعداد العملية ثم راجعها.'
    if not is_app_manager():
        return False, 'لم تعد تملك صلاحية مسؤول التطبيق.'
    kind = plan.get('kind')
    identity_mutation_kinds = {
        'employee_create', 'employee_edit', 'employee_delete', 'employee_restore', 'user_edit',
        'governorate_create', 'governorate_edit', 'governorate_toggle',
        'branch_create', 'branch_edit', 'branch_toggle',
    }
    if kind in identity_mutation_kinds:
        # Assistant plans share the same global transaction-scoped identity gate
        # as manual and Excel writes. Reload and validate only after acquiring it.
        lock_entity_identity_writes(db.session)
        if not is_app_manager():
            return False, 'لم تعد تملك صلاحية مسؤول التطبيق.'
    if kind == 'governorate_create':
        if governorate_name_conflict(plan['name']): return False, 'اسم المحافظة موجود بالفعل أو يتعارض مع اسم رسمي/بديل مؤكد.'
        x = Governorate(name=plan['name'])
        db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Governorate',x.id,x.name)
        message = f'تمت إضافة المحافظة «{x.name}».'
    elif kind == 'governorate_edit':
        x = Governorate.query.populate_existing().filter_by(id=plan['id']).with_for_update().one_or_none()
        if not x: return False, 'المحافظة غير موجودة.'
        expected_snapshot = plan.get('identity_snapshot')
        if not isinstance(expected_snapshot, dict) or expected_snapshot != governorate_write_snapshot(x):
            return False, 'تغيّرت المحافظة منذ إعداد المعاينة؛ لم يُنفّذ التعديل. أعد إعداد الخطة وراجع البيانات الحالية.'
        if governorate_name_conflict(plan['new_name'], exclude_id=x.id): return False, 'الاسم الجديد يتعارض مع اسم رسمي/بديل مؤكد لمحافظة أخرى.'
        x.name = plan['new_name']; log('AI_MANAGER_EDIT','Governorate',x.id,x.name); message = 'تم تعديل المحافظة.'
    elif kind == 'governorate_toggle':
        x = Governorate.query.populate_existing().filter_by(id=plan['id']).with_for_update().one_or_none()
        if not x: return False, 'المحافظة غير موجودة.'
        expected_snapshot = plan.get('identity_snapshot')
        if not isinstance(expected_snapshot, dict) or expected_snapshot != governorate_write_snapshot(x):
            return False, 'تغيّرت المحافظة منذ إعداد المعاينة؛ لم يتغير وضعها. أعد إعداد الخطة وراجع البيانات الحالية.'
        new_active = _strict_plan_bool(plan, 'new_active')
        if new_active is None: return False, 'حالة المحافظة المطلوبة غير صالحة؛ أعد إعداد العملية.'
        x.is_active = new_active; log('AI_MANAGER_TOGGLE','Governorate',x.id,x.name); message = 'تم تحديث حالة المحافظة.'
    elif kind == 'branch_create':
        g = db.session.get(Governorate, plan['governorate_id'])
        if not g or not g.is_active: return False, 'المحافظة غير موجودة أو غير نشطة.'
        if branch_name_conflict(plan['name'], g.id): return False, 'اسم الفرع موجود بالفعل داخل المحافظة أو يتعارض مع اسم بديل مؤكد.'
        if branch_code_conflict(plan.get('code'), g.id): return False, 'كود الفرع مستخدم بالفعل في هذه المحافظة.'
        x = Branch(governorate_id=g.id,name=plan['name'],code=plan['code'])
        db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Branch',x.id,x.name); message = f'تمت إضافة الفرع «{x.name}».'
    elif kind in ('branch_edit','branch_toggle'):
        x = Branch.query.populate_existing().filter_by(id=plan['id']).with_for_update().one_or_none()
        if not x: return False, 'الفرع غير موجود.'
        expected_snapshot = plan.get('identity_snapshot')
        if not isinstance(expected_snapshot, dict) or expected_snapshot != branch_write_snapshot(x):
            return False, 'تغيّر الفرع أو كوده أو محافظته منذ إعداد المعاينة؛ لم تُنفّذ العملية. أعد إعداد الخطة وراجع البيانات الحالية.'
        if kind == 'branch_edit':
            gov = db.session.get(Governorate, x.governorate_id)
            if not gov or not gov.is_active: return False, 'محافظة الفرع غير نشطة.'
            if branch_name_conflict(plan['new_name'], x.governorate_id, exclude_id=x.id): return False, 'اسم الفرع موجود بالفعل داخل المحافظة أو يتعارض مع اسم بديل مؤكد.'
            if branch_code_conflict(plan.get('code'), x.governorate_id, exclude_id=x.id): return False, 'كود الفرع مستخدم بالفعل.'
            x.name, x.code = plan['new_name'], plan['code']
        else:
            new_active = _strict_plan_bool(plan, 'new_active')
            if new_active is None:
                return False, 'حالة الفرع المطلوبة غير صالحة؛ أعد إعداد العملية.'
            if new_active:
                parent = db.session.get(Governorate, x.governorate_id)
                if not parent or not parent.is_active:
                    return False, 'لا يمكن تفعيل الفرع قبل تفعيل المحافظة التابعة له.'
            x.is_active = new_active
        log('AI_MANAGER_EDIT' if kind=='branch_edit' else 'AI_MANAGER_TOGGLE','Branch',x.id,x.name); message='تم تحديث الفرع.'
    elif kind in ('employee_delete','employee_restore','employee_edit'):
        x = db.session.get(Employee, plan['id'])
        if not x: return False, 'الموظف غير موجود.'
        # Delete/restore changes identity availability and must use the same
        # refresh-and-lock discipline as identity edits and Excel imports.
        db.session.refresh(x, with_for_update=True)
        expected_snapshot = plan.get('identity_snapshot')
        if not isinstance(expected_snapshot, dict) or expected_snapshot != employee_write_snapshot(x):
            return False, 'تغيّر سجل الموظف منذ إعداد المعاينة؛ لم تُنفّذ العملية. أعد إعداد الخطة وراجع البيانات الحالية.'
        if kind == 'employee_delete':
            if not x.is_active or x.deleted_at is not None:
                return False, 'الموظف غير نشط أو مخفي بالفعل؛ أعد المعاينة قبل المتابعة.'
            x.is_active=False; x.deleted_at=datetime.utcnow(); x.deleted_by=me().id
        elif kind == 'employee_restore':
            if x.is_active and x.deleted_at is None:
                return False, 'الموظف مفعّل بالفعل؛ أعد المعاينة قبل المتابعة.'
            branch = Branch.query.filter_by(id=x.branch_id).populate_existing().one_or_none()
            parent = Governorate.query.filter_by(id=branch.governorate_id).populate_existing().one_or_none() if branch else None
            if not branch or not branch.is_active or not parent or not parent.is_active:
                return False, 'لا يمكن استعادة الموظف قبل تفعيل فرعه ومحافظته.'
            if employee_name_conflict(x.full_name, x.branch_id, exclude_employee_id=x.id):
                return False, 'لا يمكن استعادة الموظف بسبب تعارض الاسم مع سجل أو صيغة بديلة.'
            for code_value in (x.employee_code, x.job_code):
                if code_value and conflicting_employee_code(code_value, exclude_employee_id=x.id):
                    return False, 'لا يمكن استعادة الموظف بسبب تعارض الكود أو إحدى صِيَغه البديلة.'
            email = (x.email or '').strip().lower()
            if email and Employee.query.filter(
                Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == email,
                Employee.id != x.id,
            ).populate_existing().first():
                return False, 'لا يمكن استعادة الموظف لأن البريد الإلكتروني مستخدم بالفعل.'
            if email and User.query.filter(
                User.email.isnot(None), func.lower(func.trim(User.email)) == email,
                User.id != (x.user_id or -1),
            ).populate_existing().first():
                return False, 'لا يمكن استعادة الموظف لأن البريد الإلكتروني مرتبط بحساب آخر.'
            x.is_active=True; x.deleted_at=None; x.deleted_by=None
        else:
            updates = plan.get('updates')
            allowed_employee_fields = {
                'full_name', 'email', 'employee_code', 'job_title', 'job_code',
                'company_phone', 'personal_phone', 'hire_date', 'branch_id',
            }
            if not isinstance(updates, dict) or not updates or not set(updates).issubset(allowed_employee_fields):
                return False, 'حقول تعديل الموظف غير صالحة. أعد إعداد الخطة ومراجعتها.'
            employee_field_limits = {
                'full_name': 250, 'email': 254, 'employee_code': 100,
                'job_title': 200, 'job_code': 100, 'company_phone': 80,
                'personal_phone': 80, 'hire_date': 10,
            }
            for field, value in updates.items():
                if field == 'branch_id':
                    if isinstance(value, bool) or not str(value).isdigit() or int(value) <= 0:
                        return False, 'فرع الموظف الجديد غير صالح.'
                elif not isinstance(value, str):
                    return False, 'تحتوي خطة تعديل الموظف على قيمة غير صالحة.'
                elif field not in employee_field_limits or len(value) > employee_field_limits[field]:
                    return False, 'إحدى قيم تعديل الموظف تتجاوز الحد المسموح.'
            if 'full_name' in updates:
                new_name = updates['full_name'].strip()
                if not new_name:
                    return False, 'اسم الموظف لا يمكن أن يكون فارغًا.'
                updates['full_name'] = new_name
            if 'branch_id' in updates:
                b=db.session.get(Branch, int(updates['branch_id']))
                parent = db.session.get(Governorate, b.governorate_id) if b else None
                if not b or not b.is_active or not parent or not parent.is_active:
                    return False, 'فرع الموظف الجديد غير موجود أو غير نشط، أو محافظته غير نشطة.'
            if 'full_name' in updates or 'branch_id' in updates:
                target_branch_id = int(updates.get('branch_id', x.branch_id))
                target_name = updates.get('full_name', x.full_name)
                if employee_name_conflict(target_name, target_branch_id, exclude_employee_id=x.id):
                    return False, 'الاسم يتعارض مع موظف آخر داخل الفرع المستهدف أو مع صيغة بديلة مؤكدة.'
            if 'email' in updates:
                new_email = updates['email'].strip().lower()
                if new_email and not valid_email(new_email):
                    return False, 'البريد الإلكتروني غير صحيح.'
                if new_email:
                    other=Employee.query.filter(
                        Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == new_email,
                        Employee.id!=x.id,
                    ).first()
                    if other: return False, 'البريد الإلكتروني مستخدم بالفعل.'
                updates['email'] = new_email or None
            for code_field in ('employee_code', 'job_code'):
                if code_field in updates and updates[code_field].strip():
                    if conflicting_employee_code(updates[code_field], exclude_employee_id=x.id):
                        return False, 'الكود الوظيفي أو أحد بدائله الرقمية مستخدم بالفعل لموظف آخر.'
                    updates[code_field] = updates[code_field].strip()
            if 'hire_date' in updates and not parse_date(updates['hire_date']):
                return False, 'تاريخ التعيين غير صحيح؛ أعد إعداد الخطة.'
            for k,v in updates.items(): setattr(x,k,int(v) if k=='branch_id' else parse_date(v) if k=='hire_date' else v)
        log('AI_MANAGER_DELETE' if kind=='employee_delete' else 'AI_MANAGER_RESTORE' if kind=='employee_restore' else 'AI_MANAGER_EDIT','Employee',x.id,x.full_name); message='تم تنفيذ العملية على الموظف.'
    elif kind == 'employee_create':
        branch_raw = plan.get('branch_id')
        if isinstance(branch_raw, bool) or not str(branch_raw).isdigit() or int(branch_raw) <= 0:
            return False, 'فرع الموظف غير صالح.'
        b=db.session.get(Branch, int(branch_raw))
        parent = db.session.get(Governorate, b.governorate_id) if b else None
        if not b or not b.is_active or not parent or not parent.is_active:
            return False, 'فرع الموظف أو محافظته غير موجودة أو غير نشطة.'
        name = plan.get('name')
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 250:
            return False, 'اسم الموظف غير صالح.'
        name = name.strip()
        if employee_name_conflict(name, b.id):
            return False, 'يوجد اسم مطابق داخل الفرع أو صيغة بديلة مؤكدة مرتبطة بموظف آخر.'
        email = str(plan.get('email') or '').strip().lower()
        if email and not valid_email(email): return False, 'البريد الإلكتروني غير صحيح.'
        if email and Employee.query.filter(
            Employee.email.isnot(None), func.lower(func.trim(Employee.email)) == email,
        ).first(): return False, 'البريد الإلكتروني مستخدم بالفعل.'
        employee_code = str(plan.get('employee_code') or '').strip() or None
        job_code = str(plan.get('job_code') or '').strip() or None
        job_title = plan.get('job_title')
        company_phone = plan.get('company_phone')
        personal_phone = plan.get('personal_phone')
        raw_hire_date = plan.get('hire_date')
        if not isinstance(job_title, str) or not job_title.strip() or len(job_title.strip()) > 200:
            return False, 'المسمى الوظيفي مطلوب ويجب ألا يتجاوز 200 حرف.'
        if not job_code or not parse_date(raw_hire_date):
            return False, 'الكود الوظيفي وتاريخ التعيين الصحيح مطلوبان لإنشاء الموظف.'
        if employee_code and len(employee_code) > 100:
            return False, 'كود الموظف أطول من الحد المسموح.'
        if job_code and len(job_code) > 100:
            return False, 'الكود الوظيفي أطول من الحد المسموح.'
        if company_phone is not None and (not isinstance(company_phone, str) or len(company_phone) > 80):
            return False, 'هاتف الشركة غير صالح.'
        if personal_phone is not None and (not isinstance(personal_phone, str) or len(personal_phone) > 80):
            return False, 'الهاتف الشخصي غير صالح.'
        if employee_code and conflicting_employee_code(employee_code):
            return False, 'كود الموظف أو أحد بدائله الرقمية مستخدم بالفعل.'
        if job_code and conflicting_employee_code(job_code):
            return False, 'الكود الوظيفي أو أحد بدائله الرقمية مستخدم بالفعل.'
        x = Employee(full_name=name, branch_id=b.id, email=email or None, employee_code=employee_code,
                     job_title=job_title.strip(), job_code=job_code, hire_date=parse_date(raw_hire_date),
                     company_phone=(company_phone or ''), personal_phone=(personal_phone or ''), is_active=True)
        db.session.add(x); db.session.flush(); log('AI_MANAGER_ADD','Employee',x.id,x.full_name); message='تمت إضافة الموظف بنجاح.'
    elif kind == 'user_create':
        # Validate the stored confirmation plan again; preview-time validation alone
        # is not sufficient for stale plans or concurrent account creation.
        username = plan.get('username')
        full_name = plan.get('full_name')
        email = plan.get('email')
        job_title = plan.get('job_title')
        job_code = plan.get('job_code')
        raw_roles = plan.get('roles')
        if not all(isinstance(value, str) for value in (username, full_name, email, job_title, job_code)):
            return False, 'بيانات الحساب غير صالحة. أعد إعداد العملية.'
        username, full_name = username.strip(), full_name.strip()
        email, job_title, job_code = email.strip().lower(), job_title.strip(), job_code.strip()
        if (
            not username or len(username) > 80 or not full_name or len(full_name) > 200
            or not email or len(email) > 254 or not valid_email(email)
            or not job_title or len(job_title) > 200 or not job_code or len(job_code) > 100
        ):
            return False, 'بيانات الحساب غير مكتملة أو تتجاوز الحدود المسموح بها.'
        if not isinstance(raw_roles, list) or not raw_roles or any(not isinstance(role, str) or role not in LOGIN_ROLES for role in raw_roles):
            return False, 'أدوار الحساب غير صالحة. أعد إعداد العملية.'
        requested_roles = list(dict.fromkeys(raw_roles))
        raw_gov_ids = plan.get('governorate_ids', [])
        governorate_ids = _positive_id_list(raw_gov_ids)
        if governorate_ids is None:
            return False, 'قائمة المحافظات المرتبطة بالحساب غير صالحة.'
        if 'مشرف محافظة' in requested_roles:
            if not governorate_ids:
                return False, 'يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.'
            active_gov_ids = {
                g.id for g in Governorate.query.filter(
                    Governorate.id.in_(governorate_ids), Governorate.is_active == True,
                ).all()
            }
            if active_gov_ids != set(governorate_ids):
                return False, 'إحدى المحافظات المحددة غير موجودة أو غير نشطة.'
        elif governorate_ids:
            return False, 'لا يجوز إسناد محافظات عبر خطة لا تتضمن دور مشرف محافظة.'
        duplicate = User.query.filter(
            (User.username == username)
            | (func.lower(func.trim(User.email)) == email)
        ).first()
        if duplicate:
            return False, 'اسم المستخدم أو البريد مستخدم بالفعل.'
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for _ in range(12))
        u = User(
            username=username, full_name=full_name, email=email, job_title=job_title,
            job_code=job_code, password_hash=generate_password_hash(password),
            must_change_password=True,
        )
        db.session.add(u)
        try:
            db.session.flush()
        except IntegrityError:
            db.session.rollback()
            return False, 'اسم المستخدم أو البريد مستخدم بالفعل؛ لم يتم إنشاء الحساب.'
        for role in requested_roles:
            db.session.add(UserRole(user_id=u.id, role=role))
            for perm in ROLE_DEFAULT_PERMISSIONS.get(role, set()):
                db.session.add(UserPermission(user_id=u.id, permission=perm))
        db.session.add(UserPermission(user_id=u.id, permission=CUSTOM_PERMISSION_SET_MARKER))
        sync_role_accounts(u)
        for gid in governorate_ids:
            db.session.add(UserGovernorate(user_id=u.id, governorate_id=gid))
        log('AI_MANAGER_ADD','User',u.id,u.username)
        message=f'تم إنشاء الحساب «{u.username}» بنجاح. كلمة المرور المؤقتة: {password}'
    elif kind == 'user_toggle':
        u = db.session.get(User, plan['id'])
        if not u: return False, 'الحساب غير موجود.'
        new_active = _strict_plan_bool(plan, 'new_active')
        if new_active is None: return False, 'حالة الحساب المطلوبة غير صالحة؛ أعد إعداد العملية.'
        if u.id == me().id and not new_active: return False, 'لا يمكن تعطيل حسابك الحالي.'
        if (u.is_active and not new_active and 'مسؤول التطبيق' in actual_roles(u)
                and not can_remove_admin_role(u.id)):
            return False, 'لا يمكن تعطيل آخر حساب مسؤول تطبيق نشط؛ يجب الإبقاء على حساب إداري نشط آخر.'
        u.is_active = new_active
        invalidate_user_workflows(u.id)
        log('AI_MANAGER_TOGGLE','User',u.id,u.username); message='تم تحديث حالة الحساب.'
    elif kind == 'user_delete':
        u=db.session.get(User,plan['id'])
        if not u: return False,'الحساب غير موجود.'
        if u.id==me().id: return False,'لا يمكن إيقاف حسابك الحالي.'
        if 'مسؤول التطبيق' in actual_roles(u) and not can_remove_admin_role(u.id):
            return False, 'لا يمكن إيقاف آخر حساب مسؤول تطبيق نشط أو قابل للاسترداد؛ يجب الإبقاء على حساب إداري آخر.'
        u.is_active=False
        invalidate_user_workflows(u.id)
        log('AI_MANAGER_DELETE','User',u.id,u.username); message='تم إيقاف الحساب مع الاحتفاظ بسجله.'
    elif kind == 'user_set_governorates':
        u=db.session.get(User,plan['id'])
        if not u or not u.is_active: return False,'الحساب غير موجود أو غير نشط.'
        if 'مشرف محافظة' not in actual_roles(u): return False,'الحساب ليس مشرف محافظة.'
        ids = _positive_id_list(plan.get('governorate_ids', []))
        if ids is None or not ids:
            return False, 'يجب إسناد محافظة واحدة على الأقل، وقائمة المحافظات يجب أن تكون صالحة.'
        active={g.id for g in Governorate.query.filter(Governorate.id.in_(ids),Governorate.is_active==True).all()}
        if set(ids)!=active: return False,'إحدى المحافظات غير موجودة أو غير نشطة.'
        UserGovernorate.query.filter_by(user_id=u.id).delete(); db.session.flush()
        for gid in ids: db.session.add(UserGovernorate(user_id=u.id,governorate_id=gid))
        invalidate_user_workflows(u.id)
        log('AI_MANAGER_SCOPE','User',u.id,'تحديث محافظات المشرف'); message='تم تحديث محافظات المشرف.'
    elif kind == 'user_set_branches':
        # This legacy path is intentionally disabled: branch assignments for the
        # first-entry role must be changed only through the Home assignment workflow.
        # Reject stale confirmation plans before any mutation is attempted.
        return False, 'مسار تعديل فروع الحساب القديم ملغى. استخدم تكليف مسؤول إدخال الفروع من الصفحة الرئيسية.'
    elif kind == 'user_password_reset':
        u = db.session.get(User, plan['id'])
        if not u: return False, 'الحساب غير موجود.'
        alphabet=string.ascii_letters + string.digits
        password=''.join(secrets.choice(alphabet) for _ in range(12))
        u.password_hash = generate_password_hash(password); u.must_change_password = True
        sync_role_accounts(u); invalidate_user_workflows(u.id)
        log('AI_MANAGER_PASSWORD','User',u.id,u.username); message=f'تم تغيير كلمة المرور للحساب «{u.username}». كلمة المرور المؤقتة: {password}'
    elif kind == 'user_edit':
        u = db.session.get(User, plan['id'])
        if not u: return False, 'الحساب غير موجود.'
        db.session.refresh(u, with_for_update=True)
        updates = plan.get('updates')
        allowed_fields = {'full_name', 'email', 'job_title', 'job_code'}
        if not isinstance(updates, dict) or not updates or not set(updates).issubset(allowed_fields):
            return False, 'حقول تعديل الحساب غير صالحة؛ أعد إعداد العملية.'
        normalized_updates = {}
        field_limits = {'full_name': 200, 'email': 254, 'job_title': 200, 'job_code': 100}
        for key, value in updates.items():
            if not isinstance(value, str):
                return False, 'إحدى بيانات الحساب غير نصية أو غير صالحة.'
            value = value.strip()
            if not value or len(value) > field_limits[key]:
                return False, 'إحدى بيانات الحساب فارغة أو تتجاوز الحد المسموح.'
            if key == 'email':
                value = value.lower()
                if not valid_email(value):
                    return False, 'البريد الإلكتروني غير صالح.'
                duplicate = User.query.filter(
                    func.lower(func.trim(User.email)) == value, User.id != u.id,
                ).first()
                if duplicate:
                    return False, 'البريد الإلكتروني مستخدم بالفعل لحساب آخر.'
            normalized_updates[key] = value

        # An account may also represent an employee record. Keep both records
        # consistent and run the same identity/code conflict checks as the UI.
        linked_employee = Employee.query.filter_by(user_id=u.id).first()
        if linked_employee:
            if 'full_name' in normalized_updates and employee_name_conflict(
                normalized_updates['full_name'], linked_employee.branch_id,
                exclude_employee_id=linked_employee.id,
            ):
                return False, 'الاسم المقترح يتعارض مع موظف آخر داخل الفرع أو مع صيغة بديلة مؤكدة.'
            if 'job_code' in normalized_updates and conflicting_employee_code(
                normalized_updates['job_code'], exclude_employee_id=linked_employee.id,
            ):
                return False, 'الكود الوظيفي المقترح مستخدم لموظف آخر أو يتعارض مع كود معروف.'
            if 'email' in normalized_updates and normalized_updates['email']:
                duplicate_employee_email = Employee.query.filter(
                    func.lower(func.trim(Employee.email)) == normalized_updates['email'],
                    Employee.id != linked_employee.id,
                ).first()
                if duplicate_employee_email:
                    return False, 'البريد الإلكتروني مستخدم بالفعل لسجل موظف آخر.'

        for key, value in normalized_updates.items():
            setattr(u, key, value)
            if linked_employee:
                setattr(linked_employee, key, value)
        sync_role_accounts(u)
        invalidate_user_workflows(u.id)
        log('AI_MANAGER_EDIT','User',u.id,u.username); message='تم تعديل بيانات الحساب.'
    elif kind == 'movement_delete':
        x = db.session.get(Movement, plan['id'])
        if not x:
            return False, 'الحركة غير موجودة.'
        # Use the common employee -> movement lock order so an assistant-admin
        # delete cannot race with a manual edit/close/delete of the same record.
        from ..validation import lock_employee_for_movement, lock_movement_for_employee
        employee = lock_employee_for_movement(x.employee_id)
        if not employee:
            return False, 'الموظف المرتبط بالحركة غير موجود.'
        x = lock_movement_for_employee(x.id, employee.id)
        if not x:
            return False, 'الحركة تغيرت أثناء التنفيذ؛ أعد معاينتها.'
        if not x.is_active:
            return False, 'الحركة محذوفة بالفعل.'
        # The assistant must obey the same closed-mission workflow as the page:
        # closed missions cannot be deleted directly, even by an admin plan.
        if x.movement_type == 'انتداب' and movement_is_closed(x):
            return False, 'لا يمكن حذف مأمورية مغلقة مباشرة. استخدم طلب تعديل المأمورية ومراجعة الـManager.'
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
        # Legacy/persisted plans must not bypass the closed-mission edit-request
        # workflow even if they were created by an older version of the assistant.
        return False, 'إعادة الفتح المباشر غير متاحة. يجب تقديم طلب تعديل واعتماده من الـManager.'

    elif kind == 'movement_close':
        x = db.session.get(Movement, plan['id'])
        if not x or x.movement_type != 'انتداب' or not x.is_active:
            return False, 'الانتداب غير موجود أو غير نشط.'
        from ..validation import lock_employee_for_movement, lock_movement_for_employee, movement_overlaps
        employee = lock_employee_for_movement(x.employee_id)
        if not employee:
            return False, 'الموظف المرتبط بالانتداب غير موجود.'
        x = lock_movement_for_employee(x.id, employee.id)
        if not x or not x.is_active or x.movement_type != 'انتداب':
            return False, 'تغيرت المأمورية أثناء التنفيذ؛ أعد معاينتها.'
        if movement_is_closed(x):
            return False, 'الانتداب مغلق بالفعل.'
        try:
            close_date = parse_date(plan.get('close_date')) if plan.get('close_date') else date.today()
        except (TypeError, ValueError):
            return False, 'تاريخ الإغلاق غير صالح.'
        if not close_date or (x.from_date and close_date < x.from_date):
            return False, 'تاريخ الإغلاق غير صالح.'
        overlap = movement_overlaps(x.employee_id, 'انتداب', x.from_date.isoformat() if x.from_date else None, close_date.isoformat(), None, x.id)
        if overlap:
            return False, overlap
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
        from ..validation import lock_employee_for_movement, lock_movement_for_employee, validate_movement_fields, movement_overlaps
        employee = lock_employee_for_movement(x.employee_id)
        if not employee:
            return False, 'الموظف المرتبط بالحركة غير موجود.'
        x = lock_movement_for_employee(x.id, employee.id)
        if not x or not x.is_active:
            return False, 'تغيرت الحركة أثناء التنفيذ؛ أعد معاينتها.'
        if x.movement_type == 'انتداب' and movement_is_closed(x):
            return False, 'المأمورية مغلقة. يجب تقديم طلب تعديل واعتماده من الـManager؛ لا يمكن تعديلها مباشرة من المساعد.'
        u = plan['updates']
        dest_id = u.get('destination_branch_id')
        dest = db.session.get(Branch, int(dest_id)) if dest_id else None
        if u.get('movement_type') == 'انتداب' and (not dest or not dest.is_active or not dest.governorate or not dest.governorate.is_active):
            return False, 'فرع الانتداب غير موجود أو غير نشط.'
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
        new_active = _strict_plan_bool(plan, 'new_active')
        if new_active is None: return False, 'حالة عنصر القائمة المطلوبة غير صالحة؛ أعد إعداد العملية.'
        x.is_active=new_active; log('AI_MANAGER_TOGGLE','Lookup',x.id,x.name); message='تم تحديث حالة عنصر القائمة.'
    elif kind == 'lookup_delete':
        x=db.session.get(Lookup,plan['id'])
        if not x: return False,'عنصر القائمة غير موجود.'
        used=(x.kind=='movement' and Movement.query.filter_by(movement_type=x.name).count()) or (x.kind=='leave' and Movement.query.filter_by(leave_type=x.name).count())
        if used: return False,'العنصر مستخدم في حركات تاريخية؛ استخدم التعطيل.'
        db.session.delete(x); log('AI_MANAGER_DELETE','Lookup',x.id,x.name); message='تم حذف عنصر القائمة.'
    elif kind == 'entry_assign':
        e = db.session.get(Employee, plan['employee_id']); sup = db.session.get(User, plan['supervisor_id'])
        if not e or not e.is_active or not sup or 'مشرف محافظة' not in actual_roles(sup): return False, 'بيانات التكليف غير صالحة.'
        if EntryAssignment.query.filter_by(employee_id=e.id, is_active=True).first(): return False, 'الموظف لديه تكليف إدخال نشط بالفعل.'
        branch_ids = [int(x) for x in plan['branch_ids']]
        taken = (EntryAssignmentBranch.query
                 .join(EntryAssignment)
                 .filter(EntryAssignment.is_active == True, EntryAssignmentBranch.branch_id.in_(branch_ids))
                 .first())
        if taken: return False, 'أحد الفروع مسند بالفعل إلى مسؤول إدخال آخر.'
        a = EntryAssignment(employee_id=e.id, supervisor_id=sup.id, is_active=True); db.session.add(a); db.session.flush()
        for bid in plan['branch_ids']: db.session.add(EntryAssignmentBranch(entry_assignment_id=a.id, branch_id=bid))
        log('AI_MANAGER_ENTRY_ASSIGNMENT','Employee',e.id,'تكليف مسؤول إدخال الفروع'); message='تم تكليف مسؤول إدخال الفروع وربط فروع مسؤوليته.'
    elif kind == 'entry_remove':
        a = db.session.get(EntryAssignment, plan['id'])
        if not a: return False, 'التكليف غير موجود.'
        a.is_active = False; log('AI_MANAGER_ENTRY_ASSIGNMENT','Employee',a.employee_id,'إزالة تكليف مسؤول إدخال الفروع'); message='تمت إزالة تكليف مسؤول إدخال الفروع.'
    elif kind == 'entry_replace':
        a = db.session.get(EntryAssignment, plan['assignment_id']); new = db.session.get(Employee, plan['new_employee_id'])
        if not a or not new or not new.is_active: return False, 'بيانات الاستبدال غير صالحة.'
        if EntryAssignment.query.filter_by(employee_id=new.id, is_active=True).first(): return False, 'الموظف البديل لديه تكليف إدخال نشط بالفعل.'
        old = a.employee_id; a.employee_id = new.id; log('AI_MANAGER_REPLACE','Employee',old,f'استبداله بالموظف {new.full_name}'); log('AI_MANAGER_ENTRY_ASSIGNMENT_REPLACE','Employee',new.id,'استلام تكليف مسؤول إدخال الفروع'); message='تم استبدال مسؤول إدخال الفروع ونقل التكليف.'
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
                gov_ids = _positive_id_list(plan.get('governorate_ids') or [])
                if gov_ids is None or not gov_ids:
                    return False, 'يجب تحديد محافظة واحدة على الأقل وبمعرّفات صحيحة للدور الجديد.'
                active_gov_ids = {
                    g.id for g in Governorate.query.filter(
                        Governorate.id.in_(gov_ids), Governorate.is_active == True,
                    ).all()
                }
                if active_gov_ids != set(gov_ids):
                    return False, 'إحدى المحافظات المرتبطة غير موجودة أو غير نشطة.'
                for gid in gov_ids:
                    if not UserGovernorate.query.filter_by(user_id=u.id, governorate_id=gid).first():
                        db.session.add(UserGovernorate(user_id=u.id, governorate_id=gid))
        else:
            r=UserRole.query.filter_by(user_id=u.id, role=role).first()
            if not r: return False, 'الدور غير موجود.'
            if u.id == me().id and role == 'مسؤول التطبيق': return False, 'لا يمكن إزالة دورك الحالي من هذا المسار.'
            if role == 'مسؤول التطبيق' and not can_remove_admin_role(u.id):
                return False, 'لا يمكن إزالة دور مسؤول التطبيق من آخر حساب إداري؛ يجب الإبقاء على حساب إداري نشط أو قابل للاسترداد.'
            db.session.delete(r)
            if role == 'مشرف محافظة':
                UserGovernorate.query.filter_by(user_id=u.id).delete()
            db.session.flush()
            remaining_roles = actual_roles(u) - {role}
            keep_perms = set()
            for rr in remaining_roles:
                keep_perms |= ROLE_DEFAULT_PERMISSIONS.get(rr, set())
            removable_perms = ROLE_DEFAULT_PERMISSIONS.get(role, set()) - keep_perms
            for up in UserPermission.query.filter(
                UserPermission.user_id == u.id,
                UserPermission.permission.in_(removable_perms),
            ).all():
                    db.session.delete(up)
        db.session.flush()
        sync_role_accounts(u)
        invalidate_user_workflows(u.id)
        log('AI_MANAGER_ROLE','User',u.id,f"{'GRANT' if kind=='role_grant' else 'REVOKE'} {role}"); message='تم تحديث الدور والصلاحيات والنطاق المرتبط به.'
    else:
        return False, 'العملية غير معروفة.'
    return True, message
