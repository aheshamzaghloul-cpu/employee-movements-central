"""Governorates, branches and lookup lists."""

from flask import abort, Blueprint, flash, redirect, render_template, request
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from ..access import can, gids, governorate_ok, has_role, log, me, only, req, roles
from ..extensions import db
from ..services.entity_matching import normalize_alias_key
from ..services.entity_integrity import (
    branch_code_conflict,
    branch_name_conflict,
    confirmed_alias_conflict,
    governorate_name_conflict,
)
from ..services.identity_locks import lock_entity_identity_writes
from ..models import (
    ApprovalDelegation,
    Branch,
    BranchNameAlias,
    Employee,
    EntryAssignmentBranch,
    Governorate,
    GovernorateNameAlias,
    Lookup,
    Movement,
    UserBranch,
    UserGovernorate,
)

bp = Blueprint('catalog', __name__)


@bp.route('/governorates', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق')
def governorates():
    if request.method == 'POST':
        lock_entity_identity_writes(db.session)
        name = request.form.get('name', '').strip()
        if not name:
            flash('اكتب اسم المحافظة.')
        elif governorate_name_conflict(name):
            flash('اسم المحافظة موجود بالفعل أو يتعارض مع اسم رسمي/بديل مؤكد؛ راجع سجل المحافظات.')
        else:
            x = Governorate(name=name)
            db.session.add(x)
            db.session.flush()
            log('ADD', 'Governorate', x.id, name)
            db.session.commit()
            flash('تمت الإضافة.')
    rows = Governorate.query.order_by(Governorate.name).all()
    governorate_aliases = {}
    for alias in GovernorateNameAlias.query.order_by(GovernorateNameAlias.alias_text).all():
        governorate_aliases.setdefault(alias.governorate_id, []).append(alias.alias_text)
    governorate_ids = [g.id for g in rows]
    branch_counts = {}
    active_branch_counts = {}
    employee_counts = {}
    if governorate_ids:
        branch_counts = dict(
            db.session.query(Branch.governorate_id, func.count(Branch.id))
            .filter(Branch.governorate_id.in_(governorate_ids))
            .group_by(Branch.governorate_id).all()
        )
        active_branch_counts = dict(
            db.session.query(Branch.governorate_id, func.count(Branch.id))
            .filter(Branch.governorate_id.in_(governorate_ids), Branch.is_active == True)
            .group_by(Branch.governorate_id).all()
        )
        employee_counts = dict(
            db.session.query(Branch.governorate_id, func.count(Employee.id))
            .join(Employee, Employee.branch_id == Branch.id)
            .filter(
                Branch.governorate_id.in_(governorate_ids),
                Branch.is_active == True,
                Employee.is_active == True,
            )
            .group_by(Branch.governorate_id).all()
        )
    return render_template(
        'governorates.html', rows=rows,
        active_governorates=sum(1 for g in rows if g.is_active),
        total_branches=sum(branch_counts.values()),
        total_employees=sum(employee_counts.values()),
        branch_counts=branch_counts, active_branch_counts=active_branch_counts,
        employee_counts=employee_counts, governorate_aliases=governorate_aliases,
    )


@bp.post('/governorates/<int:i>/aliases')
@req
@only('مسؤول التطبيق')
def governorate_alias_add(i):
    lock_entity_identity_writes(db.session)
    governorate = Governorate.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    if not governorate:
        abort(404)
    alias_text = (request.form.get('alias_text') or '').strip()[:200]
    normalized = normalize_alias_key(alias_text)
    if len(normalized) < 2 or normalized == normalize_alias_key(governorate.name):
        flash('اكتب اسمًا بديلًا واضحًا يختلف عن الاسم الرسمي.')
        return redirect('/governorates')
    if confirmed_alias_conflict('governorate', alias_text, target_id=governorate.id):
        flash('لا يمكن حفظ الاسم؛ فهو يطابق اسمًا رسميًا أو بديلًا مرتبطًا بمحافظة أخرى.')
        return redirect('/governorates')
    existing = GovernorateNameAlias.query.filter_by(normalized_alias=normalized).first()
    if existing:
        flash('الاسم البديل مرتبط بالفعل بالمحافظة نفسها.' if existing.governorate_id == i else 'الاسم البديل مرتبط بمحافظة أخرى؛ لم يتم تغيير الربط.')
        return redirect('/governorates')
    try:
        row = GovernorateNameAlias(governorate_id=i, alias_text=alias_text, normalized_alias=normalized, created_by=me().id)
        db.session.add(row)
        db.session.flush()
        log('ADD', 'GovernorateNameAlias', row.id, 'حفظ اسم محافظة بديل مؤكد')
        db.session.commit()
        flash('تم حفظ الاسم البديل وسيُستخدم في البحث والمطابقة.')
    except IntegrityError:
        db.session.rollback()
        flash('لم يُحفظ الاسم بسبب تعارض متزامن؛ أعد المحاولة بعد تحديث الصفحة.')
    return redirect('/governorates')


@bp.route('/governorates/<int:i>/edit', methods=['POST'])
@req
@only('مسؤول التطبيق')
def governorate_edit(i):
    lock_entity_identity_writes(db.session)
    x = Governorate.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    if not x:
        abort(404)
    n = request.form.get('name', '').strip()
    name_conflict = governorate_name_conflict(n, exclude_id=i)
    if not n:
        flash('الاسم غير صالح أو فارغ.')
    elif name_conflict:
        flash('الاسم يتعارض مع اسم رسمي أو بديل مؤكد لمحافظة أخرى؛ لم يتم التعديل.')
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
    lock_entity_identity_writes(db.session)
    x = Governorate.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
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
    lock_entity_identity_writes(db.session)
    x = Governorate.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    if not x:
        abort(404)
    if (
        Branch.query.filter_by(governorate_id=i).count()
        or UserGovernorate.query.filter_by(governorate_id=i).count()
        or ApprovalDelegation.query.filter_by(governorate_id=i).count()
    ):
        flash('لا يمكن الحذف لوجود ارتباطات؛ استخدم التعطيل.')
    else:
        db.session.delete(x)
        log('DELETE', 'Governorate', i)
        db.session.commit()
        flash('تم الحذف.')
    return redirect('/governorates')



def _render_branches_page(rows, gs):
    branch_ids = [branch.id for branch in rows]
    employee_counts = {}
    if branch_ids:
        employee_counts = dict(
            db.session.query(Employee.branch_id, func.count(Employee.id))
            .filter(Employee.branch_id.in_(branch_ids), Employee.is_active == True)
            .group_by(Employee.branch_id).all()
        )
    active_branches = sum(1 for branch in rows if branch.is_active)
    branch_aliases = {}
    for alias in BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(branch_ids) if branch_ids else False).order_by(BranchNameAlias.alias_text).all():
        branch_aliases.setdefault(alias.branch_id, []).append(alias.alias_text)
    return render_template(
        'branches.html', rows=rows, gs=gs, employee_counts=employee_counts,
        active_branches=active_branches, inactive_branches=len(rows) - active_branches,
        total_employees=sum(employee_counts.values()), branch_aliases=branch_aliases,
    )

