"""Shared, conservative entity matching for the whole application.

This module centralizes Arabic-aware search across employee identities, branch
names/codes and governorates. It ranks/filters records but never bypasses the
caller’s authorization scope and never auto-selects fuzzy matches.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Iterable

from sqlalchemy import false, func, or_, select

from ..extensions import db
from ..search import normalize_search_text, normalized_sql_text, search_contains
from .ticket_matching import (
    compact_entity_name,
    entity_name_similarity,
    job_code_lookup_variants,
    normalize_entity_name,
    normalize_job_code,
    rank_branch_candidates,
)

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_CODE_SEPARATORS = (" ", "-", "‐", "‑", "–", "—", "/", ".", "_")


def normalize_alias_key(value: object, kind: str = "name") -> str:
    """Stable key for confirmed aliases without modifying official values."""
    if kind == "code":
        return normalize_job_code(str(value or "").translate(_DIGITS))
    return normalize_entity_name(value)


def alias_owner_conflict(kind: str, value: object, target_id: int | None = None):
    """Return a canonical/alias owner that conflicts with a proposed alias.

    A spelling may not shadow another record's canonical name or an alias already
    confirmed for another record. ``target_id`` is the owning record being edited;
    its own canonical name does not count as a cross-record conflict.
    """
    normalized = normalize_alias_key(value, "code" if kind == "employee_code" else "name")
    if not normalized:
        return None
    from ..models import (
        Branch,
        BranchNameAlias,
        Employee,
        EmployeeNameAlias,
        Governorate,
        GovernorateNameAlias,
        TicketEmployeeCodeAlias,
    )

    mapping = {
        "employee_name": (EmployeeNameAlias, "employee_id", Employee, "full_name"),
        "employee_code": (TicketEmployeeCodeAlias, "employee_id", None, None),
        "branch": (BranchNameAlias, "branch_id", Branch, "name"),
        "governorate": (GovernorateNameAlias, "governorate_id", Governorate, "name"),
    }
    if kind not in mapping:
        raise ValueError(f"Unsupported alias kind: {kind}")
    alias_model, owner_field, canonical_model, canonical_field = mapping[kind]

    if canonical_model is not None:
        for canonical in canonical_model.query.populate_existing().all():
            if target_id is not None and getattr(canonical, "id", None) == target_id:
                continue
            if normalize_alias_key(getattr(canonical, canonical_field, "")) == normalized:
                return canonical

    row = alias_model.query.populate_existing().filter_by(normalized_alias=normalized).first()
    if row and target_id is not None and getattr(row, owner_field) == target_id:
        return None
    return row

def employee_write_snapshot(employee: Any) -> dict[str, Any]:
    """JSON-safe snapshot for fail-closed confirmation of assistant mutations.

    Include every editable employee field plus lifecycle state so a pending
    assistant confirmation cannot apply to a record that changed after preview.
    Values are intentionally compared exactly (email case/whitespace changes
    included) because this snapshot protects the user's reviewed view.
    """
    def _iso(value: Any) -> str | None:
        if value is None:
            return None
        return value.isoformat() if hasattr(value, "isoformat") else str(value)

    def _text(value: Any) -> str | None:
        return None if value is None else str(value)

    branch_id = getattr(employee, "branch_id", None)
    return {
        "full_name": _text(getattr(employee, "full_name", None)),
        "email": _text(getattr(employee, "email", None)),
        "employee_code": _text(getattr(employee, "employee_code", None)),
        "job_title": _text(getattr(employee, "job_title", None)),
        "job_code": _text(getattr(employee, "job_code", None)),
        "company_phone": _text(getattr(employee, "company_phone", None)),
        "personal_phone": _text(getattr(employee, "personal_phone", None)),
        "hire_date": _iso(getattr(employee, "hire_date", None)),
        "branch_id": int(branch_id) if branch_id is not None else None,
        "is_active": bool(getattr(employee, "is_active", False)),
        "deleted_at": _iso(getattr(employee, "deleted_at", None)),
        "resignation_date": _iso(getattr(employee, "resignation_date", None)),
    }


def conflicting_employee_code(value: object, exclude_employee_id: int | None = None):
    """Find another employee/confirmed code alias colliding with this code's variants."""
    variants = job_code_lookup_variants(value)
    if not variants:
        return None
    from ..models import Employee, TicketEmployeeCodeAlias

    rows = Employee.query.populate_existing().filter(Employee.id != (exclude_employee_id or -1)).all()
    for employee in rows:
        for official_code in (getattr(employee, "job_code", None), getattr(employee, "employee_code", None)):
            if official_code and variants & job_code_lookup_variants(official_code):
                return employee
    aliases = TicketEmployeeCodeAlias.query.populate_existing().filter(TicketEmployeeCodeAlias.normalized_alias.in_(variants)).all()
    for alias in aliases:
        if alias.employee_id != exclude_employee_id:
            return getattr(alias, "employee", None) or alias
    return None


