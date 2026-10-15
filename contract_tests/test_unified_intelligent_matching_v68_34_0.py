from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_shared_matching_service_handles_confirmed_aliases_and_never_auto_selects_fuzzy_matches():
    service = read("employee_movements/services/entity_matching.py")
    for token in (
        "def employee_search_filter(",
        "EmployeeNameAlias",
        "TicketEmployeeCodeAlias",
        "BranchNameAlias",
        "GovernorateNameAlias",
        "def rank_scoped_employee_suggestions(",
        "def rank_scoped_branch_suggestions(",
        '"match_type": "approximate"',
        "def conflicting_employee_code(",
        "def alias_owner_conflict(",
    ):
        assert token in service
    assert "The caller must still apply active-state and authorization/work-scope filters" in service
    assert "require an explicit choice" in service


def test_server_side_short_numeric_search_is_exact_not_substring_based():
    service = read("employee_movements/services/entity_matching.py")
    start = service.index("def employee_search_filter(")
    end = service.index("\ndef branch_search_filter(", start)
    block = service[start:end]
    short_branch = block.index("if code_key.isdigit() and len(code_key) <= 4:")
    common_substring = block.index("predicates = [\n        search_contains(Employee.full_name, raw)")
    assert short_branch < common_substring
    assert "_normalized_code_sql(Employee.job_code).in_(variants)" in block
    assert "_normalized_code_sql(Employee.employee_code).in_(variants)" in block
    assert "Employee.branch.has(normalized_sql_text(Branch.code) == code_key)" in block
    assert "select(TicketEmployeeCodeAlias.employee_id).where(" in block


def test_shared_matcher_is_wired_into_all_primary_server_search_surfaces():
    sources = {
        "home": read("employee_movements/blueprints/dashboard.py"),
        "employee directory": read("employee_movements/blueprints/employees.py"),
        "movement API": read("employee_movements/blueprints/movements.py"),
        "assistant tool": read("employee_movements/assistant/agent.py"),
        "assistant directory": read("employee_movements/assistant/directory.py"),
        "Excel import": read("employee_movements/blueprints/excel_import.py"),
    }
    for label in ("home", "employee directory", "movement API", "assistant tool", "assistant directory"):
        assert "employee_search_filter" in sources[label], f"shared employee matcher missing from {label}"
    assert "EmployeeNameAlias" in sources["Excel import"]
    assert "TicketEmployeeCodeAlias" in sources["Excel import"]
    assert "job_code_lookup_variants" in sources["Excel import"]
    assert "branch_search_filter" in sources["assistant tool"]
    assert "governorate_search_filter" in sources["assistant tool"]
    assert "rank_governorate_suggestions" in sources["assistant tool"]


def test_scope_is_applied_before_assistant_employee_result_limit():
    agent = read("employee_movements/assistant/agent.py")
    block = agent[agent.index('if name == "search_employees":'):agent.index('if name == "get_employee_profile":')]
    assert "allowed_branch_ids = set(bids())" in block
    assert "candidate_scope.filter(Employee.branch_id.in_(allowed_branch_ids))" in block
    assert "rank_scoped_employee_suggestions(q, pool, limit=limit)" in block
    assert "include_contacts=can(\"manage_employees\")" in block


def test_movement_picker_and_movement_worklist_include_confirmed_aliases_without_expanding_scope():
    routes = read("employee_movements/blueprints/movements.py")
    template = read("employee_movements/templates/movements.html")
    assert "def _branch_search_payload(branches):" in routes
    assert "def _employee_search_aliases(employees):" in routes
    assert "def _movement_search_text_map(movements):" in routes
    assert "search_aliases" in routes
    assert "movement_search_text_by_id=movement_search_text_by_id" in routes
    assert "window.employeeSearchMatches(query,`${b.name||''} ${b.code||''} ${b.search_aliases||''}`)" in template
    assert "window.employeeSearchMatches(query,`${e.name||''} ${e.code||''} ${e.search_aliases||''}`)" in template
    assert "window.employeeSearchMatches(q,row.dataset.search||" in template
    assert "Branch.id.in_(allowed_bids)" in routes


