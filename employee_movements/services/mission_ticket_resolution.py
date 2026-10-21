"""Database-backed identity resolution for screenshot-created missions.

This module owns matching and alias persistence. HTTP route orchestration and
form rendering remain in :mod:`employee_movements.blueprints.missions`.
"""
from __future__ import annotations

import re

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from ..access import (
    can_manage_movement_destination,
    can_manage_movement_employee,
    log,
)
from ..extensions import db
from ..models import (
    Branch,
    BranchNameAlias,
    Employee,
    Governorate,
    TicketEmployeeCodeAlias,
)
from ..search import normalized_sql_text
from .identity_locks import lock_employee_identity_writes
from .ticket_matching import (
    branch_code_match_candidates,
    branch_exact_match,
    job_code_lookup_variants,
    normalize_entity_name,
    normalize_job_code,
    rank_branch_candidates,
    rank_employee_code_candidates,
)


def _ticket_mission_all_active_branches():
    return (
        Branch.query.join(Governorate, Governorate.id == Branch.governorate_id)
        .filter(Branch.is_active == True, Governorate.is_active == True)
        .order_by(Governorate.name.asc(), Branch.name.asc())
        .all()
    )


def _ticket_mission_strip_branch_code_tokens(value, branches):
    codes = {normalize_job_code(branch.code or '') for branch in branches if normalize_job_code(branch.code or '')}
    text = str(value or '')
    for token_match in list(re.finditer(r"[A-Za-z0-9٠-٩۰-۹]+", text))[::-1]:
        if normalize_job_code(token_match.group(0)) in codes:
            text = text[:token_match.start()] + ' ' + text[token_match.end():]
    return re.sub(r"\s+", " ", text).strip(" -–—|·")


def _ticket_mission_basic_branch_alias_matches(value, branch):
    """Match the employee's known basic branch while guarding duplicate branch codes."""
    if not branch:
        return False
    all_active = _ticket_mission_all_active_branches()
    global_records = _ticket_mission_branch_records(all_active)
    global_code_matches = branch_code_match_candidates(value, global_records)
    branch_records = _ticket_mission_branch_records([branch])
    if global_code_matches:
        # Exact branch codes are authoritative only when globally unique and
        # attached to this branch. A duplicated code must be disambiguated by name.
        if len(global_code_matches) == 1:
            return global_code_matches[0]['id'] == branch.id
        name_value = _ticket_mission_strip_branch_code_tokens(value, all_active)
        name_records = [{
            **record,
            'code': '',
            'label': ' · '.join(part for part in (
                branch.name,
                branch.governorate.name if branch.governorate else '',
            ) if part),
        } for record in branch_records]
        return len(branch_exact_match(name_value, name_records)) == 1
    return len(branch_exact_match(value, branch_records)) == 1


def _ticket_mission_branches():
    """Return only active destinations available to the current user's assignment scope."""
    rows = _ticket_mission_all_active_branches()
    return [branch for branch in rows if can_manage_movement_destination(branch, 'انتداب')]


def _ticket_job_code_sql(column):
    """SQL-side counterpart of normalize_job_code for formatted official codes."""
    expression = normalized_sql_text(column)
    for separator in (' ', '-', '‐', '‑', '–', '—', '/', '.', '_'):
        expression = func.replace(expression, separator, '')
    return expression


