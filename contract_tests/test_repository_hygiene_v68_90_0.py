"""Repository hygiene contracts for source organization and release integrity."""
from scripts.check_repository_hygiene import (
    find_duplicate_test_sources,
    find_late_module_imports,
    find_release_metadata_drift,
)


def test_application_imports_are_grouped_at_module_headers():
    assert find_late_module_imports() == []


def test_runtime_and_contract_suites_do_not_duplicate_identical_test_files():
    assert find_duplicate_test_sources() == []


def test_release_version_markers_are_synchronized():
    assert find_release_metadata_drift() == []
