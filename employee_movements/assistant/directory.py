"""Scope-aware employee and branch lookup for the assistant."""

import re

from ..access import bids, can, me, readable_branch_ids
from ..extensions import db
from ..models import AssistantAlias, Branch, BranchNameAlias, Employee, EmployeeNameAlias, Governorate, TicketEmployeeCodeAlias
from ..services.entity_matching import (
    employee_search_filter, branch_search_filter, normalize_alias_key,
    rank_scoped_employee_suggestions, rank_scoped_branch_suggestions,
)
from ..services.ticket_matching import job_code_lookup_variants, normalize_job_code
from .text import normalize_for_search


# v34.91 — إصلاح نافذة المساعد العائمة داخل التطبيق وإزالة حجب X-Frame-Options.
def _lookup_branch_ids():
    """Return active branches readable by this request, independent of write scope."""
    if can('view_reports'):
        return set(readable_branch_ids())
    return set(bids())


def scope_employees():
    branch_ids = _lookup_branch_ids()
    if not branch_ids:
        return []
    return (
        Employee.query
        .filter(Employee.is_active == True, Employee.branch_id.in_(branch_ids))
        .order_by(Employee.full_name)
        .all()
    )


def _sql_arabic_fold(column):
    """Fold common Arabic spelling variants in SQL before applying LIKE.

    Python normalization alone is not enough: PostgreSQL/SQLite substring matching
    against a raw value like ``أحمد`` will not match ``احمد`` before normalization.
    """
    expr = column
    for source, target in (
        ('أ', 'ا'), ('إ', 'ا'), ('آ', 'ا'), ('ٱ', 'ا'),
        ('ى', 'ي'), ('ئ', 'ي'), ('ؤ', 'و'), ('ة', 'ه'),
    ):
        expr = db.func.replace(expr, source, target)
    return expr


def _alias_employee(value, normalized_value):
    user = me()
    if not user or not normalized_value:
        return None
    alias = AssistantAlias.query.filter_by(
        user_id=user.id,
        normalized_alias=normalized_value[:160],
    ).first()
    if not alias:
        return None
    employee = db.session.get(Employee, alias.employee_id)
    if not employee or not employee.is_active:
        return None
    if employee.branch_id not in _lookup_branch_ids():
        return None
    return employee


