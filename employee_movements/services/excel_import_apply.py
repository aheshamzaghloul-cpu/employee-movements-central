"""Validation and persistence helpers for selected Excel-import changes.

The request/blueprint layer remains responsible for role checks, session-token
validation, review-file ownership, transaction commit/rollback and audit logs.
This module centralizes apply-time ORM validation and entity mutations so those
rules can be tested and maintained independently from HTTP request handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping, Sequence

from sqlalchemy import func

from .identity_locks import lock_entity_identity_writes
from .entity_integrity import (
    branch_name_conflict,
    governorate_name_conflict,
    normalize_branch_code_key,
)
from .entity_matching import normalize_alias_key


def validate_selected_excel_import_changes(
    kind: str,
    selected_adds: Sequence[Mapping[str, Any]],
    selected_updates: Sequence[Mapping[str, Any]],
    selection_plan: Any,
    *,
    session: Any,
    Branch: Any,
    Employee: Any,
    Governorate: Any,
    TicketEmployeeCodeAlias: Any,
    EmployeeNameAlias: Any,
    excel_key: Callable[[Any], str],
    normalize_job_code: Callable[[Any], str],
    job_code_lookup_variants: Callable[[Any], set[str]],
    BranchNameAlias: Any = None,
    GovernorateNameAlias: Any = None,
) -> None:
    """Revalidate selected actions and detect cross-row/database collisions.

    The preview manifest is untrusted and may be stale. This function performs
    no mutations; it must run before apply helpers and before the caller commits.
    Invalid or conflicting plans raise ``ValueError`` for the route to roll back.
    """
    # Acquire the same global entity-identity gate used by manual catalog
    # routes and confirmed assistant plans. This serializes collision checks for
    # employees, branches, and governorates on PostgreSQL; database constraints
    # and validation remain necessary for writers outside this application.
    if kind in {'employees', 'branches', 'governorates'} and (selected_adds or selected_updates):
        lock_entity_identity_writes(session)

    # Lock all existing targets and referenced branch/governorate rows in a
    # stable table/id order before checking preview values. On PostgreSQL this
    # prevents another transaction from changing a reviewed record between the
    # stale-preview check and this import's commit. SQLite may ignore row locks;
    # that concurrency behavior remains a deployment-time verification item.
    lock_requests = {}
    for action in selected_updates:
        action_type = action.get('type')
        if action_type == 'branch':
            model = Branch
            record_id = action.get('id')
        elif action_type == 'employee':
            model = Employee
            record_id = action.get('id')
        else:
            continue
        normalized_record_id = int(record_id)
        lock_requests[(model.__tablename__, normalized_record_id)] = (model, normalized_record_id)
        if action_type == 'branch':
            # Serialize Excel branch-code/name changes with additions and other
            # branch updates for the same governorate on PostgreSQL. Preview
            # collision checks alone cannot reserve a name during approval.
            scope_branch = session.get(Branch, normalized_record_id)
            scope_governorate_id = getattr(scope_branch, 'governorate_id', None)
            if scope_governorate_id is not None:
                scope_governorate_id = int(scope_governorate_id)
                lock_requests[(Governorate.__tablename__, scope_governorate_id)] = (
                    Governorate, scope_governorate_id
                )
        if action_type == 'employee' and 'branch_id' in selection_plan.selected_fields(action):
            new_branch_id = (action.get('changes') or {}).get('branch_id', {}).get('new')
            try:
                new_branch_id = int(new_branch_id)
            except (TypeError, ValueError):
                raise ValueError('Excel employee update contains an invalid branch reference')
            lock_requests[(Branch.__tablename__, new_branch_id)] = (Branch, new_branch_id)
        if kind == 'employees' and action_type == 'employee':
            branch_identity = action.get('branch_identity')
            if not isinstance(branch_identity, dict):
                raise ValueError('Excel employee review is missing its branch identity snapshot')
            try:
                source_branch_id = int(branch_identity.get('branch_id'))
                source_governorate_id = int(branch_identity.get('governorate_id'))
            except (TypeError, ValueError):
                raise ValueError('Excel employee review contains an invalid branch identity snapshot')
            lock_requests[(Branch.__tablename__, source_branch_id)] = (Branch, source_branch_id)
            lock_requests[(Governorate.__tablename__, source_governorate_id)] = (Governorate, source_governorate_id)
    for action in selected_adds:
        if action.get('type') == 'new_branch':
            try:
                ref_id = int(action.get('governorate_id'))
            except (TypeError, ValueError):
                raise ValueError('Excel branch import contains an invalid governorate reference')
            lock_requests[(Governorate.__tablename__, ref_id)] = (Governorate, ref_id)
        elif action.get('type') == 'new_employee':
            try:
                ref_id = int(action.get('branch_id'))
            except (TypeError, ValueError):
                raise ValueError('Excel employee import contains an invalid branch reference')
            lock_requests[(Branch.__tablename__, ref_id)] = (Branch, ref_id)
            branch_identity = action.get('branch_identity')
            if not isinstance(branch_identity, dict):
                raise ValueError('Excel employee addition is missing its branch identity snapshot')
            try:
                source_branch_id = int(branch_identity.get('branch_id'))
                source_governorate_id = int(branch_identity.get('governorate_id'))
            except (TypeError, ValueError):
                raise ValueError('Excel employee addition contains an invalid branch identity snapshot')
            if source_branch_id != ref_id:
                raise ValueError('Excel employee addition branch references do not agree')
            lock_requests[(Governorate.__tablename__, source_governorate_id)] = (Governorate, source_governorate_id)
    locked_records = {}
    for key, (model, record_id) in sorted(lock_requests.items(), key=lambda item: item[0]):
        locked_records[(model, record_id)] = (
            session.query(model).filter(model.id == record_id).populate_existing().with_for_update().one_or_none()
        )

    if kind == 'governorates' and selected_adds:
        # Re-check all selected additions as one final set at approval time.
        # The preview is not a reservation, and a duplicate found here must
        # abort the batch instead of being silently converted to a skipped row.
        existing_name_keys = set()
        existing_exact_keys = set()
        for (name,) in Governorate.query.with_entities(Governorate.name).all():
            name_text = str(name or '').strip()
            if name_text:
                existing_exact_keys.add(name_text.casefold())
                key = excel_key(name_text)
                if key:
                    existing_name_keys.add(key)
        if GovernorateNameAlias is not None:
            aliases = GovernorateNameAlias.query.with_entities(
                GovernorateNameAlias.alias_text
            ).join(
                Governorate, Governorate.id == GovernorateNameAlias.governorate_id
            ).filter(Governorate.is_active == True).all()
            existing_name_keys.update(
                key for (alias_text,) in aliases if (key := excel_key(alias_text))
            )
        desired_name_keys = set()
        desired_exact_keys = set()
        for action in selected_adds:
            if action.get('type') != 'new_governorate':
                raise ValueError('Unexpected action type in selected governorate import')
            name = str((action.get('values') or {}).get('name') or '').strip()
            normalized_name = excel_key(name)
            exact_name = name.casefold()
            if not name or not normalized_name:
                raise ValueError('Selected Excel governorate has an invalid name')
            if governorate_name_conflict(name):
                raise ValueError('Selected Excel governorate conflicts with a canonical name or confirmed alias')
            if (
                normalized_name in existing_name_keys
                or exact_name in existing_exact_keys
                or normalized_name in desired_name_keys
                or exact_name in desired_exact_keys
            ):
                raise ValueError('Selected Excel rows contain duplicate or conflicting governorate names')
            desired_name_keys.add(normalized_name)
            desired_exact_keys.add(exact_name)

    def _locked(model, record_id):
        try:
            normalized_id = int(record_id)
        except (TypeError, ValueError):
            return None
        return locked_records.get((model, normalized_id))

    branch_identity_catalog = None
    branch_alias_keys = None
    governorate_alias_keys = None
    governorate_name_candidates = None

    def _load_branch_identity_catalog():
        nonlocal branch_identity_catalog, branch_alias_keys, governorate_alias_keys, governorate_name_candidates
        if branch_identity_catalog is not None:
            return
        rows = Branch.query.join(
            Governorate, Branch.governorate_id == Governorate.id
        ).filter(Governorate.is_active == True).with_entities(
            Branch.id, Branch.governorate_id, Branch.code, Branch.name,
            Branch.is_active, Governorate.name, Governorate.is_active,
        ).yield_per(2000)
        branch_identity_catalog = {
            int(branch_id): {
                'id': int(branch_id),
                'governorate_id': int(governorate_id),
                'code': code or '',
                'name': name or '',
                'is_active': bool(branch_active),
                'governorate_name': governorate_name or '',
                'governorate_active': bool(governorate_active),
            }
            for branch_id, governorate_id, code, name, branch_active, governorate_name, governorate_active in rows
        }
        branch_alias_keys = {}
        if BranchNameAlias is not None:
            for branch_id, alias_text in BranchNameAlias.query.join(
                Branch, Branch.id == BranchNameAlias.branch_id
            ).join(Governorate, Branch.governorate_id == Governorate.id).filter(
                Branch.is_active == True, Governorate.is_active == True
            ).with_entities(BranchNameAlias.branch_id, BranchNameAlias.alias_text).yield_per(2000):
                branch_alias_keys.setdefault(int(branch_id), set()).add(excel_key(alias_text))
        governorate_alias_keys = {}
        governorate_name_candidates = {}
        active_governorates = Governorate.query.filter_by(is_active=True).with_entities(
            Governorate.id, Governorate.name
        ).yield_per(2000)
        active_governorate_ids = set()
        for governorate_id, governorate_name in active_governorates:
            normalized_id = int(governorate_id)
            active_governorate_ids.add(normalized_id)
            key = excel_key(governorate_name)
            if key:
                governorate_name_candidates.setdefault(key, set()).add(normalized_id)
        if GovernorateNameAlias is not None:
            for governorate_id, alias_text in GovernorateNameAlias.query.with_entities(
                GovernorateNameAlias.governorate_id, GovernorateNameAlias.alias_text
            ).yield_per(2000):
                normalized_id = int(governorate_id)
                alias_key = excel_key(alias_text)
                governorate_alias_keys.setdefault(normalized_id, set()).add(alias_key)
                if alias_key and normalized_id in active_governorate_ids:
                    # Ignore aliases owned by inactive governorates, matching
                    # the importer's active-scope catalogue.
                    governorate_name_candidates.setdefault(alias_key, set()).add(normalized_id)

    def _validate_branch_identity_snapshot(action):
        # Reject a staged employee row if its reviewed branch evidence is stale.
        snapshot = action.get('branch_identity')
        if not isinstance(snapshot, dict):
            raise ValueError('Excel employee review is missing its branch identity snapshot')
        try:
            branch_id = int(snapshot.get('branch_id'))
            governorate_id = int(snapshot.get('governorate_id'))
        except (TypeError, ValueError):
            raise ValueError('Excel employee review contains an invalid branch identity snapshot')
        if branch_id <= 0 or governorate_id <= 0:
            raise ValueError('Excel employee review contains an invalid branch identity snapshot')
        branch = _locked(Branch, branch_id)
        governorate = _locked(Governorate, governorate_id)
        if (
            not branch or not governorate
            or int(getattr(branch, 'governorate_id', 0) or 0) != governorate_id
            or not branch.is_active or not governorate.is_active
        ):
            raise ValueError('Excel employee review references a branch that changed or became inactive')

        _load_branch_identity_catalog()
        target = branch_identity_catalog.get(branch_id)
        if (
            not target or target['governorate_id'] != governorate_id
            or not target['is_active'] or not target['governorate_active']
        ):
            raise ValueError('Excel employee review references a branch that changed or became inactive')

        source_code_key = normalize_branch_code_key(snapshot.get('branch_code'))
        source_name_key = excel_key(snapshot.get('branch_name'))
        source_governorate_key = excel_key(snapshot.get('governorate'))

        def _governorate_label_matches(candidate_governorate_id):
            if not source_governorate_key:
                return True
            candidates = [
                item for item in branch_identity_catalog.values()
                if item['governorate_id'] == int(candidate_governorate_id)
            ]
            candidate_name = candidates[0]['governorate_name'] if candidates else ''
            return bool(
                candidate_name
                and (
                    excel_key(candidate_name) == source_governorate_key
                    or source_governorate_key in governorate_alias_keys.get(int(candidate_governorate_id), set())
                )
            )

        def _branch_label_matches(candidate):
            if not source_name_key:
                return True
            return bool(
                excel_key(candidate.get('name')) == source_name_key
                or source_name_key in branch_alias_keys.get(int(candidate['id']), set())
            )

        # Labels supplied with a code must still describe the same branch.
        if source_governorate_key and not _governorate_label_matches(governorate_id):
            raise ValueError('Excel employee import governorate identity changed after preview')
        if source_name_key and not _branch_label_matches(target):
            raise ValueError('Excel employee import branch name or confirmed alias changed after preview')

        if source_code_key:
            code_candidates = [
                candidate for candidate in branch_identity_catalog.values()
                if normalize_branch_code_key(candidate['code']) == source_code_key
            ]
            if not code_candidates or all(candidate['id'] != branch_id for candidate in code_candidates):
                raise ValueError('Excel employee import branch code changed or no longer identifies the reviewed branch')
            counts_by_governorate = {}
            for candidate in code_candidates:
                counts_by_governorate[candidate['governorate_id']] = counts_by_governorate.get(candidate['governorate_id'], 0) + 1
            if any(count > 1 for count in counts_by_governorate.values()):
                raise ValueError('Excel employee import branch code is no longer unique within its governorate')
            if len(code_candidates) == 1:
                resolved = code_candidates[0]
            else:
                scoped = [candidate for candidate in code_candidates
                          if _governorate_label_matches(candidate['governorate_id'])]
                if len(scoped) == 1:
                    resolved = scoped[0]
                else:
                    named = [candidate for candidate in code_candidates if _branch_label_matches(candidate)]
                    resolved = named[0] if len(named) == 1 else None
            if not resolved or resolved['id'] != branch_id:
                raise ValueError('Excel employee import branch code no longer resolves to the reviewed branch')
        else:
            if not source_name_key:
                raise ValueError('Excel employee import needs a branch code or branch name')
            if source_governorate_key:
                matched_governorates = governorate_name_candidates.get(source_governorate_key, set())
                if len(matched_governorates) != 1 or governorate_id not in matched_governorates:
                    raise ValueError('Excel employee import governorate name is missing, ambiguous, or changed after preview')
            candidates = [candidate for candidate in branch_identity_catalog.values()
                          if candidate['is_active'] and candidate['governorate_active']
                          and _branch_label_matches(candidate)
                          and (not source_governorate_key or candidate['governorate_id'] == governorate_id)]
            if len(candidates) != 1 or candidates[0]['id'] != branch_id:
                raise ValueError('Excel employee import branch name no longer uniquely identifies the reviewed branch')

        return branch_id

    def _validate_employee_identity_snapshot(action, employee):
        # Reconfirm the code/email/name evidence that bound a row to an employee.
        snapshot = action.get('employee_identity')
        if not isinstance(snapshot, dict) or snapshot.get('employee_id') != employee.id:
            raise ValueError('Excel employee review is missing a valid employee identity snapshot')
        try:
            reviewed_branch_id = int(snapshot.get('reviewed_branch_id'))
        except (TypeError, ValueError):
            raise ValueError('Excel employee review is missing its reviewed branch identity')
        if (
            int(employee.branch_id or 0) != reviewed_branch_id
            or (employee.full_name or '') != str(snapshot.get('reviewed_full_name') or '')
            or (employee.email or '') != str(snapshot.get('reviewed_email') or '')
            or (employee.job_code or '') != str(snapshot.get('reviewed_job_code') or '')
        ):
            raise ValueError('Existing employee identity fields changed after Excel preview; review the workbook again')
        source_code = normalize_job_code(snapshot.get('job_code'))
        source_variants = job_code_lookup_variants(source_code)
        if not source_variants:
            raise ValueError('Excel employee review contains an invalid personnel-code identity')
        current_variants = job_code_lookup_variants(normalize_job_code(employee.job_code))
        alias_variants = set()
        for (alias_text,) in TicketEmployeeCodeAlias.query.with_entities(
            TicketEmployeeCodeAlias.alias_text
        ).filter(TicketEmployeeCodeAlias.employee_id == employee.id).all():
            alias_variants.update(job_code_lookup_variants(alias_text))
        if not source_variants.intersection(current_variants | alias_variants):
            raise ValueError('Excel employee personnel-code identity changed after preview')

        # A code must not have become shared through another employee or a
        # newly added confirmed alias between the two stages.
        for other_id, other_code in Employee.query.with_entities(Employee.id, Employee.job_code).yield_per(2000):
            if other_id == employee.id or not other_code:
                continue
            if source_variants.intersection(job_code_lookup_variants(normalize_job_code(other_code))):
                raise ValueError('Excel employee personnel code now conflicts with another employee')
        for alias_employee_id, alias_text in TicketEmployeeCodeAlias.query.with_entities(
            TicketEmployeeCodeAlias.employee_id, TicketEmployeeCodeAlias.alias_text
        ).yield_per(2000):
            if alias_employee_id != employee.id and source_variants.intersection(job_code_lookup_variants(alias_text)):
                raise ValueError('Excel employee personnel code now conflicts with another confirmed alias')

        source_email_key = str(snapshot.get('email_key') or '')
        if snapshot.get('email_matched') is True:
            if not source_email_key or excel_key(employee.email) != source_email_key:
                raise ValueError('Excel employee email identity changed after preview')
            for other_id, email in Employee.query.with_entities(Employee.id, Employee.email).yield_per(2000):
                if other_id != employee.id and email and excel_key(email) == source_email_key:
                    raise ValueError('Excel employee email identity now conflicts with another record')

        if snapshot.get('name_matched') is True:
            try:
                branch_id = int((action.get('branch_identity') or {}).get('branch_id'))
            except (TypeError, ValueError):
                raise ValueError('Excel employee name identity has an invalid branch reference')
            source_name_key = str(snapshot.get('name_key') or '')
            if not source_name_key or employee.branch_id != branch_id:
                raise ValueError('Excel employee branch/name identity changed after preview')
            current_name_matches = excel_key(employee.full_name) == source_name_key
            if not current_name_matches:
                current_name_matches = any(
                    excel_key(alias_text) == source_name_key
                    for (alias_text,) in EmployeeNameAlias.query.with_entities(
                        EmployeeNameAlias.alias_text
                    ).filter(EmployeeNameAlias.employee_id == employee.id).all()
                )
            if not current_name_matches:
                raise ValueError('Excel employee canonical name or confirmed alias changed after preview')
            for other_id, full_name in Employee.query.with_entities(
                Employee.id, Employee.full_name
            ).filter(Employee.branch_id == branch_id).yield_per(2000):
                if other_id != employee.id and excel_key(full_name) == source_name_key:
                    raise ValueError('Excel employee name now conflicts with another employee in the branch')
            for other_id, alias_text in EmployeeNameAlias.query.join(
                Employee, Employee.id == EmployeeNameAlias.employee_id
            ).with_entities(EmployeeNameAlias.employee_id, EmployeeNameAlias.alias_text).filter(
                Employee.branch_id == branch_id
            ).yield_per(2000):
                if other_id != employee.id and excel_key(alias_text) == source_name_key:
                    raise ValueError('Excel employee name now conflicts with another confirmed alias')

    def _same_review_value(field, actual, expected):
        if field == 'branch_id':
            try:
                return int(actual) == int(expected)
            except (TypeError, ValueError):
                return False
        if field == 'hire_date':
            actual = actual.isoformat() if actual else ''
        actual_text = '' if actual is None else str(actual)
        expected_text = '' if expected is None else str(expected)
        return actual_text == expected_text

    def _assert_reviewed_old_value(action, model, record, field):
        changes = action.get('changes') or {}
        change = changes.get(field)
        if not isinstance(change, dict) or 'old' not in change or 'new' not in change:
            raise ValueError('Invalid Excel review change structure')
        if model is Branch:
            actual = getattr(record, field, None)
            if field == 'code':
                actual = actual or '—'
        elif model is Employee:
            actual = getattr(record, field, None)
            if field == 'email':
                actual = actual or ''
            elif field in {'job_title', 'job_code', 'company_phone', 'personal_phone'}:
                actual = actual or ''
        else:
            raise ValueError('Unsupported Excel review target type')
        if not _same_review_value(field, actual, change['old']):
            raise ValueError(
                'An existing record changed after Excel preview; re-upload and review the workbook again'
            )

    # Revalidate every database reference and every selected field's old value
    # before any mutation. Preview-time identity and change proposals are stale
    # candidates, not authorization to overwrite newer data.
    for action in selected_adds + selected_updates:
        if not isinstance(action, dict) or not isinstance(action.get('type'), str):
            raise ValueError('Invalid Excel review action')
        action_type = action['type']
        if kind == 'employees' and action_type == 'new_employee':
            _validate_branch_identity_snapshot(action)
        elif kind == 'employees' and action_type == 'employee':
            source_branch_id = _validate_branch_identity_snapshot(action)
            changes = action.get('changes') or {}
            if 'branch_id' in changes:
                try:
                    proposed_branch_id = int(changes.get('branch_id', {}).get('new'))
                except (TypeError, ValueError):
                    raise ValueError('Excel employee update contains an invalid branch reference')
                if proposed_branch_id != source_branch_id:
                    raise ValueError('Excel employee update branch does not match the reviewed workbook identity')
            current_employee = _locked(Employee, action.get('id'))
            if not current_employee or current_employee.deleted_at is not None:
                raise ValueError('Excel employee update references a missing or deleted employee')
            identity = action.get('employee_identity')
            if not isinstance(identity, dict):
                raise ValueError('Excel employee review is missing a valid employee identity snapshot')
            if 'job_code' in changes and normalize_job_code(changes['job_code'].get('new')) != normalize_job_code(identity.get('job_code')):
                raise ValueError('Excel employee personnel code change does not match the reviewed workbook row')
            if 'email' in changes and excel_key(changes['email'].get('new')) != str(identity.get('email_key') or ''):
                raise ValueError('Excel employee email change does not match the reviewed workbook row')
            if 'full_name' in changes and excel_key(changes['full_name'].get('new')) != str(identity.get('name_key') or ''):
                raise ValueError('Excel employee name change does not match the reviewed workbook row')
            _validate_employee_identity_snapshot(action, current_employee)
        if kind == 'branches' and action_type == 'new_branch':
            governorate_id = action.get('governorate_id')
            governorate = _locked(Governorate, governorate_id) if isinstance(governorate_id, int) else None
            if not governorate or not governorate.is_active:
                raise ValueError('Excel branch import references a missing or inactive governorate')
        elif kind == 'branches' and action_type == 'branch':
            branch = _locked(Branch, action.get('id'))
            if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
                raise ValueError('Excel branch update references a missing or inactive branch')
            for field in selection_plan.selected_fields(action):
                _assert_reviewed_old_value(action, Branch, branch, field)
        elif kind == 'employees' and action_type == 'new_employee':
            branch_id = action.get('branch_id')
            branch = _locked(Branch, branch_id) if isinstance(branch_id, int) else None
            if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
                raise ValueError('Excel employee import references a missing or inactive branch')
            values = action.get('values') or {}
            if not str(values.get('job_code') or '').strip():
                raise ValueError('Excel employee import is missing a personnel code')
        elif kind == 'employees' and action_type == 'employee':
            employee = _locked(Employee, action.get('id'))
            if not employee or employee.deleted_at is not None:
                raise ValueError('Excel employee update references a missing or deleted employee')
            for field in selection_plan.selected_fields(action):
                _assert_reviewed_old_value(action, Employee, employee, field)
            fields = selection_plan.selected_fields(action)
            if 'branch_id' in fields:
                try:
                    branch_id = int(action['changes']['branch_id']['new'])
                except (TypeError, ValueError, KeyError):
                    raise ValueError('Excel employee update contains an invalid branch reference')
                branch = _locked(Branch, branch_id)
                if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
                    raise ValueError('Excel employee update references a missing or inactive branch')

    # Check job-code collisions in one streaming pass rather than issuing a
    # database query for every Excel row. Legacy 200-prefix variants and
    # confirmed aliases count as the same identity and must remain unique.
    desired_codes = []
    if kind == 'employees':
        for action in selected_adds:
            if action.get('type') == 'new_employee':
                values = action.get('values') or {}
                raw_code = values.get('job_code') or ''
                desired_codes.append((None, normalize_job_code(raw_code), action.get('row')))
        for action in selected_updates:
            if action.get('type') == 'employee' and 'job_code' in selection_plan.selected_fields(action):
                raw_code = (action.get('changes') or {}).get('job_code', {}).get('new', '')
                desired_codes.append((action.get('id'), normalize_job_code(raw_code), action.get('row')))

    target_variants = {}
    for target_id, raw_code, row_no in desired_codes:
        variants = job_code_lookup_variants(raw_code)
        if not variants:
            raise ValueError('Excel employee import contains an empty or invalid personnel code')
        owner = (target_id, row_no)
        for variant in variants:
            previous = target_variants.get(variant)
            if previous is not None and previous != owner:
                raise ValueError('Selected Excel rows contain duplicate or conflicting personnel codes')
            target_variants[variant] = owner

    desired_employee_names = {}
    if kind == 'employees':
        def _register_employee_name(target_id, branch_id, name, row_no):
            name_key = (branch_id, excel_key(name))
            if not branch_id or not name_key[1]:
                raise ValueError('Selected Excel employee has a missing branch or name')
            owner = (target_id, row_no)
            previous = desired_employee_names.get(name_key)
            if previous is not None and previous != owner:
                raise ValueError('Selected Excel rows contain duplicate employee names in one branch')
            desired_employee_names[name_key] = owner

        for action in selected_adds:
            if action.get('type') == 'new_employee':
                values = action.get('values') or {}
                _register_employee_name(None, action.get('branch_id'), values.get('name'), action.get('row'))
        for action in selected_updates:
            if action.get('type') != 'employee':
                continue
            fields = selection_plan.selected_fields(action)
            if not fields.intersection({'full_name', 'branch_id'}):
                continue
            employee = _locked(Employee, action.get('id'))
            if not employee or employee.deleted_at is not None:
                raise ValueError('Excel employee name update references a missing or deleted employee')
            changes = action.get('changes') or {}
            target_name = changes.get('full_name', {}).get('new') if 'full_name' in fields else employee.full_name
            target_branch_id = changes.get('branch_id', {}).get('new') if 'branch_id' in fields else employee.branch_id
            try:
                target_branch_id = int(target_branch_id)
            except (TypeError, ValueError):
                raise ValueError('Excel employee update contains an invalid branch reference')
            _register_employee_name(employee.id, target_branch_id, target_name, action.get('row'))

    # Check identity collisions in one streaming pass rather than issuing a
    # query for each Excel row. Legacy 200-prefix variants and confirmed
    # aliases remain part of the same identity invariant.
    if target_variants or desired_employee_names:
        scan_query = Employee.query.with_entities(
            Employee.id, Employee.job_code, Employee.branch_id, Employee.full_name
        ).yield_per(2000)
        for employee_id, existing_code, branch_id, full_name in scan_query:
            if target_variants and existing_code:
                variants = job_code_lookup_variants(normalize_job_code(existing_code))
                for variant in variants.intersection(target_variants):
                    target_id = target_variants[variant][0]
                    if target_id != employee_id:
                        raise ValueError('Excel employee import conflicts with an existing personnel code')
            if desired_employee_names:
                owner = desired_employee_names.get((branch_id, excel_key(full_name)))
                if owner is not None and owner[0] != employee_id:
                    raise ValueError('Excel employee import conflicts with an existing employee name in the same branch')

        if target_variants:
            # Alias normalized_alias is generated for ticket OCR and may collapse
            # O/0 or I/1. For Excel's authoritative codes, compare the confirmed
            # alias_text using the strict normalizer supplied by the import route.
            for alias_employee_id, alias_text in TicketEmployeeCodeAlias.query.with_entities(
                TicketEmployeeCodeAlias.employee_id, TicketEmployeeCodeAlias.alias_text
            ).yield_per(2000):
                for variant in job_code_lookup_variants(alias_text).intersection(target_variants):
                    target = target_variants.get(variant)
                    if not target or target[0] != alias_employee_id:
                        raise ValueError('Excel employee import conflicts with an existing confirmed personnel-code alias')

        if desired_employee_names:
            target_branch_ids = {branch_id for branch_id, _ in desired_employee_names}
            for alias_employee_id, branch_id, alias_text in EmployeeNameAlias.query.join(
                Employee, Employee.id == EmployeeNameAlias.employee_id
            ).with_entities(
                EmployeeNameAlias.employee_id, Employee.branch_id, EmployeeNameAlias.alias_text
            ).filter(Employee.branch_id.in_(target_branch_ids)).yield_per(2000):
                owner = desired_employee_names.get((branch_id, excel_key(alias_text)))
                if owner is not None and owner[0] != alias_employee_id:
                    raise ValueError('Excel employee import conflicts with a confirmed employee-name alias')

    email_targets = {}
    email_row_targets = {}
    for action in selected_adds:
        if action.get('type') == 'new_employee':
            email = str((action.get('values') or {}).get('email') or '').strip().casefold()
            if email:
                email_row_targets.setdefault(email, []).append((None, action.get('row')))
    for action in selected_updates:
        if action.get('type') == 'employee' and 'email' in selection_plan.selected_fields(action):
            email = str((action.get('changes') or {}).get('email', {}).get('new') or '').strip().casefold()
            if email:
                email_row_targets.setdefault(email, []).append((action.get('id'), action.get('row')))
    for email, owners in email_row_targets.items():
        if len(set(owners)) > 1:
            raise ValueError('Selected Excel rows contain duplicate email addresses')
        email_targets[email] = owners[0][0]
    email_keys = list(email_targets)
    for offset in range(0, len(email_keys), 500):
        chunk = email_keys[offset:offset + 500]
        existing_emails = Employee.query.with_entities(
            Employee.id, func.lower(func.trim(Employee.email))
        ).filter(
            Employee.email.isnot(None),
            func.lower(func.trim(Employee.email)).in_(chunk),
        ).all()
        for employee_id, email in existing_emails:
            if email_targets.get(email) != employee_id:
                raise ValueError('Excel employee import conflicts with an existing email address')

    # Branch codes are unique within their governorate for import purposes.
    # Validate selected additions and selected code changes together, so a
    # stale preview cannot create two branches with the same code.
    desired_branch_codes = {}
    if kind == 'branches':
        desired = []
        for action in selected_adds:
            if action.get('type') == 'new_branch':
                desired.append((None, action.get('governorate_id'), (action.get('values') or {}).get('code', ''), action.get('row')))
        for action in selected_updates:
            if action.get('type') == 'branch' and 'code' in selection_plan.selected_fields(action):
                branch = _locked(Branch, action.get('id'))
                desired.append((action.get('id'), branch.governorate_id if branch else None,
                                (action.get('changes') or {}).get('code', {}).get('new', ''), action.get('row')))
        for desired_item in desired:
            target_id, governorate_id, code = desired_item[:3]
            row_no = desired_item[3] if len(desired_item) > 3 else None
            key = (governorate_id, normalize_branch_code_key(code))
            if not governorate_id or not key[1]:
                raise ValueError('Selected Excel branch has a missing governorate or branch code')
            owner = (target_id, row_no)
            previous = desired_branch_codes.get(key, 'not-seen')
            if previous != 'not-seen' and previous != owner:
                raise ValueError('Selected Excel rows contain duplicate branch codes in one governorate')
            desired_branch_codes[key] = owner
        if desired_branch_codes:
            governorate_ids = {key[0] for key in desired_branch_codes}
            for existing_id, governorate_id, code in (
                Branch.query.with_entities(Branch.id, Branch.governorate_id, Branch.code)
                .filter(Branch.governorate_id.in_(governorate_ids), Branch.code.isnot(None))
                .yield_per(2000)
            ):
                key = (governorate_id, normalize_branch_code_key(code))
                owner = desired_branch_codes.get(key, 'not-seen')
                target_id = owner[0] if owner != 'not-seen' else 'not-seen'
                if target_id != 'not-seen' and target_id != existing_id:
                    raise ValueError('Excel branch import conflicts with an existing branch code')

        # Repeat branch-name collision checks at approval time. Preview is not
        # authoritative because the catalogue may have changed after review.
        # Build a final-state overlay for selected renames so duplicate checks
        # account for the whole selected batch rather than only one row at a time.
        branch_name_updates = {}
        affected_name_keys = set()
        desired_branch_names = {}
        selected_new_branch_name_keys = []

        def _register_desired_branch_name(governorate_id, name, target_id, row_no):
            name_key = normalize_alias_key(name)
            if not governorate_id or not name_key:
                raise ValueError('Selected Excel branch has a missing governorate or branch name')
            key = (governorate_id, name_key)
            owner = (target_id, row_no)
            previous = desired_branch_names.get(key)
            if previous is not None and previous != owner:
                raise ValueError('Selected Excel rows contain duplicate branch names in one governorate')
            desired_branch_names[key] = owner
            affected_name_keys.add(key)

        for action in selected_adds:
            if action.get('type') != 'new_branch':
                continue
            values = action.get('values') or {}
            _register_desired_branch_name(
                action.get('governorate_id'), values.get('name'), None, action.get('row')
            )
            selected_new_branch_name_keys.append(
                (action.get('governorate_id'), normalize_alias_key(values.get('name')))
            )

        for action in selected_updates:
            if action.get('type') != 'branch' or 'name' not in selection_plan.selected_fields(action):
                continue
            branch = _locked(Branch, action.get('id'))
            if not branch:
                raise ValueError('Excel branch name update references a missing branch')
            changes = action.get('changes') or {}
            old_key = (branch.governorate_id, normalize_alias_key(branch.name))
            if old_key[1]:
                affected_name_keys.add(old_key)
            new_name = changes.get('name', {}).get('new')
            branch_name_updates[branch.id] = new_name
            _register_desired_branch_name(branch.governorate_id, new_name, branch.id, action.get('row'))

        if affected_name_keys:
            final_name_owners = {}
            for existing_id, governorate_id, existing_name in (
                Branch.query.with_entities(Branch.id, Branch.governorate_id, Branch.name).yield_per(2000)
            ):
                final_name = branch_name_updates.get(existing_id, existing_name)
                key = (governorate_id, normalize_alias_key(final_name))
                if key[1]:
                    final_name_owners.setdefault(key, []).append(existing_id)
            for key in affected_name_keys:
                existing_count = len(final_name_owners.get(key, ()))
                selected_add_count = sum(1 for candidate_key in selected_new_branch_name_keys if candidate_key == key)
                if existing_count + selected_add_count > 1:
                    raise ValueError('Excel branch import conflicts with an existing branch name in the same governorate')

            # A confirmed alias can make a supposedly new canonical name point
            # to another branch. Check that catalogue too, not just canonical names.
            if BranchNameAlias is not None and desired_branch_names:
                for alias_branch_id, governorate_id, alias_text in (
                    BranchNameAlias.query.with_entities(
                        BranchNameAlias.branch_id, Branch.governorate_id, BranchNameAlias.alias_text
                    ).join(Branch, Branch.id == BranchNameAlias.branch_id).yield_per(2000)
                ):
                    key = (governorate_id, normalize_alias_key(alias_text))
                    desired_owner = desired_branch_names.get(key)
                    if desired_owner is not None and desired_owner[0] != alias_branch_id:
                        raise ValueError('Excel branch import conflicts with a confirmed branch-name alias')

            # Use the same canonical/alias rule as manual edits and the assistant.
            # Ignore current canonical names of branches renamed in this batch so
            # a legitimate final-state rename is not rejected, but never ignore
            # aliases owned by those branches (aliases remain reserved).
            renamed_branch_ids = set(branch_name_updates)
            final_name_candidates = []
            for action in selected_adds:
                if action.get('type') == 'new_branch':
                    values = action.get('values') or {}
                    final_name_candidates.append((
                        values.get('name'), action.get('governorate_id'), None, action.get('row')
                    ))
            for action in selected_updates:
                if action.get('type') != 'branch' or 'name' not in selection_plan.selected_fields(action):
                    continue
                changes = action.get('changes') or {}
                branch = _locked(Branch, action.get('id'))
                if not branch:
                    raise ValueError('Excel branch name update references a missing branch')
                final_name_candidates.append((
                    changes.get('name', {}).get('new'), branch.governorate_id,
                    branch.id, action.get('row')
                ))
            for name, governorate_id, target_id, _row_no in final_name_candidates:
                conflict = branch_name_conflict(
                    name, governorate_id, exclude_id=target_id,
                    ignore_branch_ids=renamed_branch_ids,
                )
                if conflict:
                    raise ValueError('Excel branch import conflicts with a canonical branch name or confirmed alias')


@dataclass(frozen=True)
class ExcelImportApplyCounts:
    """Counts produced by the persistence phase, including skipped rows."""

    added: int
    updated: int
    skipped: int


def apply_selected_excel_import_changes(
    kind: str,
    actions: Iterable[Mapping[str, Any]],
    selection_plan: Any,
    initial_skipped: int,
    *,
    session: Any,
    Governorate: Any,
    GovernorateNameAlias: Any,
    Branch: Any,
    Employee: Any,
    excel_key: Callable[[Any], str],
) -> ExcelImportApplyCounts:
    """Apply selected additions/updates without committing the transaction.

    The caller owns transaction boundaries and audit logging. References and
    uniqueness constraints are expected to be revalidated first by
    :func:`validate_selected_excel_import_changes`.
    """
    if kind not in {"governorates", "branches", "employees"}:
        raise ValueError("Unknown Excel import kind")
    added = updated = 0
    skipped = initial_skipped
    if kind == 'governorates':
        # Final validation should already have rejected collisions. Keep a
        # persistence-time guard as a fail-closed invariant; never silently turn
        # an explicitly selected addition into a skip after approval.
        all_governorates = Governorate.query.all()
        existing_name_keys = {excel_key(governorate.name) for governorate in all_governorates}
        exact_name_keys = {str(governorate.name or '').strip().casefold() for governorate in all_governorates}
        for alias_text, in GovernorateNameAlias.query.with_entities(GovernorateNameAlias.alias_text).join(
            Governorate, Governorate.id == GovernorateNameAlias.governorate_id
        ).filter(Governorate.is_active == True):
            existing_name_keys.add(excel_key(alias_text))
        for a in actions:
            if a['type'] != 'new_governorate' or not selection_plan.is_selected_add(a):
                continue
            name = str((a.get('values') or {}).get('name') or '').strip()
            if not name:
                raise ValueError('Selected Excel governorate has an invalid name')
            normalized_name = excel_key(name)
            exact_name = name.casefold()
            if normalized_name in existing_name_keys or exact_name in exact_name_keys:
                raise ValueError('Selected Excel governorate conflicts with a name added or changed after validation')
            session.add(Governorate(name=name, is_active=True))
            existing_name_keys.add(normalized_name)
            exact_name_keys.add(exact_name)
            added += 1
    elif kind == 'branches':
        for a in actions:
            if a['type'] == 'new_branch' and selection_plan.is_selected_add(a):
                v = a['values']
                b = Branch(governorate_id=a['governorate_id'], name=v['name'], code=v['code'])
                session.add(b)
                session.flush()
                added += 1
            elif a['type'] == 'branch':
                if not selection_plan.selected_fields(a):
                    continue
                b = session.get(Branch, a['id'])
                if not b:
                    raise ValueError('Selected Excel branch update target disappeared before persistence')
                changed = False
                for f in ('name', 'code'):
                    if f in selection_plan.selected_fields(a):
                        setattr(b, f, a['changes'][f]['new'])
                        changed = True
                if changed:
                    updated += 1
    else:
        for a in actions:
            if a['type'] == 'new_employee' and selection_plan.is_selected_add(a):
                v = a['values']
                e = Employee(
                    employee_code=None,
                    email=(v.get('email') or '').strip() or None,
                    full_name=v['name'],
                    branch_id=a['branch_id'],
                    job_title=v['job_title'],
                    job_code=v['job_code'],
                    hire_date=datetime.fromisoformat(a['hire_date']).date(),
                    company_phone=v['company_phone'],
                    personal_phone=v['personal_phone'],
                )
                session.add(e)
                session.flush()
                added += 1
            elif a['type'] == 'employee':
                if not selection_plan.selected_fields(a):
                    continue
                e = session.get(Employee, a['id'])
                if not e or e.deleted_at is not None:
                    raise ValueError('Selected Excel employee update target disappeared or was deleted before persistence')
                changed = False
                for f in a['changes']:
                    if f not in selection_plan.selected_fields(a):
                        continue
                    new = a['changes'][f]['new']
                    if f == 'branch_id':
                        setattr(e, f, int(new))
                    elif f == 'hire_date':
                        setattr(e, f, datetime.fromisoformat(new).date())
                    elif f == 'email':
                        setattr(e, f, (str(new or '').strip() or None))
                    else:
                        setattr(e, f, new)
                    changed = True
                if changed:
                    updated += 1
    return ExcelImportApplyCounts(added=added, updated=updated, skipped=skipped)
