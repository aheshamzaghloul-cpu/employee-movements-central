"""Supervisor coverage delegations, scoped to the selected work governorate."""

from datetime import date, datetime

from flask import abort, Blueprint, flash, g, redirect, render_template, request

from ..access import (
    actual_roles,
    delegation_allowed_for_user,
    log,
    me,
    req,
    roles,
    scope_governorate_id,
    user_gov_ids,
)
from ..extensions import db
from ..form_state import form_values_from_request
from ..models import ApprovalDelegation, Governorate, User
from ..services.account_security import invalidate_user_workflows

bp = Blueprint('delegations', __name__)


def _active_supervisors_for_governorate(governorate_id):
    if not governorate_id:
        return []
    return [
        user
        for user in User.query.filter_by(is_active=True).order_by(User.full_name).all()
        if 'مشرف محافظة' in actual_roles(user)
        and governorate_id in user_gov_ids(user)
    ]


def _delegation_return(form_key=None):
    if form_key:
        g._delegation_form_values = form_values_from_request(request.form)
        return delegations()
    return redirect('/delegations')


@bp.get('/delegations')
@req
def delegations():
    u = me()
    rs = roles(u)
    if not ({'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'} & rs):
        abort(403)

    central_operator = bool({'مسؤول التطبيق', 'Manager Application Support'} & rs)
    selected_gid = scope_governorate_id()
    if not selected_gid:
        # The top-level shell selector remains visible and must be used before
        # changing coverage; do not guess a governorate for a central operator.
        rows = []
        supervisors = []
        delegates = []
        govs = []
    else:
        q = ApprovalDelegation.query.filter_by(governorate_id=selected_gid)
        if not central_operator:
            q = q.filter(
                db.or_(
                    ApprovalDelegation.supervisor_id == u.id,
                    ApprovalDelegation.delegate_id == u.id,
                )
            )
        rows = q.order_by(
            ApprovalDelegation.is_active.desc(),
            ApprovalDelegation.starts_at.desc(),
            ApprovalDelegation.id.desc(),
        ).all()
        supervisors = _active_supervisors_for_governorate(selected_gid) if central_operator else [u]
        delegates = [x for x in _active_supervisors_for_governorate(selected_gid) if not (not central_operator and x.id == u.id)]
        govs = Governorate.query.filter_by(id=selected_gid, is_active=True).all()

    return render_template(
        'delegations.html',
        rows=rows,
        supervisors=supervisors,
        govs=govs,
        delegates=delegates,
        today=date.today(),
        selected_work_governorate_id=selected_gid,
        delegation_central_operator=central_operator,
        form_values=getattr(g, '_delegation_form_values', {}),
    )