def _ticket_mission_employee(job_code):
    """Resolve one active employee by official code or a confirmed alternate code.

    Missing ``200`` is supported only when all exact/prefix/alias variants point
    to the same employee. Ambiguity always requires manual resolution.
    """
    code = normalize_job_code(job_code)
    if not code:
        return None, 'لم يُقرأ الكود الوظيفي بوضوح. اكتبه كما يظهر في التيكيت.'
    if len(code) < 4:
        return None, 'الكود الوظيفي المقروء قصير جدًا لتحديد موظف بأمان. راجعه يدويًا أو أعد رفع صورة أوضح.'
    variants = job_code_lookup_variants(code)
    official_rows = (
        Employee.query.filter(
            Employee.is_active == True,
            Employee.job_code.isnot(None),
            _ticket_job_code_sql(Employee.job_code).in_(variants),
        )
        .options(joinedload(Employee.branch).joinedload(Branch.governorate))
        .all()
    )
    alias_rows = (
        TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.normalized_alias.in_(variants))
        .join(Employee, Employee.id == TicketEmployeeCodeAlias.employee_id)
        .filter(Employee.is_active == True)
        .options(joinedload(TicketEmployeeCodeAlias.employee).joinedload(Employee.branch).joinedload(Branch.governorate))
        .all()
    )
    candidates_by_id = {employee.id: employee for employee in official_rows}
    for alias in alias_rows:
        candidates_by_id[alias.employee.id] = alias.employee
    if not candidates_by_id:
        return None, 'لم يُعثر على موظف نشط بهذا الكود أو بصيغة بديلة مؤكدة. راجع الكود أو اختر موظفًا من الاقتراحات.'
    if len(candidates_by_id) > 1:
        return None, 'الكود أو إحدى صِيَغه المحتملة يطابق أكثر من موظف. لم نختَر أحدًا تلقائيًا؛ اختر الموظف الصحيح من المرشحين.'
    employee = next(iter(candidates_by_id.values()))
    if not can_manage_movement_employee(employee, 'انتداب'):
        return None, 'الموظف خارج نطاق الصلاحية المتاح لك لتسجيل الانتداب.'
    return employee, ''


def _ticket_mission_employee_suggestions(job_code, basic_branch_name='', limit=5):
    """Return scoped fuzzy candidates from official codes and confirmed aliases.

    Results are only displayed for human confirmation and are never auto-selected.
    """
    code = normalize_job_code(job_code)
    if len(code) < 4:
        return []
    variants = job_code_lookup_variants(code)
    lengths = set()
    for variant in variants:
        for delta in (-1, 0, 1):
            if len(variant) + delta >= 4:
                lengths.add(len(variant) + delta)
    if not lengths:
        return []

    code_length = func.length(_ticket_job_code_sql(Employee.job_code))
    employee_rows = (
        Employee.query.filter(
            Employee.is_active == True,
            Employee.job_code.isnot(None),
            code_length.in_(sorted(lengths)),
        )
        .options(joinedload(Employee.branch).joinedload(Branch.governorate))
        .order_by(Employee.id.asc())
        .limit(5000)
        .all()
    )
    alias_rows = (
        TicketEmployeeCodeAlias.query.filter(
            func.length(TicketEmployeeCodeAlias.normalized_alias).in_(sorted(lengths))
        )
        .join(Employee, Employee.id == TicketEmployeeCodeAlias.employee_id)
        .filter(Employee.is_active == True)
        .options(joinedload(TicketEmployeeCodeAlias.employee).joinedload(Employee.branch).joinedload(Branch.governorate))
        .all()
    )
    by_id = {employee.id: employee for employee in employee_rows}
    aliases_by_employee = {}
    for alias in alias_rows:
        by_id[alias.employee.id] = alias.employee
        aliases_by_employee.setdefault(alias.employee.id, []).append(alias.alias_text)

    ranked = rank_employee_code_candidates(
        code, by_id.values(), basic_branch_name, limit=40,
        aliases_by_employee=aliases_by_employee,
    )
    suggestions = []
    for match in ranked:
        employee = match['employee']
        if not can_manage_movement_employee(employee, 'انتداب'):
            continue
        suggestions.append(match)
        if len(suggestions) >= limit:
            break
    return suggestions


