"""Pure regression tests for confidence-aware matching without starting Flask."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_RUNTIME = "_employee_matching_test_runtime"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_engine():
    if _RUNTIME + ".services.entity_matching" in sys.modules:
        return (
            sys.modules[_RUNTIME + ".services.ticket_matching"],
            sys.modules[_RUNTIME + ".services.entity_matching"],
        )
    root_package = types.ModuleType(_RUNTIME)
    root_package.__path__ = [str(ROOT / "employee_movements")]
    sys.modules[_RUNTIME] = root_package

    services_package = types.ModuleType(_RUNTIME + ".services")
    services_package.__path__ = [str(ROOT / "employee_movements" / "services")]
    sys.modules[_RUNTIME + ".services"] = services_package

    extension_stub = types.ModuleType(_RUNTIME + ".extensions")
    extension_stub.db = object()
    sys.modules[_RUNTIME + ".extensions"] = extension_stub

    _load_module(_RUNTIME + ".search", ROOT / "employee_movements" / "search.py")
    ticket = _load_module(
        _RUNTIME + ".services.ticket_matching",
        ROOT / "employee_movements" / "services" / "ticket_matching.py",
    )
    entity = _load_module(
        _RUNTIME + ".services.entity_matching",
        ROOT / "employee_movements" / "services" / "entity_matching.py",
    )
    return ticket, entity


class Governorate:
    def __init__(self, id, name):
        self.id, self.name = id, name


class Branch:
    def __init__(self, id, name, code, governorate):
        self.id, self.name, self.code, self.governorate = id, name, code, governorate


class Employee:
    def __init__(self, id, full_name, job_code, branch, employee_code=""):
        self.id = id
        self.full_name = full_name
        self.job_code = job_code
        self.employee_code = employee_code
        self.branch = branch


def _records():
    gov_west = Governorate(1, "الغربية")
    gov_sohag = Governorate(2, "سوهاج")
    branch_meshla = Branch(11, "مشلة", "369", gov_west)
    branch_ku = Branch(12, "كفرالزيات أول", "451", gov_west)
    branch_j = Branch(13, "جهينة", "255", gov_sohag)
    employees = [
        Employee(101, "أحمد محمود حسن", "20012345", branch_meshla),
        Employee(102, "أحمد محمد حسن", "20012346", branch_ku),
        Employee(103, "محمد علي حسن", "20020353", branch_j),
    ]
    return employees, (branch_meshla, branch_ku, branch_j)


def test_normalization_handles_arabic_digits_legacy_prefix_and_spelling_variants():
    ticket, entity = _load_engine()
    assert ticket.normalize_job_code("٢٠٠-٢٠٣٥٣") == "20020353"
    assert ticket.job_code_lookup_variants("20353") == {"20353", "20020353"}
    assert entity.normalize_alias_key("أحمد مُحَمَّد") == entity.normalize_alias_key("احمد محمد")
    assert entity.normalize_alias_key("مشله") == entity.normalize_alias_key("مُشْلَة")


def test_multi_evidence_ranking_combines_name_branch_and_governorate_context():
    _, entity = _load_engine()
    employees, branches = _records()
    ranked = entity.rank_employee_suggestions(
        "احمد محمود",
        employees,
        basic_branch_name="مشله",
        governorate_name="الغربيه",
    )
    assert ranked
    assert ranked[0]["employee"].id == 101
    assert ranked[0]["evidence"]["branch_context"] > 0.9
    assert ranked[0]["evidence"]["governorate_context"] > 0.9
    assert "توافق الفرع الأساسي" in ranked[0]["match_reasons"]
    assert ranked[0]["match_type"] == "approximate"  # ranking is never an automatic selection


def test_ambiguous_legacy_prefix_is_never_auto_resolved():
    _, entity = _load_engine()
    employees, _ = _records()
    employees.append(Employee(104, "محمد حسن", "20353", employees[2].branch))
    result = entity.resolve_employee_identity("20353", employees)
    assert result["status"] == "ambiguous"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert len(result["candidates"]) == 2


def test_unique_legacy_prefix_match_only_prefills_and_never_creates_movement():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity("٢٠٣٥٣", employees)
    assert result["status"] == "unique_match"
    assert result["employee"].id == 103
    assert result["safe_to_prefill"] is True
    assert result["movement_creation_allowed"] is False


def test_conflicting_name_hint_blocks_unique_code_autofill():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity("20353", employees, employee_name_hint="أحمد محمود حسن")
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False


def test_fuzzy_name_is_a_suggestion_not_a_match_decision():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity("احمد محود حسن", employees)
    assert result["status"] == "needs_confirmation"
    # This typo should not create an action even if ranking is extremely confident.
    assert result["movement_creation_allowed"] is False
    if result["status"] == "needs_confirmation":
        assert result["employee"] is None
        assert result["candidates"]


def test_short_numeric_fragment_does_not_generate_noisy_suggestions():
    _, entity = _load_engine()
    employees, _ = _records()
    assert entity.rank_employee_suggestions("12", employees) == []
    result = entity.resolve_employee_identity("12", employees)
    assert result["status"] == "no_match"


def test_confirmed_alias_exact_match_is_unique_but_still_not_a_write_authorization():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity(
        "حمدي احمد",
        employees,
        name_aliases_by_employee={101: ["حمدي أحمد"]},
    )
    assert result["status"] == "unique_match"
    assert result["employee"].id == 101
    assert result["movement_creation_allowed"] is False


def test_ticket_code_ranking_uses_basic_branch_as_corroborating_evidence():
    ticket, _ = _load_engine()
    employees, branches = _records()
    ranked = ticket.rank_employee_code_candidates(
        "20012347",
        employees[:2],
        basic_branch_name="مشله",
    )
    assert ranked
    assert ranked[0]["employee"].id == 101
    assert ranked[0]["branch_score"] > ranked[1]["branch_score"]
    assert "اسم الفرع الأساسي يدعم المطابقة" in ranked[0]["match_reasons"]
    assert ranked[0]["requires_confirmation"] is True


def test_exact_official_name_with_branch_context_disambiguates_same_name_safely():
    _, entity = _load_engine()
    west = Governorate(10, "الغربية")
    sohag = Governorate(20, "سوهاج")
    west_branch = Branch(110, "مشلة", "369", west)
    sohag_branch = Branch(120, "جهينة", "255", sohag)
    employees = [
        Employee(201, "أحمد محمد حسن", "20011111", west_branch),
        Employee(202, "أحمد محمد حسن", "20022222", sohag_branch),
    ]
    result = entity.resolve_employee_identity("أحمد محمد حسن", employees, basic_branch_name="مشله")
    assert result["status"] == "unique_match"
    assert result["employee"].id == 201
    assert result["movement_creation_allowed"] is False


def test_exact_code_conflicts_with_fuzzy_name_hint_for_a_different_employee():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity(
        "20020353", employees, employee_name_hint="أحمد محمد حس"
    )
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert "الاسم المساند" in result["reason"]
    assert {item["employee"].id for item in result["candidates"]} == {102, 103}


def test_exact_code_conflicts_with_fuzzy_basic_branch_context_for_another_employee():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity(
        "20020353", employees, basic_branch_name="مشلا"
    )
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert "الفرع الأساسي" in result["reason"]
    assert {item["employee"].id for item in result["candidates"]} == {101, 103}


def test_exact_code_conflicts_with_a_different_official_governorate():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity(
        "20020353", employees, governorate_name="الغربية"
    )
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert "المحافظة" in result["reason"]


def test_typographic_noise_in_matching_context_does_not_conflict_with_exact_employee():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity(
        "20020353",
        employees,
        employee_name_hint="محمد علي حس",
        basic_branch_name="جهينه",
        governorate_name="سوهاج",
    )
    assert result["status"] == "unique_match"
    assert result["employee"].id == 103
    assert result["safe_to_prefill"] is True
    assert result["movement_creation_allowed"] is False


def test_exact_code_conflicts_with_fuzzy_governorate_context_for_another_employee():
    _, entity = _load_engine()
    employees, _ = _records()
    result = entity.resolve_employee_identity("20020353", employees, governorate_name="الغربي")
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert "المحافظة" in result["reason"]
