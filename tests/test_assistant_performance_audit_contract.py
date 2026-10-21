from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = (ROOT / 'employee_movements' / 'assistant' / 'manager.py').read_text()
PLANNING = (ROOT / 'employee_movements' / 'assistant' / 'manager_planning.py').read_text()
EXECUTOR = (ROOT / 'employee_movements' / 'assistant' / 'manager_execution.py').read_text()
RESOLVER = (ROOT / 'employee_movements' / 'assistant' / 'manager_resolvers.py').read_text()
RENDER = (ROOT / 'employee_movements' / 'assistant' / 'read_helpers.py').read_text()


def test_manager_governorate_match_is_db_limited():
    assert "governorate_search_filter(q)" in RESOLVER
    assert '.limit(11).all()' in RESOLVER


def test_manager_entry_assignment_conflict_is_exists_like_query():
    assert 'EntryAssignmentBranch.branch_id.in_(branch_ids)' in EXECUTOR
    assert '.first())' in EXECUTOR
    assert "taken = {x.branch_id for x in EntryAssignmentBranch.query" not in EXECUTOR


def test_manager_permission_cleanup_is_filtered():
    assert 'UserPermission.permission.in_(removable_perms)' in EXECUTOR


def test_render_branch_scope_is_database_filtered():
    assert "def _visible_branch(b):" in RENDER
    assert "governorate.is_active and can('view_reports')" in RENDER
    assert "EntryAssignmentBranch.query.join(EntryAssignment)" in RENDER
    assert "target_branch_ids = set(bids())" not in RENDER
    assert "for b in Branch.query.filter_by(is_active=True).all()" not in RENDER