def _ticket_mission_save_job_code_alias(raw_code, employee, creator_id):
    """Persist a corrected OCR code only after explicit opt-in and unique checks."""
    alias_text = str(raw_code or '').strip()[:100]
    normalized_alias = normalize_job_code(alias_text)
    official_code = normalize_job_code(employee.job_code or '')
    if not normalized_alias or len(normalized_alias) < 4 or not official_code:
        return False, 'لم تُحفظ صيغة الكود البديلة لأنها قصيرة أو غير واضحة.'
    if normalized_alias == official_code or normalized_alias in job_code_lookup_variants(official_code):
        return False, ''  # Prefix-200 variants are resolved natively and need no alias.

    # Alias creation mutates the same global personnel-code namespace as Excel,
    # manual edits, and assistant actions; acquire the shared lock before any
    # collision scan so the check-and-insert is serialized on PostgreSQL.
    lock_employee_identity_writes(db.session)
    db.session.refresh(employee, with_for_update=True)
    # The target's canonical code may have changed while this request waited for
    # the lock; re-check the no-alias-needed case against the fresh row.
    official_code = normalize_job_code(employee.job_code or '')
    if normalized_alias == official_code or normalized_alias in job_code_lookup_variants(official_code):
        return False, ''
    variants = job_code_lookup_variants(normalized_alias)
    official_matches = Employee.query.populate_existing().filter(Employee.job_code.isnot(None)).all()
    conflicting_official = [
        row for row in official_matches
        if row.id != employee.id and normalize_job_code(row.job_code) in variants
    ]
    if conflicting_official:
        return False, 'لم تُحفظ صيغة الكود البديلة لأنها قد تطابق كودًا رسميًا لموظف آخر.'

    alias_matches = TicketEmployeeCodeAlias.query.filter(
        TicketEmployeeCodeAlias.normalized_alias.in_(variants)
    ).all()
    for existing in alias_matches:
        if existing.employee_id != employee.id:
            return False, 'لم تُحفظ صيغة الكود البديلة لأنها مرتبطة بموظف آخر أو قد تسبب التباسًا.'
        return False, 'صيغة الكود أو أحد أشكالها معروفة مسبقًا لهذا الموظف.'

    alias = TicketEmployeeCodeAlias(
        employee_id=employee.id,
        alias_text=alias_text,
        normalized_alias=normalized_alias,
        created_by=creator_id,
    )
    try:
        # Savepoint protects the already-validated mission transaction from a
        # concurrent request trying to register the same global alias.
        with db.session.begin_nested():
            db.session.add(alias)
            db.session.flush()
    except IntegrityError:
        return False, 'لم تُحفظ صيغة الكود البديلة لأنها أُضيفت بالتزامن أو أصبحت متعارضة.'
    log('ADD', 'TicketEmployeeCodeAlias', alias.id, 'حفظ صيغة كود بديلة بعد تأكيد مستخدم مخوّل')
    return True, 'تم حفظ صيغة الكود التي صححتها كبديل مؤكد لهذا الموظف.'


def _ticket_mission_branch_records(branches):
    """Provide branch names and confirmed aliases for current-scope matching."""
    if not branches:
        return []
    branch_ids = [branch.id for branch in branches]
    aliases = BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(branch_ids)).all()
    by_branch = {}
    for alias in aliases:
        by_branch.setdefault(alias.branch_id, []).append(alias.alias_text)
    records = []
    for branch in branches:
        governorate_name = branch.governorate.name if branch.governorate else ''
        records.append({
            'id': branch.id,
            'name': branch.name,
            'code': branch.code or '',
            'label': ' · '.join(part for part in (branch.code or '', branch.name, governorate_name) if part),
            'aliases': by_branch.get(branch.id, []),
            'branch': branch,
        })
    return records