def _safe_like_pattern(value):
    """Create a literal substring LIKE pattern (user %/_ are not wildcards)."""
    escaped = str(value or '').replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def find_employee(value):
    value = (value or '').strip()
    if not value:
        return None, []
    nv = normalize_for_search(value)
    remembered = _alias_employee(value, nv)
    if remembered:
        return remembered, [remembered]

    allowed_branches = _lookup_branch_ids()
    candidate_query = Employee.query.filter(
        Employee.is_active == True,
        Employee.branch_id.in_(allowed_branches) if allowed_branches else False,
        employee_search_filter(value, include_job_title=True, include_branch=True),
    )
    rows = candidate_query.order_by(Employee.full_name).limit(100).all()
    name_key = normalize_alias_key(value)
    code_key = normalize_alias_key(value, 'code')
    row_ids = [employee.id for employee in rows]
    name_alias_map = {}
    code_alias_map = {}
    if row_ids:
        for alias in EmployeeNameAlias.query.filter(EmployeeNameAlias.employee_id.in_(row_ids)).all():
            name_alias_map.setdefault(alias.employee_id, []).append(alias.alias_text)
        for alias in TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.employee_id.in_(row_ids)).all():
            code_alias_map.setdefault(alias.employee_id, []).append(alias.alias_text)
    alias_employee_ids = {
        row.employee_id for row in EmployeeNameAlias.query.filter_by(normalized_alias=name_key).all()
    } if name_key else set()
    code_variants = job_code_lookup_variants(code_key)
    code_alias_ids = {
        row.employee_id for row in TicketEmployeeCodeAlias.query.filter(
            TicketEmployeeCodeAlias.normalized_alias.in_(code_variants)
        ).all()
    } if code_variants else set()
    exact = [
        employee for employee in rows
        if normalize_for_search(employee.full_name) == nv
        or (employee.job_code and normalize_job_code(employee.job_code) in code_variants)
        or (employee.employee_code and normalize_job_code(employee.employee_code) in code_variants)
        or employee.id in alias_employee_ids
        or employee.id in code_alias_ids
        or any(normalize_alias_key(alias) == name_key for alias in name_alias_map.get(employee.id, []))
        or any(normalize_job_code(alias) in code_variants for alias in code_alias_map.get(employee.id, []))
    ]
    if len(exact) == 1:
        return exact[0], exact
    parts = [part for part in re.split(r'\s+', nv) if len(part) >= 2]
    matches = [
        employee for employee in rows
        if nv in normalize_for_search(employee.full_name)
        or (employee.job_code and nv in normalize_for_search(employee.job_code))
        or (employee.employee_code and nv in normalize_for_search(employee.employee_code))
        or employee.id in alias_employee_ids
        or employee.id in code_alias_ids
        or any(nv in normalize_for_search(alias) for alias in name_alias_map.get(employee.id, []))
        or any(nv in normalize_for_search(alias) for alias in code_alias_map.get(employee.id, []))
    ]
    if not matches and parts:
        matches = [employee for employee in rows if all(part in normalize_for_search(employee.full_name) for part in parts)]
    if matches:
        # A partial substring is evidence for a suggestion, not proof of identity.
        # Even a single partial result must be explicitly selected by the user.
        return None, matches

    # Fuzzy results are never selected automatically. The pool is bounded and
    # already filtered by the caller's branch/governorate authorization scope.
    fallback = Employee.query.filter(
        Employee.is_active == True,
        Employee.branch_id.in_(allowed_branches) if allowed_branches else False,
    )
    pool = fallback.order_by(Employee.full_name).limit(2500).all()
    suggestions = rank_scoped_employee_suggestions(value, pool, limit=8)
    suggested_employees = [item['employee'] for item in suggestions]
    return None, suggested_employees


def find_branch(value, governorate_id=None):
    value = (value or '').strip()
    if not value:
        return None, []
    query = Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(
        Branch.is_active == True, Governorate.is_active == True,
        branch_search_filter(value, include_governorate=True),
    )
    if governorate_id:
        query = query.filter(Branch.governorate_id == governorate_id)
    allowed = _lookup_branch_ids()
    query = query.filter(Branch.id.in_(allowed)) if allowed else query.filter(False)
    rows = query.order_by(Branch.name).limit(100).all()
    nv = normalize_for_search(value)
    alias_key = normalize_alias_key(value)
    alias_branch_ids = {
        alias.branch_id for alias in BranchNameAlias.query.filter_by(normalized_alias=alias_key).all()
    } if alias_key else set()
    normalized_digits = str(value).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"))
    query_code_tokens = set(re.findall(r"(?<![A-Za-z0-9])\d{2,}(?![A-Za-z0-9])", normalized_digits))
    exact = [
        branch for branch in rows
        if normalize_for_search(branch.name) == nv
        or (branch.code and normalize_for_search(branch.code) == nv)
        or (branch.code and normalize_job_code(branch.code) in query_code_tokens)
        or branch.id in alias_branch_ids
    ]
    if len(exact) == 1:
        return exact[0], exact
    matches = [
        branch for branch in rows
        if nv in normalize_for_search(branch.name)
        or (branch.code and nv in normalize_for_search(branch.code))
        or branch.id in alias_branch_ids
    ]
    if matches:
        # Exact official/confirmed-alias matches were handled above. A substring
        # or partial branch-code match still requires explicit human selection.
        return None, matches

    # Only search the already-scoped catalogue; a fuzzy branch is a suggestion,
    # never an implicit destination selection.
    fallback_query = Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(
        Branch.is_active == True, Governorate.is_active == True,
    )
    if governorate_id:
        fallback_query = fallback_query.filter(Branch.governorate_id == governorate_id)
    fallback_query = fallback_query.filter(Branch.id.in_(allowed)) if allowed else fallback_query.filter(False)
    pool = fallback_query.order_by(Branch.name).limit(2500).all()
    suggestions = rank_scoped_branch_suggestions(value, pool, limit=8)
    return None, [item['branch'] for item in suggestions]
