"""Conservative, Arabic-aware matching helpers for ServiceDesk screenshot fields.

These helpers rank candidates only. They never decide that a fuzzy employee/code
match is correct; the route must require a user choice and revalidate all scope.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable

from ..search import normalize_search_text

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def normalize_job_code(value: object) -> str:
    """Normalize job-code digits, whitespace and common OCR O/0, I/1 confusions."""
    text = normalize_search_text(str(value or "").translate(_DIGITS))
    compact = "".join(char for char in text if char.isalnum())
    digit_count = sum(char.isdigit() for char in compact)
    # OCR confusions are corrected only for codes that are overwhelmingly numeric.
    if compact and digit_count >= min(4, max(1, len(compact) - 1)):
        compact = compact.translate(str.maketrans({"o": "0", "i": "1", "l": "1"}))
    return compact


def job_code_lookup_variants(value: object) -> set[str]:
    """Return exact and known-200-prefix variants without fuzzy guessing."""
    code = normalize_job_code(value)
    if not code:
        return set()
    variants = {code}
    # The legacy prefix rule applies only to numeric job codes. Never mutate
    # usernames/alphanumeric identifiers by prepending a numeric prefix.
    if not code.isdigit():
        return variants
    if code.startswith("200") and len(code) > 3:
        variants.add(code[3:])
    else:
        variants.add("200" + code)
    return variants


def normalize_entity_name(value: object) -> str:
    """Normalize Arabic names for comparisons, preserving word boundaries."""
    text = normalize_search_text(value).replace("ة", "ه")
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def compact_entity_name(value: object) -> str:
    return "".join(char for char in normalize_entity_name(value) if char.isalnum())


def _branch_code_tokens(value: object) -> set[str]:
    """Extract plausible standalone branch-code tokens from OCR text."""
    text = str(value or "").translate(_DIGITS)
    tokens = re.findall(r"[A-Za-z0-9]+", text)
    return {normalize_job_code(token) for token in tokens if len(normalize_job_code(token)) >= 2}


def entity_name_similarity(left: object, right: object) -> float:
    """Return conservative spelling/token similarity in [0, 1]."""
    a, b = normalize_entity_name(left), normalize_entity_name(right)
    if not a or not b:
        return 0.0
    if a == b or compact_entity_name(a) == compact_entity_name(b):
        return 1.0
    ac, bc = compact_entity_name(a), compact_entity_name(b)
    compact_ratio = SequenceMatcher(None, ac, bc).ratio() if ac and bc else 0.0
    at, bt = set(a.split()), set(b.split())
    dice = (2 * len(at & bt) / (len(at) + len(bt))) if at and bt else 0.0
    # One whole word contained in a longer official label can be useful evidence,
    # but never enough by itself to auto-select a branch.
    containment = 0.0
    if min(len(ac), len(bc)) >= 3 and (ac in bc or bc in ac):
        containment = min(len(ac), len(bc)) / max(len(ac), len(bc))
    return max(compact_ratio, dice, containment)


def branch_exact_match(query: object, candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find exact official/alias matches, including governorate/branch word order."""
    query_name = normalize_entity_name(query)
    if not query_name:
        return []
    query_tokens = " ".join(sorted(query_name.split()))
    query_compact = compact_entity_name(query_name)
    query_codes = _branch_code_tokens(query)
    matches = []
    for item in candidates:
        branch_code = normalize_job_code(item.get("code", ""))
        if branch_code and branch_code in query_codes:
            matches.append(item)
            continue
        names = [item.get("name", ""), item.get("label", ""), *item.get("aliases", [])]
        for name in names:
            normalized = normalize_entity_name(name)
            if not normalized:
                continue
            token_key = " ".join(sorted(normalized.split()))
            if normalized == query_name or compact_entity_name(normalized) == query_compact or token_key == query_tokens:
                matches.append(item)
                break
    # Do not allow duplicate representations of the same branch to inflate matches.
    unique = {}
    for item in matches:
        unique[str(item.get("id"))] = item
    return list(unique.values())


