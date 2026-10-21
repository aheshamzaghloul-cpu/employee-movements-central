"""Shared identity-conflict rules for canonical entities and confirmed aliases.

This module is the common validation layer for the admin UI, assistant plans,
and Excel approval. It performs conservative conflict detection only; callers
remain responsible for authorization, locking, transaction handling, and clear
user-facing messages.
"""
from __future__ import annotations

import re


from ..models import (
    Branch,
    BranchNameAlias,
    Employee,
    EmployeeNameAlias,
    Governorate,
    GovernorateNameAlias,
)
from .entity_matching import alias_owner_conflict, normalize_alias_key


def governorate_name_conflict(name: object, *, exclude_id: int | None = None):
    """Return a conflicting canonical governorate or confirmed alias, if any.

    Comparison uses the same normalized key as confirmed aliases, making the
    manual, assistant, and Excel paths agree on spelling variants.
    """
    key = normalize_alias_key(name)
    if not key:
        return None
    for row in Governorate.query.populate_existing().with_entities(
        Governorate.id, Governorate.name
    ).all():
        row_id, row_name = row
        if exclude_id is not None and int(row_id) == int(exclude_id):
            continue
        if normalize_alias_key(row_name) == key:
            return row
    alias = GovernorateNameAlias.query.populate_existing().filter_by(
        normalized_alias=key
    ).first()
    if alias and (exclude_id is None or int(alias.governorate_id) != int(exclude_id)):
        return alias
    return None


def branch_name_conflict(
    name: object,
    governorate_id: int,
    *,
    exclude_id: int | None = None,
    ignore_branch_ids: set[int] | None = None,
):
    """Return a conflicting branch name/alias in the target governorate.

    Official branch names may repeat across different governorates; within one
    governorate they must be unique after normalization. Confirmed aliases are
    globally unique and may not shadow another branch's canonical name.
    ``ignore_branch_ids`` supports Excel final-state overlays for branches that
    are themselves being renamed in the same approved batch.
    """
    key = normalize_alias_key(name)
    if not key:
        return None
    ignored_canonical = {int(value) for value in (ignore_branch_ids or set())}
    if exclude_id is not None:
        ignored_canonical.add(int(exclude_id))

    rows = Branch.query.populate_existing().filter(
        Branch.governorate_id == int(governorate_id)
    ).with_entities(Branch.id, Branch.name).all()
    for row_id, row_name in rows:
        if int(row_id) in ignored_canonical:
            continue
        if normalize_alias_key(row_name) == key:
            return (row_id, row_name)

    alias = BranchNameAlias.query.populate_existing().filter_by(
        normalized_alias=key
    ).first()
    if alias and (exclude_id is None or int(alias.branch_id) != int(exclude_id)):
        return alias
    return None


_BRANCH_CODE_DIGITS = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)


def normalize_branch_code_key(value: object) -> str:
    """Normalize branch-code spacing/case and Arabic digits consistently."""
    key = str(value or "").replace("\u200f", "").replace("\u200e", "")
    key = key.translate(_BRANCH_CODE_DIGITS).strip()
    if re.fullmatch(r"\d+\.0+", key):
        key = key.split(".", 1)[0]
    return re.sub(r"\s+", " ", key).casefold()


def branch_code_conflict(
    code: object,
    governorate_id: int,
    *,
    exclude_id: int | None = None,
):
    """Return an existing branch with the same normalized code in its governorate."""
    key = normalize_branch_code_key(code)
    if not key:
        return None
    query = Branch.query.populate_existing().filter(
        Branch.governorate_id == int(governorate_id)
    )
    if exclude_id is not None:
        query = query.filter(Branch.id != int(exclude_id))
    for branch in query.with_entities(Branch.id, Branch.code).all():
        if normalize_branch_code_key(branch.code) == key:
            return branch
    return None



def employee_name_conflict(
    name: object,
    branch_id: int,
    *,
    exclude_employee_id: int | None = None,
):
    """Return an employee-name conflict under the shared identity policy.

    A person's canonical name is not a globally unique identifier: duplicate
    canonical names are blocked within the same branch, while the same name in
    another branch is permitted. A confirmed global alias may not be reused as
    another employee's canonical name.
    """
    key = normalize_alias_key(name)
    if not key:
        return None
    query = Employee.query.populate_existing().filter(
        Employee.branch_id == int(branch_id)
    )
    if exclude_employee_id is not None:
        query = query.filter(Employee.id != int(exclude_employee_id))
    for employee_id, full_name in query.with_entities(Employee.id, Employee.full_name).all():
        if normalize_alias_key(full_name) == key:
            return (employee_id, full_name)

    alias = EmployeeNameAlias.query.populate_existing().filter_by(
        normalized_alias=key
    ).first()
    if alias and (
        exclude_employee_id is None
        or int(alias.employee_id) != int(exclude_employee_id)
    ):
        return alias
    return None

def governorate_write_snapshot(governorate: Governorate) -> dict[str, object]:
    """Capture the editable identity/state fields shown in a structure preview."""
    return {
        "id": int(governorate.id),
        "name": str(governorate.name or ""),
        "is_active": bool(governorate.is_active),
    }


def branch_write_snapshot(branch: Branch) -> dict[str, object]:
    """Capture a branch's canonical identity and parent/state for safe confirmation."""
    return {
        "id": int(branch.id),
        "governorate_id": int(branch.governorate_id),
        "name": str(branch.name or ""),
        "code": str(branch.code or ""),
        "is_active": bool(branch.is_active),
    }


def confirmed_alias_conflict(
    kind: str,
    value: object,
    *,
    target_id: int | None = None,
):
    """Return an owner conflict before confirming an alternate spelling/code."""
    return alias_owner_conflict(kind, value, target_id=target_id)