def _escaped_contains(value: object) -> str:
    normalized = normalize_alias_key(value)
    escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _normalized_code_sql(column):
    expression = normalized_sql_text(column)
    for separator in _CODE_SEPARATORS:
        expression = func.replace(expression, separator, "")
    return expression


def employee_search_filter(
    value: object,
    *,
    include_job_title: bool = False,
    include_contacts: bool = False,
    include_branch: bool = True,
):
    """Return a SQLAlchemy predicate for employee name/code/confirmed aliases.

    The caller must still apply active-state and authorization/work-scope filters.
    Numeric codes support the known missing/extra ``200`` prefix only as search
    variants; caller selection remains ambiguous if more than one row matches.
    """
    from ..models import (
        Branch,
        Employee,
        EmployeeNameAlias,
        Governorate,
        GovernorateNameAlias,
        TicketEmployeeCodeAlias,
        BranchNameAlias,
    )

    raw = str(value or "").strip()
    normalized = normalize_search_text(raw)
    entity_key = normalize_alias_key(raw)
    if not normalized and not entity_key:
        return false()

    code_key = normalize_job_code(raw.translate(_DIGITS))
    # Short numeric queries (1–4 digits) are exact-code lookups only. Treating
    # a fragment such as "123" as a substring across a longer code or branch
    # label returns a noisy, misleading result set and disagrees with the UI.
    if code_key.isdigit() and len(code_key) <= 4:
        variants = job_code_lookup_variants(code_key)
        predicates = [
            _normalized_code_sql(Employee.job_code).in_(variants),
            _normalized_code_sql(Employee.employee_code).in_(variants),
        ]
        short_code_alias_ids = select(TicketEmployeeCodeAlias.employee_id).where(
            TicketEmployeeCodeAlias.normalized_alias.in_(variants)
        )
        predicates.append(Employee.id.in_(short_code_alias_ids))
        if include_branch:
            predicates.append(Employee.branch.has(normalized_sql_text(Branch.code) == code_key))
        return or_(*predicates)

    predicates = [
        search_contains(Employee.full_name, raw),
        search_contains(Employee.job_code, raw),
        search_contains(Employee.employee_code, raw),
    ]
    if include_job_title:
        predicates.append(search_contains(Employee.job_title, raw))
    if include_contacts:
        predicates.extend([search_contains(Employee.email, raw), search_contains(Employee.company_phone, raw), search_contains(Employee.personal_phone, raw)])

    if len(entity_key) >= 2:
        name_alias_ids = (
            db.session.query(EmployeeNameAlias.employee_id)
            .filter(EmployeeNameAlias.normalized_alias.like(_escaped_contains(raw), escape="\\"))
            .subquery()
        )
        predicates.append(Employee.id.in_(name_alias_ids))

    if code_key and len(code_key) >= 3:
        variants = job_code_lookup_variants(code_key)
        code_columns = (Employee.job_code, Employee.employee_code)
        predicates.extend(_normalized_code_sql(column).in_(variants) for column in code_columns)
        alias_ids = (
            db.session.query(TicketEmployeeCodeAlias.employee_id)
            .filter(
                or_(
                    TicketEmployeeCodeAlias.normalized_alias.in_(variants),
                    TicketEmployeeCodeAlias.normalized_alias.like(_escaped_contains(code_key), escape="\\"),
                )
            )
            .subquery()
        )
        predicates.append(Employee.id.in_(alias_ids))

    if include_branch:
        branch_conditions = [search_contains(Branch.name, raw), search_contains(Branch.code, raw)]
        branch_alias_ids = (
            db.session.query(BranchNameAlias.branch_id)
            .filter(BranchNameAlias.normalized_alias.like(_escaped_contains(raw), escape="\\"))
            .subquery()
        )
        branch_conditions.append(Branch.id.in_(branch_alias_ids))
        governorate_alias_ids = (
            db.session.query(GovernorateNameAlias.governorate_id)
            .filter(GovernorateNameAlias.normalized_alias.like(_escaped_contains(raw), escape="\\"))
            .subquery()
        )
        branch_conditions.extend([
            Branch.governorate.has(search_contains(Governorate.name, raw)),
            Branch.governorate_id.in_(governorate_alias_ids),
        ])
        predicates.append(Employee.branch.has(or_(*branch_conditions)))

    return or_(*predicates)