def branch_code_match_candidates(query: object, candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return unique branches whose official code appears as a token in OCR text."""
    query_codes = _branch_code_tokens(query)
    if not query_codes:
        return []
    matches = {}
    for item in candidates:
        code = normalize_job_code(item.get("code", ""))
        if code and code in query_codes:
            matches[str(item.get("id"))] = item
    return list(matches.values())


def rank_branch_candidates(query: object, candidates: Iterable[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    """Rank near-name branches for display. Ranked results must be selected manually."""
    query_text = normalize_entity_name(query)
    if len(compact_entity_name(query_text)) < 3:
        return []
    ranked = []
    query_codes = _branch_code_tokens(query)
    for item in candidates:
        branch_code = normalize_job_code(item.get("code", ""))
        names = [item.get("name", ""), item.get("label", ""), *item.get("aliases", [])]
        score = 1.0 if branch_code and branch_code in query_codes else max(
            (entity_name_similarity(query_text, name) for name in names if name), default=0.0
        )
        if score >= 0.43:
            result = dict(item)
            result["match_score"] = round(score, 4)
            ranked.append(result)
    ranked.sort(key=lambda item: (-item["match_score"], str(item.get("label") or item.get("name") or "")))
    return ranked[:limit]


def rank_employee_code_candidates(
    entered_code: object,
    employees: Iterable[Any],
    basic_branch_name: object = "",
    limit: int = 5,
    aliases_by_employee: dict[int, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Suggest (never auto-select) employees for a mistyped/OCR-damaged code."""
    entered = normalize_job_code(entered_code)
    if len(entered) < 4:
        return []
    entered_variants = job_code_lookup_variants(entered)
    branch_text = normalize_entity_name(basic_branch_name)
    aliases_by_employee = aliases_by_employee or {}
    ranked: list[dict[str, Any]] = []
    seen: set[int] = set()
    for employee in employees:
        employee_codes = [getattr(employee, "job_code", ""), *aliases_by_employee.get(getattr(employee, "id", -1), [])]
        employee_variants: set[str] = set()
        for employee_code in employee_codes:
            employee_variants.update(job_code_lookup_variants(employee_code))
        if not employee_variants:
            continue
        code_score = max(
            (SequenceMatcher(None, left, right).ratio() for left in entered_variants for right in employee_variants),
            default=0.0,
        )
        if code_score < 0.70:
            continue
        branch = getattr(employee, "branch", None)
        official_branch = getattr(branch, "name", "") if branch else ""
        branch_code = getattr(branch, "code", "") if branch else ""
        governorate = getattr(getattr(branch, "governorate", None), "name", "") if branch else ""
        branch_label = " · ".join(value for value in (branch_code, official_branch, governorate) if value)
        branch_score = max(
            entity_name_similarity(branch_text, official_branch),
            entity_name_similarity(branch_text, branch_label),
        ) if branch_text else 0.0
        official_variants: set[str] = set()
        alias_variants: set[str] = set()
        for employee_code in (getattr(employee, "job_code", ""), getattr(employee, "employee_code", "")):
            official_variants.update(job_code_lookup_variants(employee_code))
        for employee_code in aliases_by_employee.get(getattr(employee, "id", -1), []):
            alias_variants.update(job_code_lookup_variants(employee_code))
        exact_official = bool(entered_variants & official_variants)
        exact_alias = bool(entered_variants & alias_variants)
        # Context should refine a code match, not arbitrarily lower its score when
        # no branch text was supplied. An exact/prefix code is evidence, never an
        # authorization to create a movement by itself.
        if branch_text:
            overall = code_score * 0.86 + branch_score * 0.14
        else:
            overall = code_score
        reasons = []
        if exact_official:
            reasons.append("الكود يطابق كودًا رسميًا أو صيغة البادئة المعروفة")
        elif exact_alias:
            reasons.append("الكود يطابق صيغة بديلة مؤكدة")
        else:
            reasons.append("الكود قريب من كود محفوظ ويحتاج إلى تأكيد")
        if branch_text and branch_score >= 0.90:
            reasons.append("اسم الفرع الأساسي يدعم المطابقة")
        elif branch_text and branch_score < 0.30:
            reasons.append("اسم الفرع الأساسي لا يدعم هذه المطابقة")
        employee_id = getattr(employee, "id", None)
        if employee_id is not None and employee_id in seen:
            continue
        if employee_id is not None:
            seen.add(employee_id)
        ranked.append({
            "employee": employee,
            "code_score": round(code_score, 4),
            "branch_score": round(branch_score, 4),
            "match_score": round(overall, 4),
            "match_reasons": reasons,
            "evidence": {
                "official_code_exact": exact_official,
                "confirmed_code_alias_exact": exact_alias,
                "branch_context": round(branch_score, 4),
            },
            "requires_confirmation": True,
        })
    ranked.sort(key=lambda item: (-item["match_score"], -item["code_score"], getattr(item["employee"], "full_name", "")))
    return ranked[:limit]
