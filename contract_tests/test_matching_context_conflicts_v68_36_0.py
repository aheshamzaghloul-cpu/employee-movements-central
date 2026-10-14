"""Runtime regression checks for contradictory matching evidence.

The test fixture loads only the shared matcher and plain in-memory records, so
these safety decisions can be checked without booting Flask or a live database.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_FIXTURE_PATH = ROOT / "tests" / "test_matching_engine_confidence.py"
_SPEC = importlib.util.spec_from_file_location("confidence_matching_fixture_v68_36_0", _FIXTURE_PATH)
assert _SPEC and _SPEC.loader
_FIXTURE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FIXTURE)


def test_exact_code_is_blocked_when_fuzzy_name_hint_points_to_another_employee():
    _, matcher = _FIXTURE._load_engine()
    employees, _ = _FIXTURE._records()
    result = matcher.resolve_employee_identity("20020353", employees, employee_name_hint="أحمد محمد حس")
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert {row["employee"].id for row in result["candidates"]} == {102, 103}


def test_exact_code_is_blocked_when_fuzzy_basic_branch_points_to_another_employee():
    _, matcher = _FIXTURE._load_engine()
    employees, _ = _FIXTURE._records()
    result = matcher.resolve_employee_identity("20020353", employees, basic_branch_name="مشلا")
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert {row["employee"].id for row in result["candidates"]} == {101, 103}


def test_exact_code_is_blocked_when_official_governorate_context_disagrees():
    _, matcher = _FIXTURE._load_engine()
    employees, _ = _FIXTURE._records()
    result = matcher.resolve_employee_identity("20020353", employees, governorate_name="الغربية")
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False


def test_typographic_noise_that_still_supports_the_same_employee_is_allowed_to_prefill():
    _, matcher = _FIXTURE._load_engine()
    employees, _ = _FIXTURE._records()
    result = matcher.resolve_employee_identity(
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


def test_exact_code_is_blocked_when_fuzzy_governorate_context_points_to_another_employee():
    _, matcher = _FIXTURE._load_engine()
    employees, _ = _FIXTURE._records()
    result = matcher.resolve_employee_identity("20020353", employees, governorate_name="الغربي")
    assert result["status"] == "conflicting"
    assert result["employee"] is None
    assert result["safe_to_prefill"] is False
    assert result["movement_creation_allowed"] is False
    assert "المحافظة" in result["reason"]
