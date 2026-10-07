"""Governorates, branches and lookup lists."""

from flask import abort, Blueprint, flash, redirect, render_template, request

from ..access import actual_roles, can, gids, has_role, log, only, req, roles, user_branch_ids
from ..extensions import db
from ..models import (
    Branch,
    Employee,
    Governorate,
    Lookup,
    Movement,
    User,
    UserBranch,
    UserGovernorate,
)

bp = Blueprint('catalog', __name__)


@bp.route('/governorates', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق')
def governorates():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        if not name:
            flash('اكتب اسم المحافظة.')
        elif Governorate.query.filter_by(name=name).first():
            flash('المحافظة موجودة بالفعل.')
        else:
            x = Governorate(name=name)
            db.session.add(x)
            db.session.commit()
            log('ADD', 'Governorate', x.id, name)
            db.session.commit()
            flash('تمت الإضافة.')
    return render_template('governorates.html', rows=Governorate.query.order_by(Governorate.name))


@bp.route('/governorates/<int:i>/edit', methods=['POST'])
@req
@only('مسؤول التطبيق')
def governorate_edit(i):
    x = db.session.get(Governorate, i)
    if not x:
        abort(404)
    n = request.form.get('name', '').strip()
    dup = Governorate.query.filter(Governorate.name == n, Governorate.id != i).first()
    if not n or dup:
        flash('الاسم غير صالح أو مكرر.')
    else:
        x.name = n
        log('EDIT', 'Governorate', i, n)
        db.session.commit()
        flash('تم التعديل.')
    return redirect('/governorates')


@bp.post('/governorates/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def governorate_toggle(i):
    x = db.session.get(Governorate, i)
    if not x:
        abort(404)
    x.is_active = not x.is_active
    log('TOGGLE', 'Governorate', i)
    db.session.commit()
    return redirect('/governorates')


@bp.post('/governorates/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def governorate_delete(i):
    x = db.session.get(Governorate, i)
    if not x:
        abort(404)
    if (
        Branch.query.filter_by(governorate_id=i).count()
        or UserGovernorate.query.filter_by(governorate_id=i).count()
    ):
        flash('لا يمكن الحذف لوجود ارتباطات؛ استخدم التعطيل.')
    else:
        db.session.delete(x)
        log('DELETE', 'Governorate', i)
        db.session.commit()
        flash('تم الحذف.')
    return redirect('/governorates')


@bp.route('/branches', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق')
def branches():
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    if request.method == 'GET':
        # صفحة الفروع مستقلة لمسؤول التطبيق والمشرف، وتحتوي على نموذج إضافة الفرع.
        # مسؤول التطبيق يرى جميع المحافظات، بينما المشرف يرى محافظاته فقط.
        gs = (
            (
                Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
                .order_by(Governorate.name)
                .all()
            )
            if gids()
            else []
        )
        rows = (
            (
                Branch.query.filter(Branch.governorate_id.in_(gids()))
                .order_by(Branch.governorate_id, Branch.name)
                .all()
            )
            if gids()
            else []
        )
        return render_template(
            'branches.html',
            rows=rows,
            gs=gs,
            is_admin='مسؤول التطبيق' in roles(),
        )
    if request.method == 'POST':
        gid = request.form.get('governorate_id')
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        entry_user_id = request.form.get('entry_user_id', '').strip()
        g = db.session.get(Governorate, int(gid)) if gid and gid.isdigit() else None
        if not g or not g.is_active or (not name) or (not code):
            flash('جميع بيانات الفرع مطلوبة: المحافظة والاسم والكود.')
        elif 'مسؤول التطبيق' not in roles() and g.id not in set(gids()):
            abort(403)
        elif Branch.query.filter_by(governorate_id=g.id, name=name).first():
            flash('الفرع موجود بالفعل في هذه المحافظة.')
        else:
            x = Branch(governorate_id=g.id, name=name, code=code)
            db.session.add(x)
            db.session.flush()
            if entry_user_id.isdigit():
                eu = db.session.get(User, int(entry_user_id))
                valid_entry = bool(eu and eu.is_active and ('المدخل الأول' in actual_roles(eu)))
                if valid_entry:
                    # الربط هنا خاص بفروع المسؤولية فقط، ولا يغيّر فرع التعيين الوظيفي للمدخل.
                    if 'مسؤول التطبيق' not in roles() and (not set(gids()) & {g.id}):
                        abort(403)
                    if (
                        'مسؤول التطبيق' in roles()
                        or g.id in {b.governorate_id for b in Branch.query.filter(Branch.id.in_(user_branch_ids(eu))).all()}
                    ):
                        db.session.add(UserBranch(user_id=eu.id, branch_id=x.id))
            db.session.commit()
            log('ADD', 'Branch', x.id, name)
            db.session.commit()
            flash('تمت إضافة الفرع وربطه بالمدخل الأول تلقائيًا.')
    gs = (
        Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active == True)
        .order_by(Governorate.name)
        .all()
    )
    rows = (
        Branch.query.filter(Branch.governorate_id.in_(gids())).order_by(Branch.name).all()
        if gids()
        else []
    )
    return render_template('branches.html', rows=rows, gs=gs)


@bp.post('/branches/<int:i>/edit')
@req
@only('مسؤول التطبيق')
def branch_edit(i):
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    x = db.session.get(Branch, i)
    g = db.session.get(Governorate, int(request.form.get('governorate_id', '0')))
    n = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip()
    if not x or not g or (not g.is_active) or (not n) or (not code):
        flash('جميع بيانات الفرع مطلوبة.')
        return redirect('/branches')
    if (
        'مسؤول التطبيق' not in roles()
        and (x.governorate_id not in set(gids()) or g.id not in set(gids()))
    ):
        abort(403)
    dup = (
        Branch.query.filter(Branch.governorate_id == g.id, Branch.name == n, Branch.id != i)
        .first()
    )
    if dup:
        flash('الفرع موجود بالفعل في هذه المحافظة.')
    else:
        x.governorate_id = g.id
        x.name = n
        x.code = code
        log('EDIT', 'Branch', i, n)
        db.session.commit()
        flash('تم التعديل.')
    return redirect('/branches')


@bp.post('/branches/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def branch_toggle(i):
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    x = db.session.get(Branch, i)
    if not x:
        abort(404)
    if 'مسؤول التطبيق' not in roles() and x.governorate_id not in set(gids()):
        abort(403)
    x.is_active = not x.is_active
    log('TOGGLE', 'Branch', i)
    db.session.commit()
    return redirect('/branches')


@bp.post('/branches/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def branch_delete(i):
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    x = db.session.get(Branch, i)
    if not x:
        abort(404)
    if 'مسؤول التطبيق' not in roles() and x.governorate_id not in set(gids()):
        abort(403)
    if (
        Employee.query.filter_by(branch_id=i).count()
        or UserBranch.query.filter_by(branch_id=i).count()
        or Movement.query.filter_by(destination_branch_id=i).count()
    ):
        flash('لا يمكن حذف الفرع لوجود موظفين أو مستخدمين أو حركات مرتبطة به؛ استخدم التعطيل.')
    else:
        db.session.delete(x)
        log('DELETE', 'Branch', i)
        db.session.commit()
        flash('تم حذف الفرع نهائيًا.')
    return redirect('/branches')


@bp.route('/lookups', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق')
def lookups():
    if request.method == 'POST':
        kind = request.form.get('kind')
        name = request.form.get('name', '').strip()
        if kind not in ('movement', 'leave') or not name:
            flash('بيانات القائمة غير صحيحة.')
        elif Lookup.query.filter_by(kind=kind, name=name).first():
            flash('العنصر موجود بالفعل.')
        else:
            x = Lookup(kind=kind, name=name)
            db.session.add(x)
            db.session.commit()
            log('ADD', 'Lookup', x.id, name)
            db.session.commit()
            flash('تمت الإضافة.')
    rows = Lookup.query.order_by(Lookup.kind, Lookup.name).all()
    return render_template('lookups.html', rows=rows)


@bp.post('/lookups/<int:i>/edit')
@req
@only('مسؤول التطبيق')
def lookup_edit(i):
    x = db.session.get(Lookup, i)
    if not x:
        abort(404)
    n = request.form.get('name', '').strip()
    dup = Lookup.query.filter(Lookup.kind == x.kind, Lookup.name == n, Lookup.id != i).first()
    if not n or dup:
        flash('الاسم غير صالح أو مكرر.')
    else:
        x.name = n
        log('EDIT', 'Lookup', i, n)
        db.session.commit()
        flash('تم التعديل.')
    return redirect('/lookups')


@bp.post('/lookups/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def lookup_toggle(i):
    x = db.session.get(Lookup, i)
    if not x:
        abort(404)
    x.is_active = not x.is_active
    log('TOGGLE', 'Lookup', i)
    db.session.commit()
    return redirect('/lookups')


@bp.post('/lookups/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def lookup_delete(i):
    x = db.session.get(Lookup, i)
    if x:
        used = (
            x.kind == 'movement' and Movement.query.filter_by(movement_type=x.name).count()
            or x.kind == 'leave' and Movement.query.filter_by(leave_type=x.name).count()
        )
        if used:
            flash('لا يمكن حذف عنصر مستخدم في حركات تاريخية؛ استخدم التعطيل.')
        else:
            db.session.delete(x)
            log('DELETE', 'Lookup', i)
            db.session.commit()
            flash('تم الحذف.')
    return redirect('/lookups')
