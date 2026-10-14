"""Contracts for confidence-aware, multi-evidence entity matching."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_shared_ranker_combines_independent_evidence_and_returns_explanations():
    source = read("employee_movements/services/entity_matching.py")
    start = source.index("def rank_employee_suggestions(")
    end = source.index("def _load_scoped_employee_alias_maps(", start)
    block = source[start:end]
    for marker in (
        "basic_branch_name: str = \"\"",
        "governorate_name: str = \"\"",
        "employee_name_hint: str = \"\"",
        "weighted = primary_score * primary_weight",
        "branch_context_score",
        "governorate_context_score",
        "\"match_reasons\": reasons",
        "\"evidence\": {",
        "never proof of identity",
    ):
        assert marker in block
    assert "score = max(name_score, code_score * 0.94, branch_score * 0.78)" not in block


def test_identity_decision_exposes_safe_states_and_never_authorizes_writes():
    source = read("employee_movements/services/entity_matching.py")
    start = source.index("def resolve_employee_identity(")
    end = source.index("def _load_scoped_employee_alias_maps(", start)
    block = source[start:end]
    for marker in (
        '"unique_match"',
        '"ambiguous"',
        '"conflicting"',
        '"needs_confirmation"',
        '"no_match"',
        '"movement_creation_allowed": False',
        '"safe_to_prefill": False',
        '"safe_to_prefill": True',
    ):
        assert marker in block
    assert "authorized set" in block


def test_scoped_wrapper_loads_only_aliases_for_already_scoped_candidates():
    source = read("employee_movements/services/entity_matching.py")
    block = source[source.index("def _load_scoped_employee_alias_maps("):source.index("def rank_scoped_branch_suggestions(")]
    assert "employee_ids" in block
    assert "EmployeeNameAlias.employee_id.in_(employee_ids)" in block
    assert "TicketEmployeeCodeAlias.employee_id.in_(employee_ids)" in block
    assert "BranchNameAlias.branch_id.in_(branch_ids)" in block
    assert "GovernorateNameAlias.governorate_id.in_(governorate_ids)" in block
    assert "def resolve_scoped_employee_identity(" in block


def test_assistant_never_auto_selects_a_single_partial_employee_or_branch_result():
    source = read("employee_movements/assistant/directory.py")
    assert "A partial substring is evidence for a suggestion, not proof of identity." in source
    assert "Exact official/confirmed-alias matches were handled above." in source
    assert source.count("return None, matches") >= 2
    assert "return matches[0] if len(matches) == 1 else None, matches" not in source


def test_home_only_prefills_a_unique_identity_and_keeps_partial_search_clickable():
    source = read("employee_movements/blueprints/dashboard.py")
    assert "resolve_scoped_employee_identity(" in source
    assert "if identity.get('status') == 'unique_match':" in source
    assert "elif not movement_search_invalid and len(movement_employee_matches) == 1:" not in source


def test_ticket_code_suggestions_use_optional_branch_context_and_explain_evidence():
    source = read("employee_movements/services/ticket_matching.py")
    start = source.index("def rank_employee_code_candidates(")
    block = source[start:]
    assert "if branch_text:" in block
    assert "overall = code_score * 0.86 + branch_score * 0.14" in block
    assert '"match_reasons": reasons' in block
    assert '"requires_confirmation": True' in block
    assert "branch context" in block.lower() or "branch" in block.lower()


def test_alias_conflict_guard_checks_other_canonical_names_as_well_as_aliases():
    source = read("employee_movements/services/entity_matching.py")
    start = source.index("def alias_owner_conflict(")
    end = source.index("def conflicting_employee_code(", start)
    block = source[start:end]
    for marker in (
        "canonical_model.query.all()",
        "normalize_alias_key(getattr(canonical, canonical_field, \"\")) == normalized",
        '"employee_name": (EmployeeNameAlias, "employee_id", Employee, "full_name")',
        '"branch": (BranchNameAlias, "branch_id", Branch, "name")',
        '"governorate": (GovernorateNameAlias, "governorate_id", Governorate, "name")',
    ):
        assert marker in block