@bp.route('/branches', methods=['GET', 'POST'])
@req
@only('مسؤول التطبيق', 'مشرف محافظة')
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
        return _render_branches_page(rows, gs)
    if request.method == 'POST':
        lock_entity_identity_writes(db.session)
        gid = request.form.get('governorate_id')
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        g = db.session.get(Governorate, int(gid)) if gid and gid.isdigit() else None
        if not g or not g.is_active or (not name) or (not code):
            flash('جميع بيانات الفرع مطلوبة: المحافظة والاسم والكود.')
        elif 'مسؤول التطبيق' not in roles() and not governorate_ok(g.id):
            abort(403)
        elif branch_name_conflict(name, g.id):
            flash('اسم الفرع موجود بالفعل داخل المحافظة أو يتعارض مع اسم بديل مؤكد.')
        elif branch_code_conflict(code, g.id):
            flash('كود الفرع مستخدم بالفعل في هذه المحافظة.')
        else:
            x = Branch(governorate_id=g.id, name=name, code=code)
            db.session.add(x)
            db.session.flush()
            log('ADD', 'Branch', x.id, name)
            db.session.commit()
            flash('تمت إضافة الفرع. يمكنك إسناد مسؤول إدخال الفروع من مركز التكليفات في الرئيسية.')
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
    return _render_branches_page(rows, gs)


