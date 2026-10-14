from pathlib import Path
import re
import jinja2
import tinycss2

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
BRANCHES = (ROOT / "employee_movements/templates/branches.html").read_text(encoding="utf-8")
GOVERNORATES = (ROOT / "employee_movements/templates/governorates.html").read_text(encoding="utf-8")
CATALOG_JS = (ROOT / "employee_movements/static/js/catalog_directory.js").read_text(encoding="utf-8")
SMART_UI_JS = (ROOT / "employee_movements/static/js/smart_ui.js").read_text(encoding="utf-8")
MOVEMENT_ROUTES = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
BASE = (ROOT / "employee_movements/templates/base.html").read_text(encoding="utf-8")


def test_movement_type_is_the_first_required_choice_and_gates_following_steps():
    type_at = MOVEMENTS.index('id="movementCreateType" name="movement_type" required')
    gov_at = MOVEMENTS.index('id="movementGovernorateStep" hidden')
    branch_at = MOVEMENTS.index('id="movementBranchStep" hidden')
    employee_at = MOVEMENTS.index('id="movementEmployeeStep" hidden')
    details_at = MOVEMENTS.index('id="movementDetailsStep" hidden')
    assert type_at < gov_at < branch_at < employee_at < details_at
    assert 'value="" selected>اختر نوع الحركة للمتابعة</option>' in MOVEMENTS
    assert 'function handleMovementTypeChange()' in MOVEMENTS


def test_movement_search_is_local_to_allowed_branch_and_employee_results():
    assert 'id="movementBranchSearch"' in MOVEMENTS
    assert 'id="movementEmployeeSearch"' in MOVEMENTS
    assert 'PICKER_INITIAL_COUNT=8' in MOVEMENTS
    assert 'movement_type:type.value' in MOVEMENTS
    assert 'employeeId.value=e.id' in MOVEMENTS
    assert "button.addEventListener('click',()=>selectCreateEmployee(e,activePickerBranch,button))" in MOVEMENTS
    assert "name.textContent=e.name||''" in MOVEMENTS


def test_cross_governorate_assignment_picker_remains_server_authorized():
    assert "movement_type == 'انتداب'" in MOVEMENT_ROUTES
    assert "'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'" in MOVEMENT_ROUTES
    assert 'movement_global_picker_allowed=' in MOVEMENT_ROUTES
    assert "type?.value==='انتداب' && {{ 'true' if movement_global_picker_allowed else 'false' }}" in MOVEMENTS
    assert "option.dataset.operationalScope==='1'" in MOVEMENTS


def test_branch_api_exposes_branch_code_for_search_without_relaxing_scope():
    assert "def _branch_search_payload(branches):" in MOVEMENT_ROUTES
    assert "'code': branch.code or ''" in MOVEMENT_ROUTES
    assert "search_aliases" in MOVEMENT_ROUTES
    assert 'Branch.id.in_(allowed_bids)' in MOVEMENT_ROUTES
    assert "window.employeeSearchMatches(query,`${b.name||''} ${b.code||''} ${b.search_aliases||''}`)" in MOVEMENTS


def test_governorates_and_branches_collapse_secondary_filters_and_limit_initial_cards():
    for template in (BRANCHES, GOVERNORATES):
        assert 'catalog-advanced-filters' in template
        assert 'data-catalog-more' in template
        assert 'data-catalog-search' in template
    assert 'PAGE_SIZE = 12' in CATALOG_JS
    assert 'const shown = new Set(matched.slice(0, visibleLimit))' in CATALOG_JS
    assert 'more?.addEventListener' in CATALOG_JS


def test_catalog_search_normalizes_common_arabic_spellings_and_avoids_false_empty_state():
    assert ".replace(/[أإآ]/g, 'ا')" in CATALOG_JS
    assert 'items.length === 0 || matched.length !== 0' in CATALOG_JS


def test_first_entry_directory_is_searchable_and_reveals_rows_progressively():
    assert 'id="smartEntrySearch"' in HOME
    assert 'id="smartEntryShowAll"' in HOME
    assert 'data-smart-entry-item' in HOME
    assert 'for row in entry_rows %}' in HOME
    assert 'entry_rows[:8]' not in HOME
    assert 'const PAGE_SIZE=8' in SMART_UI_JS
    assert 'applyEntryDirectory()' in SMART_UI_JS


def test_employees_inside_each_first_entry_branch_are_searchable_and_progressive():
    assert 'data-entry-employee-search' in HOME
    assert 'data-entry-employee-item' in HOME
    assert 'data-entry-employee-more' in HOME
    assert 'لا توجد نتائج مطابقة لهذا البحث.' in HOME
    assert 'applyEntryEmployeeSearch()' in SMART_UI_JS


def test_release_cache_tags_match_current_version():
    version = (ROOT / 'VERSION.md').read_text(encoding='utf-8').strip()
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    assert f'?v={version}' in BASE
    assert (ROOT / 'employee_movements/__init__.py').read_text(encoding='utf-8').find(f"__version__ = '{version}'") >= 0
    assert (ROOT / 'pyproject.toml').read_text(encoding='utf-8').find(f'version = "{version}"') >= 0


def test_all_templates_and_modified_stylesheets_parse():
    env = jinja2.Environment()
    templates = list((ROOT / 'employee_movements/templates').rglob('*.html'))
    assert len(templates) == 46
    for path in templates:
        env.parse(path.read_text(encoding='utf-8'))
    css_paths = [ROOT / 'employee_movements/static/css/app.css', ROOT / 'employee_movements/static/css/pages/home.css', ROOT / 'employee_movements/static/css/pages/workspace-pages.css']
    for path in css_paths:
        rules = tinycss2.parse_stylesheet(path.read_text(encoding='utf-8'), skip_whitespace=True, skip_comments=True)
        assert not [rule for rule in rules if rule.type == 'error']


def test_employee_directory_limits_each_branch_and_exposes_more_results():
    template = (ROOT / 'employee_movements/templates/employees.html').read_text(encoding='utf-8')
    assert 'data-employee-more hidden' in template
    assert 'Math.min(8,matched.length)' in template
    assert 'expandedEmployeeBranches' in template
    assert 'useServerSubset' in template
    assert 'النتائج الحالية تخص البحث السابق' in template