def branch_search_filter(value: object, *, include_governorate: bool = True):
    """Search active branch catalogs by official name, code, governorate or alias."""
    from ..models import Branch, BranchNameAlias, Governorate, GovernorateNameAlias

    raw = str(value or "").strip()
    if not normalize_search_text(raw):
        return false()
    predicates = [search_contains(Branch.name, raw), search_contains(Branch.code, raw)]
    alias_ids = (
        db.session.query(BranchNameAlias.branch_id)
        .filter(BranchNameAlias.normalized_alias.like(_escaped_contains(raw), escape="\\"))
        .subquery()
    )
    predicates.append(Branch.id.in_(alias_ids))
    if include_governorate:
        gov_alias_ids = (
            db.session.query(GovernorateNameAlias.governorate_id)
            .filter(GovernorateNameAlias.normalized_alias.like(_escaped_contains(raw), escape="\\"))
            .subquery()
        )
        predicates.extend([
            Branch.governorate.has(search_contains(Governorate.name, raw)),
            Branch.governorate_id.in_(gov_alias_ids),
        ])
    return or_(*predicates)


def governorate_search_filter(value: object):
    """Search governorates by canonical name or explicitly confirmed alias."""
    from ..models import Governorate, GovernorateNameAlias

    raw = str(value or "").strip()
    if not normalize_search_text(raw):
        return false()
    alias_ids = (
        db.session.query(GovernorateNameAlias.governorate_id)
        .filter(GovernorateNameAlias.normalized_alias.like(_escaped_contains(raw), escape="\\"))
        .subquery()
    )
    return or_(search_contains(Governorate.name, raw), Governorate.id.in_(alias_ids))