def test_excel_import_never_creates_a_duplicate_when_name_alias_points_to_an_existing_employee():
    importer = read("employee_movements/blueprints/excel_import.py")
    assert "employee_names_by_branch = {}" in importer
    assert "for alias in EmployeeNameAlias.query.all():" in importer
    assert "name_match_ids = employee_names_by_branch.get((b.id, _excel_key(vals.get('name'))), set())" in importer
    assert "الاسم يطابق موظفًا موجودًا في الفرع" in importer
    assert "الكود والبريد يحددان سجلًا، لكن الاسم يطابق موظفًا آخر" in importer
    assert "e.full_name if e.id in name_match_ids else vals['name']" in importer


def test_privacy_filter_covers_canonical_ids_and_learned_aliases_for_every_entity_kind():
    privacy = read("employee_movements/assistant/privacy.py")
    for token in ("EmployeeNameAlias", "TicketEmployeeCodeAlias", "BranchNameAlias", "GovernorateNameAlias", "AssistantAlias"):
        assert token in privacy
    assert "Local alias privacy screening could not complete; external processing blocked." in privacy


def test_all_client_side_searches_share_arabic_normalization_and_conservative_fuzzy_matcher():
    utility = read("employee_movements/static/js/search_utils.js")
    assert "global.normalizeEmployeeSearchText" in utility
    assert "global.employeeSearchMatches" in utility
    assert "replace(/[أإآٱ]/g, 'ا')" in utility
    assert "digitMap[digit]" in utility
    assert "tokenEditDistance" in utility
    assert "item.length >= 3 && token.length >= 3" in utility
    assert "if (/^\\d{1,2}$/.test(needle))" in utility
    assert "if (/^\\d{3,4}$/.test(needle))" in utility
    for relative in (
        "employee_movements/static/js/app.js",
        "employee_movements/static/js/catalog_directory.js",
        "employee_movements/static/js/smart_ui.js",
        "employee_movements/templates/employees.html",
        "employee_movements/templates/delegations.html",
        "employee_movements/templates/movements.html",
    ):
        assert "employeeSearchMatches" in read(relative), relative


def test_client_matcher_functionally_handles_arabic_variants_prefix_and_rejects_tiny_tokens():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed in this environment; static contracts cover wiring.")
    utility = read("employee_movements/static/js/search_utils.js")
    script = "global.window = global;\n" + utility + "\n" + r'''
const assert = require('node:assert/strict');
assert.equal(window.normalizeEmployeeSearchText('أَحْمَد'), window.normalizeEmployeeSearchText('احمد'));
assert.equal(window.employeeSearchMatches('احمذ', 'أحمد محمد حسن'), true);
assert.equal(window.employeeSearchMatches('20353', 'كود شئون العاملين 20020353'), true);
assert.equal(window.employeeSearchMatches('م ح', 'محمد حسن'), false);
assert.equal(window.employeeSearchMatches('12', '123456'), false);
assert.equal(window.employeeSearchMatches('123', 'كود 81234'), false);
assert.equal(window.employeeSearchMatches('123', 'كود 200123'), true);
assert.equal(window.employeeSearchMatches('20353', 'كود 20020353'), true);
assert.equal(window.employeeSearchMatches('20453', 'كود 20020353'), false);
'''
    subprocess.run([node, "-e", script], check=True, capture_output=True, text=True, timeout=10)


def test_version_metadata_and_asset_cache_busting_are_ready_for_current_release():
    assert read("VERSION.md").strip() == "68.49.0"
    assert 'version = "68.49.0"' in read("pyproject.toml")
    assert "__version__ = '68.49.0'" in read("employee_movements/__init__.py")
    base = read("employee_movements/templates/base.html")
    assert "v=68.49.0" in base
    assert "v=68.35.0" not in base and "v=68.34.0" not in base and "v=68.33.0" not in base


def test_admin_assistant_governorate_resolution_uses_shared_alias_matcher_and_never_auto_selects_fuzzy():
    manager = read("employee_movements/assistant/manager.py")
    start = manager.index("def _match_gov(name):")
    end = manager.index("\ndef plan(a):", start)
    block = manager[start:end]
    assert "governorate_search_filter(q)" in block
    assert "rank_governorate_suggestions(q, pool, limit=8)" in block
    assert "return None, [item['governorate'] for item in ranked]" in block
    assert "Approximate matches are suggestions only" in block
