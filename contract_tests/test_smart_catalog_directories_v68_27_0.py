from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCK = (ROOT / "employee_movements/templates/assistant_dock.html").read_text(encoding="utf-8")
GOVERNORATES = (ROOT / "employee_movements/templates/governorates.html").read_text(encoding="utf-8")
BRANCHES = (ROOT / "employee_movements/templates/branches.html").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/templates/employees.html").read_text(encoding="utf-8")
CATALOG_JS = (ROOT / "employee_movements/static/js/catalog_directory.js").read_text(encoding="utf-8")
CATALOG_ROUTES = (ROOT / "employee_movements/blueprints/catalog.py").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")
EMPLOYEE_ROUTES = (ROOT / "employee_movements/blueprints/employees.py").read_text(encoding="utf-8")


def test_assistant_has_a_clear_named_launcher_and_preserves_accessibility():
    assert 'class="assistant-dock-copy"><strong>بسيوني</strong><small>في خدمتك</small>' in DOCK
    assert 'aria-label="فتح مساعد بسيوني الذكي"' in DOCK
    assert 'aria-expanded="false"' in DOCK
    assert BASE.index("{% include 'assistant_dock.html' %}") < BASE.index('id="sidebarToggle"')
    assert 'id="assistantDockPanel" hidden' in DOCK


def test_governorate_directory_has_counts_search_status_filter_and_safe_actions():
    for token in ('catalog-kpis', 'data-catalog-search', 'data-catalog-status', 'data-catalog-item', 'branch_counts.get(x.id,0)', 'active_branch_counts.get(x.id,0)', '/governorates/{{x.id}}/toggle', '/governorates/{{x.id}}/delete'):
        assert token in GOVERNORATES
    assert 'Governorate.query.filter' in CATALOG_ROUTES
    assert 'Employee.is_active == True' in CATALOG_ROUTES


def test_branch_directory_supports_governorate_status_search_and_employee_counts():
    for token in ('data-catalog-search', 'data-catalog-governorate', 'data-catalog-status', 'data-catalog-item', 'employee_counts.get(x.id,0)', '/branches/{{x.id}}/edit', '/branches/{{x.id}}/toggle', '/branches/{{x.id}}/delete'):
        assert token in BRANCHES
    assert 'def _render_branches_page(rows, gs):' in CATALOG_ROUTES


def test_catalog_filter_script_is_deferred_until_the_directory_dom_exists():
    assert 'filename=\'js/catalog_directory.js\'' in BASE
    script_line = next(line for line in BASE.splitlines() if 'catalog_directory.js' in line)
    assert ' defer' in script_line


def test_catalog_filtering_is_local_fast_and_has_reset_and_empty_state():
    for token in ('applyFilters()', 'data-catalog-reset', 'data-catalog-empty', 'item.hidden = !shown', 'data-catalog-more', 'PAGE_SIZE = 12'):
        assert token in CATALOG_JS


def test_employee_search_covers_branch_and_governorate_names_and_has_directory_controls():
    assert 'employee_search_filter(q, include_branch=True)' in EMPLOYEE_ROUTES
    matching = (ROOT / 'employee_movements/services/entity_matching.py').read_text(encoding='utf-8')
    assert 'search_contains(Branch.name, raw)' in matching
    assert 'search_contains(Governorate.name, raw)' in matching
    assert 'BranchNameAlias' in matching and 'GovernorateNameAlias' in matching
    assert 'data-expand-branches' in EMPLOYEES and 'data-collapse-branches' in EMPLOYEES
    assert 'e.branch.name if e.branch else' in EMPLOYEES
    assert "grouped_branch_count=sum(len(group[\'branches\']) for group in grouped_employees)" in EMPLOYEE_ROUTES