@bp.post('/delegations/add')
@req
def delegation_add():
    u = me()
    rs = roles(u)
    if not ({'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'} & rs):
        abort(403)
    selected_gid = scope_governorate_id()
    raw_gid = (request.form.get('governorate_id') or '').strip()
    if not selected_gid or not raw_gid.isdigit() or int(raw_gid) != int(selected_gid):
        flash('اختر محافظة العمل أولًا، ويجب أن يطابق التفويض المحافظة المختارة.')
        return _delegation_return('delegation_create')
    gid = int(raw_gid)
    central_operator = bool({'مسؤول التطبيق', 'Manager Application Support'} & rs)

    sup = None
    if central_operator:
        raw_sup = (request.form.get('supervisor_id') or '').strip()
        sup = db.session.get(User, int(raw_sup)) if raw_sup.isdigit() else None
    else:
        sup = u

    raw_delegate = (request.form.get('delegate_id') or '').strip()
    delegate = db.session.get(User, int(raw_delegate)) if raw_delegate.isdigit() else None
    gov = db.session.get(Governorate, gid)
    try:
        starts = date.fromisoformat(request.form.get('starts_at', ''))
        ends = date.fromisoformat(request.form.get('ends_at', ''))
    except (TypeError, ValueError):
        starts = ends = None

    if not sup or not sup.is_active or not delegate or not delegate.is_active or not gov or not gov.is_active or not starts or not ends or starts > ends:
        flash('أكمل المشرف الأصلي والبديل والفترة بتاريخين صحيحين.')
        return _delegation_return('delegation_create')
    if 'مشرف محافظة' not in actual_roles(sup) or 'مشرف محافظة' not in actual_roles(delegate):
        flash('التفويض يكون بين حسابين رسميين لمشرفي المحافظات.')
        return _delegation_return('delegation_create')
    # All parts of a delegation must belong to the selected work governorate.
    if gid not in user_gov_ids(sup) or gid not in user_gov_ids(delegate):
        flash('يجب أن يكون المشرف الأصلي والبديل مسؤولين عن محافظة العمل المختارة.')
        return _delegation_return('delegation_create')
    if not delegation_allowed_for_user(sup, gid):
        flash('المشرف الأصلي أو المحافظة لا يتطابقان مع التبعية النشطة.')
        return _delegation_return('delegation_create')
    if sup.id == delegate.id:
        flash('لا يمكن اختيار المشرف نفسه كبديل.')
        return _delegation_return('delegation_create')

    overlap = ApprovalDelegation.query.filter(
        ApprovalDelegation.is_active == True,
        ApprovalDelegation.governorate_id == gid,
        ApprovalDelegation.starts_at <= ends,
        ApprovalDelegation.ends_at >= starts,
        db.or_(ApprovalDelegation.supervisor_id == sup.id, ApprovalDelegation.delegate_id == delegate.id),
    ).first()
    if overlap:
        flash('يوجد تفويض نشط يتداخل مع الفترة المحددة لأحد طرفي التفويض.')
        return _delegation_return('delegation_create')

    d = ApprovalDelegation(
        supervisor_id=sup.id,
        delegate_id=delegate.id,
        governorate_id=gid,
        starts_at=starts,
        ends_at=ends,
        created_by=u.id,
    )
    db.session.add(d)
    db.session.flush()
    log(
        'ADD',
        'ApprovalDelegation',
        d.id,
        f'تفويض {sup.full_name} إلى {delegate.full_name} للمحافظة {gov.name} من {starts} إلى {ends}',
    )
    invalidate_user_workflows(sup.id)
    invalidate_user_workflows(delegate.id)
    db.session.commit()
    flash('تم إنشاء التفويض داخل محافظة العمل المختارة.')
    return _delegation_return()


@bp.post('/delegations/<int:i>/revoke')
@req
def delegation_revoke(i):
    u = me()
    rs = roles(u)
    d = db.session.get(ApprovalDelegation, i)
    if not d:
        abort(404)
    central_operator = bool({'مسؤول التطبيق', 'Manager Application Support'} & rs)
    selected_gid = scope_governorate_id()
    if central_operator:
        authorized = bool(selected_gid and int(selected_gid) == d.governorate_id)
    else:
        authorized = bool(
            'مشرف محافظة' in rs
            and d.supervisor_id == u.id
            and delegation_allowed_for_user(u, d.governorate_id)
            and selected_gid
            and int(selected_gid) == d.governorate_id
        )
    if not authorized:
        abort(403)
    if not d.is_active:
        flash('التفويض غير ساري بالفعل.')
        return _delegation_return()
    reason = (request.form.get('reason') or '').strip()
    if len(reason) < 3:
        flash('سبب إلغاء التفويض إجباري.')
        return _delegation_return()
    d.is_active = False
    d.revoked_by = u.id
    d.revoked_at = datetime.utcnow()
    d.revoke_reason = reason
    log('REVOKE', 'ApprovalDelegation', d.id, reason)
    invalidate_user_workflows(d.supervisor_id)
    invalidate_user_workflows(d.delegate_id)
    db.session.commit()
    flash('تم إلغاء التفويض فورًا داخل محافظة العمل المختارة.')
    return _delegation_return()
