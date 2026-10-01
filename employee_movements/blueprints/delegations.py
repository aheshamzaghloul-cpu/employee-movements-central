"""Supervisor approval delegations."""

from datetime import date, datetime

from flask import abort, Blueprint, flash, redirect, render_template, request

from ..access import actual_roles, delegation_allowed_for_user, log, me, req, roles, user_gov_ids
from ..extensions import db
from ..models import ApprovalDelegation, Governorate, User

bp = Blueprint('delegations', __name__)


@bp.get('/delegations')
@req
def delegations():
    u = me()
    if 'مسؤول التطبيق' not in roles(u) and 'مشرف محافظة' not in roles(u):
        abort(403)
    q = ApprovalDelegation.query
    if 'مسؤول التطبيق' not in roles(u):
        gids = user_gov_ids(u)
        q = (
            q.filter(
                ApprovalDelegation.supervisor_id == u.id,
                ApprovalDelegation.governorate_id.in_(gids),
            )
            if gids
            else q.filter(False)
        )
    rows = (
        q.order_by(
            ApprovalDelegation.is_active.desc(),
            ApprovalDelegation.starts_at.desc(),
            ApprovalDelegation.id.desc(),
        )
        .all()
    )
    if 'مسؤول التطبيق' in roles(u):
        supervisors = [
            x
            for x in User.query.filter(User.is_active == True).order_by(User.full_name).all()
            if 'مشرف محافظة' in roles(x)
        ]
        govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
    else:
        supervisors = [u]
        govs = (
            Governorate.query.filter(Governorate.id.in_(user_gov_ids(u)))
            .filter_by(is_active=True)
            .order_by(Governorate.name)
            .all()
        )
    delegates = [
        x
        for x in User.query.filter(User.is_active == True).order_by(User.full_name).all()
        if 'مشرف محافظة' in actual_roles(x)
    ]
    return render_template(
        'delegations.html',
        rows=rows,
        supervisors=supervisors,
        govs=govs,
        delegates=delegates,
    )


@bp.post('/delegations/add')
@req
def delegation_add():
    u = me()
    if 'مسؤول التطبيق' not in roles(u) and 'مشرف محافظة' not in roles(u):
        abort(403)
    sup_id = int(request.form.get('supervisor_id') or 0)
    delegate_id = int(request.form.get('delegate_id') or 0)
    gid = int(request.form.get('governorate_id') or 0)
    try:
        starts = date.fromisoformat(request.form.get('starts_at', ''))
        ends = date.fromisoformat(request.form.get('ends_at', ''))
    except ValueError:
        starts = ends = None
    sup = db.session.get(User, sup_id)
    delegate = db.session.get(User, delegate_id)
    gov = db.session.get(Governorate, gid)
    if 'مسؤول التطبيق' not in roles(u):
        sup = u
    if not sup or not delegate or (not gov) or (not starts) or (not ends) or (starts > ends):
        flash('جميع بيانات التفويض مطلوبة، ويجب أن تكون بداية التفويض قبل أو مساوية لنهايته.')
        return redirect('/delegations')
    # التفويض الإداري يتم حصراً بين مشرفي المحافظات: مشرف أصلي ← مشرف بديل.
    # مسؤول التطبيق يدير العملية تقنياً فقط ولا يكون طرفاً في التفويض.
    if 'مشرف محافظة' not in roles(sup) or 'مشرف محافظة' not in roles(delegate):
        flash('التفويض يكون بين مشرف محافظة ومشرف محافظة فقط.')
        return redirect('/delegations')
    if not delegation_allowed_for_user(sup, gid):
        flash('المشرف أو المحافظة لا يتطابقان مع التبعية.')
        return redirect('/delegations')
    if delegate.id == sup.id:
        flash('لا يمكن اختيار المشرف نفسه كبديل.')
        return redirect('/delegations')
    if 'مشرف محافظة' not in actual_roles(delegate) or gid not in user_gov_ids(delegate):
        flash('البديل يجب أن يكون مشرف محافظة مؤهلًا ومكلفًا بالمحافظة نفسها.')
        return redirect('/delegations')
    overlap = (
        ApprovalDelegation.query.filter_by(supervisor_id=sup.id, governorate_id=gid, is_active=True)
        .filter(ApprovalDelegation.starts_at <= ends, ApprovalDelegation.ends_at >= starts)
        .first()
    )
    if overlap:
        flash('يوجد تفويض ساري متداخل مع الفترة المحددة.')
        return redirect('/delegations')
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
    db.session.commit()
    flash('تم إنشاء التفويض.')
    return redirect('/delegations')


@bp.post('/delegations/<int:i>/revoke')
@req
def delegation_revoke(i):
    u = me()
    d = db.session.get(ApprovalDelegation, i)
    if not d:
        abort(404)
    if (
        'مسؤول التطبيق' not in roles(u)
        and not (d.supervisor_id == u.id and delegation_allowed_for_user(u, d.governorate_id))
    ):
        abort(403)
    if not d.is_active:
        flash('التفويض غير ساري بالفعل.')
        return redirect('/delegations')
    reason = request.form.get('reason', '').strip()
    if len(reason) < 3:
        flash('سبب إلغاء التفويض إجباري.')
        return redirect('/delegations')
    d.is_active = False
    d.revoked_by = u.id
    d.revoked_at = datetime.utcnow()
    d.revoke_reason = reason
    log('REVOKE', 'ApprovalDelegation', d.id, reason)
    db.session.commit()
    flash('تم إلغاء التفويض فورًا.')
    return redirect('/delegations')