def rank_employee_suggestions(
    value: object,
    employees: Iterable[Any],
    limit: int = 8,
    *,
    name_aliases_by_employee: dict[int, list[str]] | None = None,
    code_aliases_by_employee: dict[int, list[str]] | None = None,
    branch_aliases_by_branch: dict[int, list[str]] | None = None,
    governorate_aliases_by_governorate: dict[int, list[str]] | None = None,
    basic_branch_name: str = "",
    governorate_name: str = "",
    employee_name_hint: str = "",
) -> list[dict[str, Any]]:
    """Rank entity candidates with multiple independent signals.

    The candidate collection MUST already be restricted to the current user's
    authorized scope. This function only ranks candidates; even a high score is
    never proof of identity and must not trigger a write without explicit
    confirmation and the normal server-side validation path. Fuzzy suggestions
    require an explicit choice from the user.
    """
    query = str(value or "").strip()
    query_name = normalize_entity_name(query)
    query_code = normalize_job_code(query.translate(_DIGITS))
    is_code_query = len(query_code) >= 4 and (
        query_code.isdigit()
        or sum(char.isdigit() for char in query_code) / max(1, len(query_code)) >= 0.60
    )
    if len(compact_entity_name(query_name)) < 3 and not is_code_query:
        return []

    variants = job_code_lookup_variants(query_code) if is_code_query else set()
    name_aliases_by_employee = name_aliases_by_employee or {}
    code_aliases_by_employee = code_aliases_by_employee or {}
    branch_aliases_by_branch = branch_aliases_by_branch or {}
    governorate_aliases_by_governorate = governorate_aliases_by_governorate or {}
    normalized_branch_context = normalize_entity_name(basic_branch_name)
    normalized_governorate_context = normalize_entity_name(governorate_name)
    normalized_employee_hint = normalize_entity_name(employee_name_hint)
    ranked: list[dict[str, Any]] = []
    seen: set[int] = set()

    def best_name_score(query_text: str, names: list[str]) -> float:
        if not query_text:
            return 0.0
        return max(
            (entity_name_similarity(query_text, name) for name in names if str(name or '').strip()),
            default=0.0,
        )

    def exact_name(query_text: str, names: list[str]) -> bool:
        if not query_text:
            return False
        compact_query = compact_entity_name(query_text)
        return any(
            normalize_entity_name(name) == query_text
            or compact_entity_name(name) == compact_query
            for name in names if str(name or '').strip()
        )

    for employee in employees:
        employee_id = getattr(employee, "id", None)
        if employee_id in seen:
            continue
        if employee_id is not None:
            seen.add(employee_id)

        official_name = getattr(employee, "full_name", "") or ""
        candidate_names = [official_name, *name_aliases_by_employee.get(employee_id, [])]
        name_score = best_name_score(query_name, candidate_names)
        name_exact = exact_name(query_name, [official_name])
        name_alias_exact = exact_name(query_name, name_aliases_by_employee.get(employee_id, []))

        official_codes = [getattr(employee, "job_code", ""), getattr(employee, "employee_code", "")]
        code_aliases = code_aliases_by_employee.get(employee_id, [])
        all_codes = [*official_codes, *code_aliases]
        all_code_variants: set[str] = set()
        official_code_variants: set[str] = set()
        for code in official_codes:
            official_code_variants.update(job_code_lookup_variants(code))
        for code in all_codes:
            all_code_variants.update(job_code_lookup_variants(code))

        code_exact = bool(variants and variants & official_code_variants)
        code_alias_exact = bool(variants and variants & (all_code_variants - official_code_variants))
        code_score = 0.0
        if is_code_query:
            if code_exact or code_alias_exact:
                code_score = 1.0
            else:
                code_scores = []
                for code in all_codes:
                    normalized_code = normalize_job_code(code)
                    if not normalized_code:
                        continue
                    for variant in variants:
                        code_scores.append(SequenceMatcher(None, variant, normalized_code).ratio())
                code_score = max(code_scores, default=0.0)

        branch = getattr(employee, "branch", None)
        branch_name = getattr(branch, "name", "") if branch else ""
        branch_code = getattr(branch, "code", "") if branch else ""
        governorate = getattr(branch, "governorate", None) if branch else None
        gov_name = getattr(governorate, "name", "") if governorate else ""
        branch_aliases = branch_aliases_by_branch.get(getattr(branch, "id", None), []) if branch else []
        governorate_aliases = governorate_aliases_by_governorate.get(getattr(governorate, "id", None), []) if governorate else []
        branch_names = [branch_name, *branch_aliases]
        governorate_names = [gov_name, *governorate_aliases]
        branch_display_names = [
            " ".join(part for part in (branch_name, gov_name) if part),
            " ".join(part for part in (branch_code, branch_name, gov_name) if part),
            *branch_aliases,
        ]
        branch_query_score = best_name_score(query_name, [*branch_display_names, *governorate_names])
        branch_context_score = best_name_score(normalized_branch_context, branch_names) if normalized_branch_context else 0.0
        # Allow branch labels such as "369 - مشلة - الغربية" as corroborating context.
        if normalized_branch_context and branch:
            branch_context_score = max(
                branch_context_score,
                best_name_score(normalized_branch_context, branch_display_names),
            )
        governorate_context_score = best_name_score(normalized_governorate_context, governorate_names) if normalized_governorate_context else 0.0
        employee_hint_score = best_name_score(normalized_employee_hint, candidate_names) if normalized_employee_hint else 0.0

        reasons: list[str] = []
        if name_exact:
            reasons.append("تطابق الاسم الرسمي")
        elif name_alias_exact:
            reasons.append("تطابق اسم بديل مؤكد")
        elif name_score >= 0.60:
            reasons.append("تشابه في اسم الموظف")
        if code_exact:
            reasons.append("تطابق الكود الرسمي أو صيغته المعروفة")
        elif code_alias_exact:
            reasons.append("تطابق كود بديل مؤكد")
        elif is_code_query and code_score >= 0.70:
            reasons.append("تشابه في الكود؛ يحتاج إلى تأكيد")
        if branch_query_score >= 0.90:
            reasons.append("تطابق في اسم الفرع أو المحافظة")
        elif branch_query_score >= 0.60:
            reasons.append("تشابه في اسم الفرع أو المحافظة")
        if branch_context_score >= 0.90:
            reasons.append("توافق الفرع الأساسي")
        elif normalized_branch_context and branch_context_score < 0.35:
            reasons.append("الفرع الأساسي لا يدعم هذه المطابقة")
        if governorate_context_score >= 0.90:
            reasons.append("توافق المحافظة")
        if employee_hint_score >= 0.90:
            reasons.append("توافق اسم الموظف المساند")

        # Select the primary evidence according to the shape of the query. Then
        # combine independent user-supplied context instead of taking only max().
        if is_code_query:
            primary_score = code_score
            primary_weight = 0.74
        elif branch_query_score >= name_score + 0.16 and branch_query_score >= 0.50:
            primary_score = branch_query_score
            primary_weight = 0.72
        else:
            primary_score = name_score
            primary_weight = 0.72

        weighted = primary_score * primary_weight
        total_weight = primary_weight
        if normalized_branch_context:
            weighted += branch_context_score * 0.16
            total_weight += 0.16
        if normalized_governorate_context:
            weighted += governorate_context_score * 0.08
            total_weight += 0.08
        if normalized_employee_hint:
            weighted += employee_hint_score * 0.18
            total_weight += 0.18
        score = weighted / total_weight if total_weight else 0.0

        # A context value cannot rescue a candidate with almost no primary match.
        primary_floor = 0.48 if is_code_query else 0.43
        if primary_score < primary_floor or score < 0.48:
            continue
        ranked.append({
            "employee": employee,
            "match_score": round(score, 4),
            "match_type": "approximate",
            "match_reasons": reasons,
            "evidence": {
                "name": round(name_score, 4),
                "official_name_exact": name_exact,
                "confirmed_name_alias_exact": name_alias_exact,
                "code": round(code_score, 4),
                "official_code_exact": code_exact,
                "confirmed_code_alias_exact": code_alias_exact,
                "branch_query": round(branch_query_score, 4),
                "branch_context": round(branch_context_score, 4),
                "governorate_context": round(governorate_context_score, 4),
                "employee_name_hint": round(employee_hint_score, 4),
            },
            "name_score": round(name_score, 4),
            "code_score": round(code_score, 4),
        })

    ranked.sort(key=lambda item: (
        -item["match_score"],
        -item["evidence"]["code"],
        -item["evidence"]["name"],
        getattr(item["employee"], "full_name", ""),
    ))
    return ranked[:max(1, min(int(limit or 8), 20))]


