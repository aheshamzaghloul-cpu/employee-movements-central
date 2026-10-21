from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUERY = ROOT / "employee_movements" / "services" / "mission_query.py"
TEMPLATE = ROOT / "employee_movements" / "templates" / "mission_reports.html"
APP_JS = ROOT / "employee_movements" / "static" / "js" / "app.js"
BASE = ROOT / "employee_movements" / "templates" / "base.html"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def test_mission_filter_options_reuse_the_same_active_reference_data():
    source = QUERY.read_text(encoding="utf-8")
    assert "destination_governorates = govs" in source
    assert "governorates_by_id = {governorate.id: governorate for governorate in govs}" in source
    assert "active_branches = active_branch_query.order_by(" in source
    assert "destination_branches = list(active_branches)" in source
    assert "destination_branches_by_id = {b.id: b for b in destination_branches}" in source
    assert "branches_by_id = {b.id: b for b in branches}" in source


def test_global_active_branch_scope_is_a_query_not_a_materialized_id_list():
    source = QUERY.read_text(encoding="utf-8")
    assert "employee_branch_scope = (" in source
    assert "select(Branch.id)" in source
    assert "Employee.branch_id.in_(employee_branch_scope)" in source
    assert "employee_branch_scope = list(allowed_bids)" in source
    assert "[b.id for b in Branch.query.join(Governorate" not in source


def test_mission_center_local_search_is_explicitly_limited_to_current_server_page():
    template = TEMPLATE.read_text(encoding="utf-8")
    js = APP_JS.read_text(encoding="utf-8")
    assert 'data-smart-server-page="true"' in template
    assert "البحث السريع يفلتر سجلات الصفحة الحالية فقط" in template
    assert "table.dataset.smartServerPage === 'true'" in js
    assert "بحث داخل ${searchScopeLabel}" in js
    assert "في الصفحة الحالية" in js


def test_static_asset_cache_keys_follow_the_single_canonical_app_version():
    base = BASE.read_text(encoding="utf-8")
    mission_template = TEMPLATE.read_text(encoding="utf-8")
    init = (ROOT / "employee_movements" / "__init__.py").read_text(encoding="utf-8")
    version_file = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    ci = CI.read_text(encoding="utf-8")
    assert "v=app_version" in base
    assert "v=app_version" in mission_template
    assert f"__version__ = '{version_file}'" in init
    assert f'version = "{version_file}"' in pyproject
    assert "Path('VERSION.md').read_text(encoding='utf-8').strip()" in ci
