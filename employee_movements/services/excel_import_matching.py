"""Pure branch identity resolution rules for employee Excel imports.

Kept independent of Flask/SQLAlchemy so branch matching rules can be tested
without a live application or database.
"""


def resolve_employee_import_branch(
    branch_code,
    governorate_value,
    branch_name,
    *,
    branches_by_code,
    branches_by_name,
    govs,
    branch_cache,
    governorate_alias_keys_by_id,
    branch_alias_keys_by_id,
    normalize_key,
    normalize_code_key=None,
):
    """Return ``(branch, method)`` without guessing across conflicting identities.

    A supplied branch code is authoritative only when it resolves to one
    active branch (or can be disambiguated by confirmed labels) *and* every
    non-empty governorate/branch label agrees with that branch's canonical name
    or a recorded alias. Unknown supplied codes never fall back to name-only
    matching. Name-only fallback is reserved for workbooks with no branch code.
    """
    code_key = (normalize_code_key or normalize_key)(branch_code)
    gov_key = normalize_key(governorate_value)
    name_key = normalize_key(branch_name)

    def governorate_label_matches(candidate):
        if not gov_key:
            return True
        canonical = normalize_key(candidate.governorate.name if candidate.governorate else '')
        return (
            gov_key == canonical
            or gov_key in governorate_alias_keys_by_id.get(candidate.governorate_id, set())
        )

    def branch_label_matches(candidate):
        if not name_key:
            return True
        canonical = normalize_key(candidate.name)
        return name_key == canonical or name_key in branch_alias_keys_by_id.get(candidate.id, set())

    if code_key:
        code_matches = branches_by_code.get(code_key, [])
        if not code_matches:
            return None, 'unknown_code'
        # Branch codes may repeat across governorates, but a duplicate within
        # one governorate is a catalogue conflict and must never be guessed away
        # by a name label.
        counts_by_governorate = {}
        for branch in code_matches:
            counts_by_governorate[branch.governorate_id] = counts_by_governorate.get(branch.governorate_id, 0) + 1
        if any(count > 1 for count in counts_by_governorate.values()):
            return None, 'ambiguous_code'

        candidate = None
        if len(code_matches) == 1:
            candidate = code_matches[0]
        else:
            scoped = [branch for branch in code_matches if governorate_label_matches(branch)]
            if len(scoped) == 1:
                candidate = scoped[0]
            else:
                named = [branch for branch in code_matches if branch_label_matches(branch)]
                if len(named) == 1:
                    candidate = named[0]
        if candidate is None:
            return None, 'ambiguous_code'
        if (
            not getattr(candidate, 'is_active', True)
            or not getattr(candidate, 'governorate', None)
            or not getattr(candidate.governorate, 'is_active', True)
        ):
            return candidate, 'inactive_code'
        if not (governorate_label_matches(candidate) and branch_label_matches(candidate)):
            return candidate, 'code_label_mismatch'
        if len(code_matches) > 1:
            return candidate, 'code_disambiguated'
        return candidate, 'code'

    # A known governorate is part of the user's intended target; a supplied but unknown label is not silently overridden.
    # Legacy name matching is safe only if the input did not supply an unknown
    # code and any provided governorate is recognized by canonical name/alias.
    governorate_candidates = govs.get(gov_key)
    if isinstance(governorate_candidates, (list, tuple, set)):
        unique_governorates = {
            getattr(candidate, 'id', id(candidate)): candidate
            for candidate in governorate_candidates
        }
        if len(unique_governorates) > 1:
            return None, 'ambiguous_governorate'
        governorate = next(iter(unique_governorates.values()), None)
    else:
        # Backwards-compatible with callers that still provide a single record.
        governorate = governorate_candidates
    if not governorate:
        if gov_key:
            return None, 'governorate_not_found'
        name_matches = branches_by_name.get(name_key, []) if name_key else []
        if len(name_matches) == 1:
            return name_matches[0], 'unique_name_without_governorate'
        if len(name_matches) > 1:
            return None, 'ambiguous_name'
        return None, 'governorate_not_found'

    named = branch_cache.get((normalize_key(governorate.name), name_key))
    if named:
        # A name can be a canonical name for one branch and a confirmed alias
        # for another. Never let dictionary insertion order choose the target.
        candidates = named if isinstance(named, (list, tuple, set)) else [named]
        unique_candidates = {getattr(candidate, 'id', id(candidate)): candidate for candidate in candidates}
        if len(unique_candidates) > 1:
            return None, 'ambiguous_name'
        if unique_candidates:
            return next(iter(unique_candidates.values())), 'name'
    return None, 'branch_not_found'