def resolve_employee_identity(
    value: object,
    employees: Iterable[Any],
    *,
    name_aliases_by_employee: dict[int, list[str]] | None = None,
    code_aliases_by_employee: dict[int, list[str]] | None = None,
    branch_aliases_by_branch: dict[int, list[str]] | None = None,
    governorate_aliases_by_governorate: dict[int, list[str]] | None = None,
    employee_name_hint: str = "",
    basic_branch_name: str = "",
    governorate_name: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    """Resolve identity conservatively within a caller-supplied authorized set.

    ``unique_match`` means identity can be prefilled from the official record; it
    never authorizes creating a movement. ``ambiguous`` and ``conflicting`` always
    require a person to choose a candidate explicitly.
    """
    rows = []
    seen_ids: set[int] = set()
    for employee in employees:
        employee_id = getattr(employee, "id", None)
        if employee_id is not None and employee_id in seen_ids:
            continue
        if employee_id is not None:
            seen_ids.add(employee_id)
        rows.append(employee)

    names = name_aliases_by_employee or {}
    codes = code_aliases_by_employee or {}
    branch_aliases = branch_aliases_by_branch or {}
    gov_aliases = governorate_aliases_by_governorate or {}
    query = str(value or "").strip()
    query_name = normalize_entity_name(query)
    query_code = normalize_job_code(query.translate(_DIGITS))
    is_code_query = len(query_code) >= 4 and (
        query_code.isdigit()
        or sum(char.isdigit() for char in query_code) / max(1, len(query_code)) >= 0.60
    )

    exact_ids: set[int] = set()
    exact_reason = ""
    if is_code_query:
        variants = job_code_lookup_variants(query_code)
        for employee in rows:
            employee_id = getattr(employee, "id", None)
            if employee_id is None:
                continue
            official_codes = [getattr(employee, "job_code", ""), getattr(employee, "employee_code", "")]
            official_variants: set[str] = set()
            for code in official_codes:
                official_variants.update(job_code_lookup_variants(code))
            alias_variants: set[str] = set()
            for code in codes.get(employee_id, []):
                alias_variants.update(job_code_lookup_variants(code))
            if variants & official_variants or variants & alias_variants:
                exact_ids.add(employee_id)
        exact_reason = "تطابق كود رسمي أو صيغة بديلة مؤكدة"
    elif len(compact_entity_name(query_name)) >= 3:
        compact_query = compact_entity_name(query_name)
        for employee in rows:
            employee_id = getattr(employee, "id", None)
            if employee_id is None:
                continue
            candidate_names = [getattr(employee, "full_name", ""), *names.get(employee_id, [])]
            if any(
                normalize_entity_name(name) == query_name
                or compact_entity_name(name) == compact_query
                for name in candidate_names if str(name or '').strip()
            ):
                exact_ids.add(employee_id)
        exact_reason = "تطابق الاسم الرسمي أو اسم بديل مؤكد"

    def context_exact_ids(context: str, getter):
        normalized_context = normalize_entity_name(context)
        compact_context = compact_entity_name(normalized_context)
        if not normalized_context or len(compact_context) < 3:
            return set()
        result = set()
        for employee in rows:
            employee_id = getattr(employee, "id", None)
            if employee_id is None:
                continue
            values = getter(employee, employee_id)
            if any(
                normalize_entity_name(item) == normalized_context
                or compact_entity_name(item) == compact_context
                for item in values if str(item or '').strip()
            ):
                result.add(employee_id)
        return result

    if employee_name_hint:
        hinted_ids = context_exact_ids(
            employee_name_hint,
            lambda employee, employee_id: [getattr(employee, "full_name", ""), *names.get(employee_id, [])],
        )
        if exact_ids and hinted_ids:
            overlap = exact_ids & hinted_ids
            if not overlap:
                ranked_conflict = rank_employee_suggestions(
                    query, rows, limit=limit, name_aliases_by_employee=names,
                    code_aliases_by_employee=codes, branch_aliases_by_branch=branch_aliases,
                    governorate_aliases_by_governorate=gov_aliases, employee_name_hint=employee_name_hint,
                    basic_branch_name=basic_branch_name, governorate_name=governorate_name,
                )
                return {"status": "conflicting", "employee": None, "candidates": ranked_conflict,
                        "reason": "الكود والاسم المساند يشيران إلى سجلين مختلفين؛ لم يتم الاختيار تلقائيًا.",
                        "safe_to_prefill": False, "movement_creation_allowed": False}
            exact_ids = overlap
        elif not exact_ids and len(hinted_ids) == 1 and not is_code_query:
            exact_ids = hinted_ids
            exact_reason = "تطابق الاسم المساند بشكل فريد"

    if basic_branch_name:
        branch_ids = context_exact_ids(
            basic_branch_name,
            lambda employee, employee_id: [
                getattr(getattr(employee, "branch", None), "name", ""),
                *branch_aliases.get(getattr(getattr(employee, "branch", None), "id", None), []),
            ],
        )
        if exact_ids and branch_ids:
            overlap = exact_ids & branch_ids
            if overlap:
                exact_ids = overlap
            else:
                return {"status": "conflicting", "employee": None, "candidates": [],
                        "reason": "الفرع الأساسي لا يتوافق مع هوية الموظف المطابقة؛ يلزم المراجعة.",
                        "safe_to_prefill": False, "movement_creation_allowed": False}

    # Apply the same exact-context constraint to the governorate. Previously a
    # unique code could prefill an employee even when an explicit governorate in
    # the source contradicted the employee's official branch. A fuzzy mismatch is
    # checked separately below and never used to auto-select another employee.
    if governorate_name:
        governorate_ids = context_exact_ids(
            governorate_name,
            lambda employee, employee_id: [
                getattr(getattr(getattr(employee, "branch", None), "governorate", None), "name", ""),
                *gov_aliases.get(
                    getattr(getattr(getattr(employee, "branch", None), "governorate", None), "id", None),
                    [],
                ),
            ],
        )
        if exact_ids and governorate_ids:
            overlap = exact_ids & governorate_ids
            if overlap:
                exact_ids = overlap
            else:
                return {"status": "conflicting", "employee": None, "candidates": [],
                        "reason": "المحافظة المذكورة لا تتوافق مع هوية الموظف المطابقة؛ يلزم المراجعة.",
                        "safe_to_prefill": False, "movement_creation_allowed": False}

    ranked = rank_employee_suggestions(
        query,
        rows,
        limit=limit,
        name_aliases_by_employee=names,
        code_aliases_by_employee=codes,
        branch_aliases_by_branch=branch_aliases,
        governorate_aliases_by_governorate=gov_aliases,
        basic_branch_name=basic_branch_name,
        governorate_name=governorate_name,
        employee_name_hint=employee_name_hint,
    )
    by_id = {getattr(item["employee"], "id", None): item for item in ranked}
    if exact_ids:
        exact_rows = [row for row in rows if getattr(row, "id", None) in exact_ids]
        if len(exact_rows) == 1:
            employee = exact_rows[0]
            # Exact identity evidence does not erase strong contradictory context.
            # Detect when an explicitly supplied name/branch/governorate is much
            # closer to another authorized candidate. Similarity is used only to
            # stop unsafe prefill, never to choose the alternative automatically.
            context_specs = (
                ("employee_name_hint", employee_name_hint, 0.82, 0.16,
                 "الاسم المساند أقرب إلى موظف آخر من صاحب الكود/الاسم المطابق"),
                ("basic_branch_name", basic_branch_name, 0.72, 0.20,
                 "اسم الفرع الأساسي أقرب إلى سجل آخر؛ راجع هوية الموظف والفرع"),
                ("governorate_name", governorate_name, 0.82, 0.18,
                 "اسم المحافظة أقرب إلى سجل آخر؛ راجع هوية الموظف والمحافظة"),
            )
            target_id = getattr(employee, "id", None)
            for context_key, context_value, minimum_score, minimum_margin, conflict_reason in context_specs:
                query_context = normalize_entity_name(context_value)
                if len(compact_entity_name(query_context)) < 4:
                    continue
                context_scores: list[tuple[float, int | None]] = []
                for candidate in rows:
                    candidate_id = getattr(candidate, "id", None)
                    branch_obj = getattr(candidate, "branch", None)
                    gov_obj = getattr(branch_obj, "governorate", None) if branch_obj else None
                    if context_key == "employee_name_hint":
                        values = [getattr(candidate, "full_name", ""), *names.get(candidate_id, [])]
                    elif context_key == "basic_branch_name":
                        values = [
                            getattr(branch_obj, "name", "") if branch_obj else "",
                            getattr(branch_obj, "code", "") if branch_obj else "",
                            " ".join(part for part in (
                                getattr(branch_obj, "code", "") if branch_obj else "",
                                getattr(branch_obj, "name", "") if branch_obj else "",
                                getattr(gov_obj, "name", "") if gov_obj else "",
                            ) if part),
                            *(branch_aliases.get(getattr(branch_obj, "id", None), []) if branch_obj else []),
                        ]
                    else:
                        values = [getattr(gov_obj, "name", "") if gov_obj else "", *(gov_aliases.get(getattr(gov_obj, "id", None), []) if gov_obj else [])]
                    score = max((entity_name_similarity(query_context, item) for item in values if str(item or "").strip()), default=0.0)
                    context_scores.append((score, candidate_id))
                target_scores = [score for score, candidate_id in context_scores if candidate_id == target_id]
                outside_scores = [(score, candidate_id) for score, candidate_id in context_scores if candidate_id != target_id]
                target_score = max(target_scores, default=0.0)
                other_score, other_id = max(outside_scores, default=(0.0, None))
                if other_id is not None and other_score >= minimum_score and other_score - target_score >= minimum_margin:
                    conflict_candidates = []
                    for candidate_id in (target_id, other_id):
                        if candidate_id in by_id:
                            conflict_candidates.append(by_id[candidate_id])
                        else:
                            candidate_obj = next((item for item in rows if getattr(item, "id", None) == candidate_id), None)
                            if candidate_obj is not None:
                                conflict_candidates.append({
                                    "employee": candidate_obj,
                                    "match_score": round(other_score if candidate_id == other_id else target_score, 4),
                                    "match_type": "context_conflict",
                                    "match_reasons": [conflict_reason] if candidate_id == other_id else [exact_reason],
                                    "evidence": {context_key: round(other_score if candidate_id == other_id else target_score, 4)},
                                })
                    return {"status": "conflicting", "employee": None, "candidates": conflict_candidates,
                            "reason": conflict_reason + "؛ لم يتم الملء التلقائي.",
                            "safe_to_prefill": False, "movement_creation_allowed": False}
            return {"status": "unique_match", "employee": employee,
                    "candidates": [by_id[getattr(employee, "id", None)]] if getattr(employee, "id", None) in by_id else [],
                    "reason": exact_reason, "safe_to_prefill": True,
                    "movement_creation_allowed": False}
        candidate_rows = []
        for employee in exact_rows:
            candidate_rows.append(by_id.get(getattr(employee, "id", None), {
                "employee": employee, "match_score": 1.0, "match_type": "exact",
                "match_reasons": [exact_reason],
                "evidence": {"exact_identity": True},
            }))
        return {"status": "ambiguous", "employee": None, "candidates": candidate_rows,
                "reason": "المعرّف يطابق أكثر من موظف؛ اختر السجل الصحيح يدويًا.",
                "safe_to_prefill": False, "movement_creation_allowed": False}
    if ranked:
        return {"status": "needs_confirmation", "employee": None, "candidates": ranked,
                "reason": "هذه اقتراحات تقريبية وليست إثباتًا لهوية الموظف.",
                "safe_to_prefill": False, "movement_creation_allowed": False}
    return {"status": "no_match", "employee": None, "candidates": [],
            "reason": "لم يُعثر على تطابق موثوق. راجع البيانات أو اختر الموظف يدويًا.",
            "safe_to_prefill": False, "movement_creation_allowed": False}

def _load_scoped_employee_alias_maps(rows: list[Any]) -> tuple[
    dict[int, list[str]], dict[int, list[str]], dict[int, list[str]], dict[int, list[str]]
]:
    """Load confirmed aliases only for entities in the caller's pre-filtered scope."""
    from ..models import BranchNameAlias, EmployeeNameAlias, GovernorateNameAlias, TicketEmployeeCodeAlias

    employee_ids = [getattr(employee, "id", None) for employee in rows if getattr(employee, "id", None) is not None]
    names: dict[int, list[str]] = {}
    codes: dict[int, list[str]] = {}
    branch_aliases: dict[int, list[str]] = {}
    governorate_aliases: dict[int, list[str]] = {}
    if not employee_ids:
        return names, codes, branch_aliases, governorate_aliases

    for alias in EmployeeNameAlias.query.filter(EmployeeNameAlias.employee_id.in_(employee_ids)).all():
        names.setdefault(alias.employee_id, []).append(alias.alias_text)
    for alias in TicketEmployeeCodeAlias.query.filter(TicketEmployeeCodeAlias.employee_id.in_(employee_ids)).all():
        codes.setdefault(alias.employee_id, []).append(alias.alias_text)
    branch_ids = {
        getattr(getattr(employee, "branch", None), "id", None)
        for employee in rows
        if getattr(getattr(employee, "branch", None), "id", None) is not None
    }
    governorate_ids = {
        getattr(getattr(getattr(employee, "branch", None), "governorate", None), "id", None)
        for employee in rows
        if getattr(getattr(getattr(employee, "branch", None), "governorate", None), "id", None) is not None
    }
    if branch_ids:
        for alias in BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(branch_ids)).all():
            branch_aliases.setdefault(alias.branch_id, []).append(alias.alias_text)
    if governorate_ids:
        for alias in GovernorateNameAlias.query.filter(GovernorateNameAlias.governorate_id.in_(governorate_ids)).all():
            governorate_aliases.setdefault(alias.governorate_id, []).append(alias.alias_text)
    return names, codes, branch_aliases, governorate_aliases