@bp.post('/branches/<int:i>/aliases')
@req
@only('مسؤول التطبيق')
def branch_alias_add(i):
    lock_entity_identity_writes(db.session)
    branch = Branch.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    if not branch:
        abort(404)
    alias_text = (request.form.get('alias_text') or '').strip()[:200]
    normalized = normalize_alias_key(alias_text)
    if len(normalized) < 2 or normalized == normalize_alias_key(branch.name):
        flash('اكتب اسمًا بديلًا واضحًا يختلف عن الاسم الرسمي.')
        return redirect('/branches')
    if confirmed_alias_conflict('branch', alias_text, target_id=branch.id):
        flash('لا يمكن حفظ الاسم؛ فهو يطابق اسمًا رسميًا أو بديلًا مرتبطًا بفرع آخر.')
        return redirect('/branches')
    existing = BranchNameAlias.query.filter_by(normalized_alias=normalized).first()
    if existing:
        flash('الاسم البديل مرتبط بالفعل بالفرع نفسه.' if existing.branch_id == i else 'الاسم البديل مرتبط بفرع آخر؛ لم يتم تغيير الربط.')
        return redirect('/branches')
    try:
        row = BranchNameAlias(branch_id=i, alias_text=alias_text, normalized_alias=normalized, created_by=me().id)
        db.session.add(row)
        db.session.flush()
        log('ADD', 'BranchNameAlias', row.id, 'حفظ اسم فرع بديل مؤكد')
        db.session.commit()
        flash('تم حفظ اسم الفرع البديل لاستخدامه في البحث والمطابقة.')
    except IntegrityError:
        db.session.rollback()
        flash('لم يُحفظ الاسم بسبب تعارض متزامن؛ أعد المحاولة بعد تحديث الصفحة.')
    return redirect('/branches')


@bp.post('/branches/<int:i>/edit')
@req
@only('مسؤول التطبيق', 'مشرف محافظة')
def branch_edit(i):
    lock_entity_identity_writes(db.session)
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    x = Branch.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    try:
        requested_governorate_id = int(request.form.get('governorate_id', '0'))
    except (TypeError, ValueError):
        requested_governorate_id = 0
    g = Governorate.query.populate_existing().filter_by(id=requested_governorate_id).with_for_update().one_or_none()
    n = request.form.get('name', '').strip()
    code = request.form.get('code', '').strip()
    if not x or not g or (not g.is_active) or (not n) or (not code):
        flash('جميع بيانات الفرع مطلوبة.')
        return redirect('/branches')
    if (
        'مسؤول التطبيق' not in roles()
        and (not governorate_ok(x.governorate_id) or not governorate_ok(g.id))
    ):
        abort(403)
    # Changing a branch's parent governorate changes the effective scope of every
    # linked employee, movement and entry assignment. Do not silently migrate a
    # populated branch; administrators must first resolve those relationships.
    if x.governorate_id != g.id and (
        Employee.query.filter_by(branch_id=i).count()
        or UserBranch.query.filter_by(branch_id=i).count()
        or EntryAssignmentBranch.query.filter_by(branch_id=i).count()
        or Movement.query.filter_by(branch_id=i).count()
        or Movement.query.filter_by(destination_branch_id=i).count()
    ):
        flash('لا يمكن نقل فرع مرتبط بموظفين أو مستخدمين أو حركات إلى محافظة أخرى؛ عالج الارتباطات أولًا.')
        return redirect('/branches')
    name_conflict = branch_name_conflict(n, g.id, exclude_id=i)
    duplicate_code = branch_code_conflict(code, g.id, exclude_id=i)
    if name_conflict:
        flash('اسم الفرع موجود بالفعل داخل المحافظة أو يتعارض مع اسم بديل مؤكد.')
    elif duplicate_code:
        flash('كود الفرع مستخدم بالفعل في هذه المحافظة.')
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
@only('مسؤول التطبيق', 'مشرف محافظة')
def branch_toggle(i):
    lock_entity_identity_writes(db.session)
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    x = Branch.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    if not x:
        abort(404)
    if 'مسؤول التطبيق' not in roles() and not governorate_ok(x.governorate_id):
        abort(403)
    # A branch must not be reactivated while its parent governorate is inactive.
    if not x.is_active:
        parent = db.session.get(Governorate, x.governorate_id)
        if not parent or not parent.is_active:
            flash('لا يمكن تفعيل الفرع قبل تفعيل المحافظة التابعة له.')
            return redirect('/branches')
    x.is_active = not x.is_active
    log('TOGGLE', 'Branch', i)
    db.session.commit()
    return redirect('/branches')


@bp.post('/branches/<int:i>/delete')
@req
@only('مسؤول التطبيق', 'مشرف محافظة')
def branch_delete(i):
    lock_entity_identity_writes(db.session)
    if not can('manage_structure') or not has_role('مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'):
        abort(403)
    x = Branch.query.populate_existing().filter_by(id=i).with_for_update().one_or_none()
    if not x:
        abort(404)
    if 'مسؤول التطبيق' not in roles() and not governorate_ok(x.governorate_id):
        abort(403)
    if (
        Employee.query.filter_by(branch_id=i).count()
        or UserBranch.query.filter_by(branch_id=i).count()
        or EntryAssignmentBranch.query.filter_by(branch_id=i).count()
        # Both source and destination references must be checked before deleting
        # a branch; historical movements can still point to it as their origin.
        or Movement.query.filter_by(branch_id=i).count()
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
            db.session.flush()
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
