"""Build search payloads for already-scoped employee, branch and movement rows.

Callers must apply authorization and operational-scope filters before passing
rows here. This module enriches those rows with confirmed aliases only; it does
not select the set of records the user is allowed to see.
"""

from ..models import (
    BranchNameAlias,
    EmployeeNameAlias,
    GovernorateNameAlias,
    TicketEmployeeCodeAlias,
)


def _alias_text_map(model, owner_field, owner_ids):
    """Load confirmed search aliases only for records already inside a scoped result set."""
    ids = sorted({int(value) for value in (owner_ids or []) if value is not None})
    if not ids:
        return {}
    owner_column = getattr(model, owner_field)
    output = {}
    for alias in model.query.filter(owner_column.in_(ids)).order_by(model.id).all():
        text = str(getattr(alias, 'alias_text', '') or '').strip()
        if text:
            output.setdefault(getattr(alias, owner_field), []).append(text)
    return output


def _branch_search_payload(branches):
    """Serialize scoped branches with confirmed alias text for client-side search."""
    rows = list(branches or [])
    branch_ids = [branch.id for branch in rows]
    gov_ids = [branch.governorate_id for branch in rows if branch.governorate_id is not None]
    branch_aliases = _alias_text_map(BranchNameAlias, 'branch_id', branch_ids)
    gov_aliases = _alias_text_map(GovernorateNameAlias, 'governorate_id', gov_ids)
    return [
        {
            'id': branch.id,
            'name': branch.name,
            'code': branch.code or '',
            'governorate_id': branch.governorate_id,
            'governorate': branch.governorate.name if branch.governorate else '',
            'search_aliases': ' '.join([*branch_aliases.get(branch.id, []), *gov_aliases.get(branch.governorate_id, [])]),
        }
        for branch in rows
    ]


def _employee_search_aliases(employees):
    """Return local aliases only for employees the current route has already scoped."""
    rows = list(employees or [])
    ids = [employee.id for employee in rows]
    name_aliases = _alias_text_map(EmployeeNameAlias, 'employee_id', ids)
    code_aliases = _alias_text_map(TicketEmployeeCodeAlias, 'employee_id', ids)
    return {
        employee.id: ' '.join([*name_aliases.get(employee.id, []), *code_aliases.get(employee.id, [])])
        for employee in rows
    }


def _movement_search_text_map(movements):
    """Build searchable identity/location text for a scoped movement worklist."""
    rows = list(movements or [])
    employees = {movement.employee.id: movement.employee for movement in rows if movement.employee}
    branches = {}
    governorates = {}
    for movement in rows:
        employee = movement.employee
        if employee and employee.branch:
            branches[employee.branch.id] = employee.branch
            if employee.branch.governorate:
                governorates[employee.branch.governorate.id] = employee.branch.governorate
        destination = getattr(movement, 'destination', None)
        if destination:
            branches[destination.id] = destination
            if destination.governorate:
                governorates[destination.governorate.id] = destination.governorate
    name_aliases = _alias_text_map(EmployeeNameAlias, 'employee_id', employees.keys())
    code_aliases = _alias_text_map(TicketEmployeeCodeAlias, 'employee_id', employees.keys())
    branch_aliases = _alias_text_map(BranchNameAlias, 'branch_id', branches.keys())
    gov_aliases = _alias_text_map(GovernorateNameAlias, 'governorate_id', governorates.keys())
    result = {}
    for movement in rows:
        employee = movement.employee
        parts = []
        if employee:
            parts.extend([employee.full_name or '', employee.job_code or '', employee.employee_code or '', employee.job_title or ''])
            parts.extend(name_aliases.get(employee.id, []))
            parts.extend(code_aliases.get(employee.id, []))
            if employee.branch:
                branch = employee.branch
                parts.extend([branch.name or '', branch.code or '', *branch_aliases.get(branch.id, [])])
                if branch.governorate:
                    parts.extend([branch.governorate.name or '', *gov_aliases.get(branch.governorate.id, [])])
        destination = getattr(movement, 'destination', None)
        if destination:
            parts.extend([destination.name or '', destination.code or '', *branch_aliases.get(destination.id, [])])
            if destination.governorate:
                parts.extend([destination.governorate.name or '', *gov_aliases.get(destination.governorate.id, [])])
        result[movement.id] = ' '.join(str(part) for part in parts if part)
    return result