def rank_scoped_employee_suggestions(
    value: object,
    employees: Iterable[Any],
    limit: int = 8,
    *,
    basic_branch_name: str = "",
    governorate_name: str = "",
    employee_name_hint: str = "",
) -> list[dict[str, Any]]:
    """Load confirmed aliases within a pre-scoped candidate set and rank evidence."""
    rows = list(employees)
    if not any(getattr(employee, "id", None) is not None for employee in rows):
        return []
    names, codes, branch_aliases, governorate_aliases = _load_scoped_employee_alias_maps(rows)
    return rank_employee_suggestions(
        value,
        rows,
        limit=limit,
        name_aliases_by_employee=names,
        code_aliases_by_employee=codes,
        branch_aliases_by_branch=branch_aliases,
        governorate_aliases_by_governorate=governorate_aliases,
        basic_branch_name=basic_branch_name,
        governorate_name=governorate_name,
        employee_name_hint=employee_name_hint,
    )

def resolve_scoped_employee_identity(
    value: object,
    employees: Iterable[Any],
    *,
    employee_name_hint: str = "",
    basic_branch_name: str = "",
    governorate_name: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    """Resolve within an already-authorized candidate set and load confirmed aliases.

    Callers must build ``employees`` after applying active-state, role and work-scope
    filters. A unique result permits pre-filling official values only; the movement
    creation endpoint must still revalidate authorization, fields and conflicts.
    """
    rows = list(employees)
    if not any(getattr(employee, "id", None) is not None for employee in rows):
        return {"status": "no_match", "employee": None, "candidates": [],
                "reason": "لا توجد سجلات ضمن النطاق المسموح.",
                "safe_to_prefill": False, "movement_creation_allowed": False}
    names, codes, branch_aliases, gov_aliases = _load_scoped_employee_alias_maps(rows)
    return resolve_employee_identity(
        value,
        rows,
        name_aliases_by_employee=names,
        code_aliases_by_employee=codes,
        branch_aliases_by_branch=branch_aliases,
        governorate_aliases_by_governorate=gov_aliases,
        employee_name_hint=employee_name_hint,
        basic_branch_name=basic_branch_name,
        governorate_name=governorate_name,
        limit=limit,
    )


def rank_scoped_branch_suggestions(value: object, branches: Iterable[Any], limit: int = 8) -> list[dict[str, Any]]:
    """Rank branch names/aliases in an already-authorized set; never auto-select."""
    from ..models import BranchNameAlias, GovernorateNameAlias

    rows = list(branches)
    ids = [getattr(branch, "id", None) for branch in rows if getattr(branch, "id", None) is not None]
    if not ids:
        return []
    aliases: dict[int, list[str]] = {}
    for alias in BranchNameAlias.query.filter(BranchNameAlias.branch_id.in_(ids)).all():
        aliases.setdefault(alias.branch_id, []).append(alias.alias_text)
    gov_ids = {getattr(branch, "governorate_id", None) for branch in rows}
    gov_aliases: dict[int, list[str]] = {}
    for alias in GovernorateNameAlias.query.filter(GovernorateNameAlias.governorate_id.in_(gov_ids)).all():
        gov_aliases.setdefault(alias.governorate_id, []).append(alias.alias_text)
    candidates = []
    for branch in rows:
        governorate = getattr(branch, "governorate", None)
        gov_name = getattr(governorate, "name", "") if governorate else ""
        all_aliases = list(aliases.get(branch.id, []))
        if governorate:
            all_aliases.extend(gov_aliases.get(governorate.id, []))
        candidates.append({
            "id": branch.id,
            "name": branch.name,
            "code": getattr(branch, "code", "") or "",
            "label": " · ".join(part for part in (getattr(branch, "code", "") or "", branch.name, gov_name) if part),
            "aliases": all_aliases,
        })
    ranked = rank_branch_candidates(value, candidates, limit=limit)
    by_id = {branch.id: branch for branch in rows}
    return [{"branch": by_id[item["id"]], "match_score": item["match_score"], "match_type": "approximate"} for item in ranked if item.get("id") in by_id]


def rank_governorate_suggestions(value: object, governorates: Iterable[Any], limit: int = 8) -> list[dict[str, Any]]:
    """Rank near governorate names using confirmed aliases; results are suggestions only."""
    from ..models import GovernorateNameAlias

    rows = list(governorates)
    ids = [getattr(governorate, "id", None) for governorate in rows if getattr(governorate, "id", None) is not None]
    aliases: dict[int, list[str]] = {}
    if ids:
        for alias in GovernorateNameAlias.query.filter(GovernorateNameAlias.governorate_id.in_(ids)).all():
            aliases.setdefault(alias.governorate_id, []).append(alias.alias_text)
    query = normalize_entity_name(value)
    if len(compact_entity_name(query)) < 3:
        return []
    ranked = []
    for governorate in rows:
        names = [getattr(governorate, "name", ""), *aliases.get(governorate.id, [])]
        score = max((entity_name_similarity(query, name) for name in names if name), default=0.0)
        if score >= 0.48:
            ranked.append({"governorate": governorate, "match_score": round(score, 4), "match_type": "approximate"})
    ranked.sort(key=lambda item: (-item["match_score"], getattr(item["governorate"], "name", "")))
    return ranked[:max(1, min(int(limit or 8), 20))]