def _ticket_mission_branch_choices(value, branches):
    """Auto-select only a unique official name, confirmed alias or globally unique branch code."""
    records = _ticket_mission_branch_records(branches)
    if not value:
        return '', [], ''

    code_matches = branch_code_match_candidates(value, records)
    if code_matches:
        # A branch code is only an automatic identifier when it is unique across
        # all active branches, not merely unique inside the current user's scope.
        all_active_branches = _ticket_mission_all_active_branches()
        global_code_matches = branch_code_match_candidates(
            value, _ticket_mission_branch_records(all_active_branches),
        )
        if len(global_code_matches) == 1 and global_code_matches[0]['id'] == code_matches[0]['id']:
            return code_matches[0]['id'], [], ''
        # If code is duplicated, strip code tokens and match only the branch name
        # and governorate. This avoids a duplicate code embedded in ``label`` from
        # turning a possibly ambiguous code into an accidental exact match.
        name_query = _ticket_mission_strip_branch_code_tokens(value, all_active_branches)
        name_records = [
            {
                **record,
                'code': '',
                'label': ' · '.join(part for part in (
                    record['branch'].name,
                    record['branch'].governorate.name if record['branch'].governorate else '',
                ) if part),
            }
            for record in records
        ]
        name_exact = branch_exact_match(name_query, name_records)
        if len(name_exact) == 1:
            return name_exact[0]['id'], [], ''
        suggestions = rank_branch_candidates(name_query, name_records, limit=5)
        return '', suggestions, 'كود الفرع غير فريد بين الفروع النشطة. اختر الوجهة يدويًا بعد مراجعة الاسم والمحافظة.'

    exact = branch_exact_match(value, records)
    if len(exact) == 1:
        return exact[0]['id'], [], ''
    suggestions = rank_branch_candidates(value, records, limit=5)
    if len(exact) > 1:
        return '', suggestions or exact[:5], 'اسم الفرع يطابق أكثر من فرع. اختر الوجهة يدويًا من الاقتراحات.'
    if suggestions:
        return '', suggestions, 'لم نجد تطابقًا حرفيًا مؤكدًا لاسم الوجهة؛ اختر الفرع الصحيح من الاقتراحات أو القائمة.'
    return '', [], 'لم يطابق اسم الوجهة سجلًا واضحًا. اختر الفرع الصحيح يدويًا من القائمة.'


def _ticket_mission_save_branch_alias(raw_name, branch, creator_id):
    """Save a corrected spelling only after explicit opt-in and successful validation."""
    alias_text = str(raw_name or '').strip()[:200]
    branch_code = normalize_job_code(branch.code or '')
    if branch_code and branch_code.isalnum():
        # If the OCR phrase contains the exact branch code, store the remaining
        # branch wording as the alias rather than baking the code into the name.
        for token_match in re.finditer(r"[A-Za-z0-9٠-٩۰-۹]+", alias_text):
            if normalize_job_code(token_match.group(0)) == branch_code:
                alias_text = (alias_text[:token_match.start()] + ' ' + alias_text[token_match.end():]).strip(" -–—|·")
                break
    normalized_alias = normalize_entity_name(alias_text)
    official = normalize_entity_name(branch.name)
    if not normalized_alias or normalized_alias == official:
        return False, ''

    existing = BranchNameAlias.query.filter_by(normalized_alias=normalized_alias).first()
    if existing:
        if existing.branch_id == branch.id:
            return False, 'صيغة اسم الفرع محفوظة مسبقًا ضمن الأسماء البديلة.'
        return False, 'لم تُحفظ الصيغة البديلة لأنها مرتبطة باسم بديل آخر؛ تجنبنا إنشاء تطابق متعارض.'

    # Do not learn a spelling if it also looks like another active branch/alias.
    all_branches = _ticket_mission_all_active_branches()
    all_records = _ticket_mission_branch_records(all_branches)
    exact = branch_exact_match(alias_text, all_records)
    if any(item['id'] != branch.id for item in exact):
        return False, 'لم تُحفظ الصيغة البديلة لأنها قد تشير إلى فرع آخر.'
    db.session.add(BranchNameAlias(
        branch_id=branch.id,
        alias_text=alias_text,
        normalized_alias=normalized_alias,
        created_by=creator_id,
    ))
    db.session.flush()
    return True, 'تم حفظ صيغة اسم الفرع كاسم بديل لتسهيل التعرف عليها لاحقًا.'

