"""Scope-aware employee and branch lookup for the assistant."""

import re

from ..access import bids
from ..models import Branch, Employee
from .text import normalize_for_search


# v34.91 — إصلاح نافذة المساعد العائمة داخل التطبيق وإزالة حجب X-Frame-Options.
def scope_employees():
    bs = bids()
    return (
        (
            Employee.query.filter(Employee.is_active == True, Employee.branch_id.in_(bs))
            .order_by(Employee.full_name)
            .all()
        )
        if bs
        else []
    )


def find_employee(value):
    value = (value or '').strip()
    if not value:
        return None, []
    rows = scope_employees()
    nv = normalize_for_search(value)
    exact = [
        e
        for e in rows
        if normalize_for_search(e.full_name) == nv or (e.job_code and normalize_for_search(e.job_code) == nv)
    ]
    if len(exact) == 1:
        return exact[0], exact
    parts = [x for x in re.split('\\s+', nv) if len(x) >= 2]
    matches = [
        e
        for e in rows
        if nv in normalize_for_search(e.full_name) or (e.job_code and nv in normalize_for_search(e.job_code))
    ]
    if not matches and parts:
        matches = [
            e
            for e in rows
            if all((part in normalize_for_search(e.full_name) for part in parts))
        ]
    return matches[0] if len(matches) == 1 else None, matches


def find_branch(value, governorate_id=None):
    value = (value or '').strip()
    q = Branch.query.filter(Branch.is_active == True)
    if governorate_id:
        q = q.filter(Branch.governorate_id == governorate_id)
    allowed = set(bids())
    rows = q.filter(Branch.id.in_(allowed)).order_by(Branch.name).all() if allowed else []
    nv = normalize_for_search(value)
    exact = [
        b
        for b in rows
        if normalize_for_search(b.name) == nv or (b.code and normalize_for_search(b.code) == nv)
    ]
    if len(exact) == 1:
        return exact[0], exact
    matches = [
        b
        for b in rows
        if nv in normalize_for_search(b.name) or (b.code and nv in normalize_for_search(b.code))
    ]
    return matches[0] if len(matches) == 1 else None, matches
