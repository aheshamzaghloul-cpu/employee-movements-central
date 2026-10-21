"""Exercise the real, framework-independent Excel branch resolver with fake catalog rows."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "employee_movements/services/excel_import_matching.py"
SPEC = importlib.util.spec_from_file_location("excel_import_matching_under_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
resolve_employee_import_branch = MODULE.resolve_employee_import_branch


def key(value):
    return " ".join(str(value or "").strip().lower().split())


def make_catalog():
    gov_a = SimpleNamespace(id=1, name="Cairo")
    gov_b = SimpleNamespace(id=2, name="Giza")
    branch_a = SimpleNamespace(id=11, name="Nasr", code="A-01", governorate_id=1, governorate=gov_a)
    branch_b = SimpleNamespace(id=22, name="Nasr", code="B-01", governorate_id=2, governorate=gov_b)
    branches = [branch_a, branch_b]
    return {
        "gov_a": gov_a,
        "gov_b": gov_b,
        "branch_a": branch_a,
        "branch_b": branch_b,
        "branches_by_code": {"a-01": [branch_a], "b-01": [branch_b], "shared": branches},
        "branches_by_name": {"nasr": branches},
        "govs": {"cairo": gov_a, "giza": gov_b, "cairo old": gov_a},
        "branch_cache": {("cairo", "nasr"): branch_a, ("giza", "nasr"): branch_b},
        "governorate_alias_keys_by_id": {1: {"cairo old"}, 2: set()},
        "branch_alias_keys_by_id": {11: {"nasr annex"}, 22: set()},
    }


def resolve(code, governorate, branch, catalog):
    return resolve_employee_import_branch(
        code, governorate, branch,
        branches_by_code=catalog["branches_by_code"],
        branches_by_name=catalog["branches_by_name"],
        govs=catalog["govs"],
        branch_cache=catalog["branch_cache"],
        governorate_alias_keys_by_id=catalog["governorate_alias_keys_by_id"],
        branch_alias_keys_by_id=catalog["branch_alias_keys_by_id"],
        normalize_key=key,
    )


def test_unknown_supplied_branch_code_does_not_fall_back_to_matching_name():
    catalog = make_catalog()
    branch, method = resolve("missing-code", "Cairo", "Nasr", catalog)
    assert branch is None
    assert method == "unknown_code"


def test_unique_code_with_conflicting_governorate_or_branch_name_is_explicit_conflict():
    catalog = make_catalog()
    branch, method = resolve("A-01", "Giza", "Nasr", catalog)
    assert branch is catalog["branch_a"]
    assert method == "code_label_mismatch"
    branch, method = resolve("A-01", "Cairo", "Another branch", catalog)
    assert branch is catalog["branch_a"]
    assert method == "code_label_mismatch"


def test_unique_code_accepts_canonical_labels_and_confirmed_aliases():
    catalog = make_catalog()
    branch, method = resolve("A-01", "Cairo old", "Nasr annex", catalog)
    assert branch is catalog["branch_a"]
    assert method == "code"


def test_duplicate_code_is_resolved_only_when_labels_disambiguate_it():
    catalog = make_catalog()
    branch, method = resolve("shared", "Giza", "Nasr", catalog)
    assert branch is catalog["branch_b"]
    assert method == "code_disambiguated"
    branch, method = resolve("shared", "", "", catalog)
    assert branch is None
    assert method == "ambiguous_code"


def test_name_only_fallback_requires_no_supplied_code_and_recognized_governorate():
    catalog = make_catalog()
    branch, method = resolve("", "Cairo", "Nasr", catalog)
    assert branch is catalog["branch_a"]
    assert method == "name"
    branch, method = resolve("", "Typo City", "Nasr", catalog)
    assert branch is None
    assert method == "governorate_not_found"
    branch, method = resolve("", "", "Nasr", catalog)
    assert branch is None
    assert method == "ambiguous_name"


def test_inactive_branch_code_is_reported_instead_of_resolving_to_an_archived_record():
    catalog = make_catalog()
    catalog["branch_a"].is_active = False
    branch, method = resolve("A-01", "Cairo", "Nasr", catalog)
    assert branch is catalog["branch_a"]
    assert method == "inactive_code"


def test_duplicate_code_inside_one_governorate_is_rejected_even_when_name_might_disambiguate():
    catalog = make_catalog()
    branch_a = catalog["branch_a"]
    duplicate = SimpleNamespace(
        id=33, name="Other", code="DUP", governorate_id=1,
        governorate=catalog["gov_a"], is_active=True,
    )
    branch_a.code = "DUP"
    catalog["branches_by_code"]["dup"] = [branch_a, duplicate]
    branch, method = resolve("DUP", "Cairo", "Nasr", catalog)
    assert branch is None
    assert method == "ambiguous_code"


def test_same_governorate_canonical_name_alias_collision_is_not_resolved_by_insertion_order():
    catalog = make_catalog()
    duplicate = SimpleNamespace(
        id=33, name="Nasr Annex", code="A-02", governorate_id=1,
        governorate=catalog["gov_a"], is_active=True,
    )
    catalog["branch_cache"][("cairo", "nasr")] = [catalog["branch_a"], duplicate]
    branch, method = resolve("", "Cairo", "Nasr", catalog)
    assert branch is None
    assert method == "ambiguous_name"
