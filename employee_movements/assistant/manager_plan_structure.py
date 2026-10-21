"""Governorate, branch, lookup and delegation plan handlers."""

from ..access import actual_roles, user_gov_ids
from ..extensions import db
from ..models import ApprovalDelegation, Branch, Governorate, Lookup, Movement, User
from ..validation import parse_date
from ..services.entity_integrity import governorate_write_snapshot, branch_write_snapshot
from ..services.entity_integrity import (
    branch_code_conflict,
    branch_name_conflict,
    governorate_name_conflict,
)
from .directory import find_branch
from .manager_resolvers import (
    resolve_active_supervisor_by_name,
    resolve_governorate as _match_gov,
)


def plan_delegation_create(a, intent):
    sup = db.session.get(User, int(a['supervisor_id'])) if a.get('supervisor_id') else None
    delegate = db.session.get(User, int(a['delegate_id'])) if a.get('delegate_id') else None
    gov = db.session.get(Governorate, int(a['governorate_id'])) if a.get('governorate_id') else None
    if not gov and a.get('governorate_name'):
        gov, gm = _match_gov(a['governorate_name'])
        if not gov and gm:
            return {'title': 'تحديد المحافظة', 'choices': gm, 'error': 'وجدت أكثر من محافظة مطابقة.'}
    if not sup and a.get('supervisor_name'):
        sup = resolve_active_supervisor_by_name(a['supervisor_name'])
    if not delegate and a.get('delegate_name'):
        delegate = resolve_active_supervisor_by_name(a['delegate_name'])
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


def plan_governorate_action(a, intent):
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
        if governorate_name_conflict(name):
            return {'title': 'إضافة محافظة', 'error': 'اسم المحافظة موجود بالفعل أو يتعارض مع اسم رسمي/بديل مؤكد.'}
        return {'title': 'تأكيد إضافة محافظة', 'plan': {'kind': intent, 'name': name},
                'preview': f'إضافة محافظة جديدة باسم «{name}»'}
    if not gov:
        return {'title': 'تحديد المحافظة', 'error': 'لم أجد المحافظة المطلوبة.'}
    if intent == 'governorate_edit':
        new_name = (a.get('new_name') or '').strip()
        if not new_name:
            return {'title': 'تعديل المحافظة', 'error': 'اذكر الاسم الجديد.'}
        if governorate_name_conflict(new_name, exclude_id=gov.id):
            return {'title': 'تعديل المحافظة', 'error': 'الاسم الجديد يتعارض مع اسم رسمي/بديل مؤكد لمحافظة أخرى.'}
        return {'title': 'تأكيد تعديل المحافظة', 'plan': {'kind': intent, 'id': gov.id, 'new_name': new_name, 'identity_snapshot': governorate_write_snapshot(gov)},
                'preview': f'تعديل «{gov.name}» إلى «{new_name}»'}
    return {'title': 'تأكيد حالة المحافظة', 'plan': {'kind': intent, 'id': gov.id, 'new_active': not gov.is_active, 'identity_snapshot': governorate_write_snapshot(gov)},
            'preview': f"{'تفعيل' if not gov.is_active else 'تعطيل'} المحافظة «{gov.name}»"}


def plan_branch_action(a, intent):
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
        if branch_name_conflict(name, gov.id):
            return {'title': 'إضافة فرع', 'error': 'اسم الفرع موجود بالفعل داخل المحافظة أو يتعارض مع اسم بديل مؤكد.'}
        if branch_code_conflict(code, gov.id):
            return {'title': 'إضافة فرع', 'error': 'كود الفرع مستخدم بالفعل داخل المحافظة.'}
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
        if branch_name_conflict(final_name, branch.governorate_id, exclude_id=branch.id):
            return {'title': 'تعديل الفرع', 'error': 'اسم الفرع موجود بالفعل داخل المحافظة أو يتعارض مع اسم بديل مؤكد.'}
        if branch_code_conflict(final_code, branch.governorate_id, exclude_id=branch.id):
            return {'title': 'تعديل الفرع', 'error': 'كود الفرع مستخدم بالفعل داخل المحافظة.'}
        return {'title': 'تأكيد تعديل الفرع', 'plan': {'kind': intent, 'id': branch.id, 'new_name': final_name, 'code': final_code, 'identity_snapshot': branch_write_snapshot(branch)},
                'preview': f'تعديل فرع «{branch.name}» إلى «{name or branch.name}»' + (f'، الكود {code}' if code else '')}
    return {'title': 'تأكيد حالة الفرع', 'plan': {'kind': intent, 'id': branch.id, 'new_active': not branch.is_active, 'identity_snapshot': branch_write_snapshot(branch)},
            'preview': f"{'تفعيل' if not branch.is_active else 'تعطيل'} الفرع «{branch.name}»"}


def plan_lookup_action(a, intent):
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
        q=(a.get('lookup_name') or '').strip(); rows=Lookup.query.filter(Lookup.kind == kind, Lookup.name.ilike(f'%{q}%')).limit(20).all(); x=rows[0] if len(rows)==1 else None
        if not x and len(rows) > 1: return {'title':'تحديد عنصر القائمة','choices':rows,'error':'وجدت أكثر من عنصر مطابق.'}
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


def plan_delegation_revoke(a, intent):
    d = db.session.get(ApprovalDelegation, int(a['delegation_id'])) if a.get('delegation_id') else None
    if not d and a.get('supervisor_name') and a.get('governorate_name'):
        gov, _ = _match_gov(a['governorate_name'])
        if gov:
            sup = resolve_active_supervisor_by_name(a['supervisor_name'])
            if sup:
                d = ApprovalDelegation.query.filter_by(supervisor_id=sup.id, governorate_id=gov.id, is_active=True).order_by(ApprovalDelegation.id.desc()).first()
    if not d:
        return {'title': 'إلغاء التفويض', 'error': 'لم أجد التفويض المطلوب.'}
    return {'title': 'تأكيد إلغاء التفويض', 'plan': {'kind': intent, 'id': d.id, 'reason': a.get('reason') or 'إلغاء من مدير التطبيق'}, 'preview': 'إلغاء التفويض المحدد'}
