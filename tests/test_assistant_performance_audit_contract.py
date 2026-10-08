from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = (ROOT / 'employee_movements' / 'assistant' / 'manager.py').read_text()
RENDER = (ROOT / 'employee_movements' / 'assistant' / 'render.py').read_text()


def test_manager_governorate_match_is_db_limited():
    assert "Governorate.name.ilike(f'%{q}%')" in MANAGER
    assert '.limit(11).all()' in MANAGER


def test_manager_entry_assignment_conflict_is_exists_like_query():
    assert 'EntryAssignmentBranch.branch_id.in_(branch_ids)' in MANAGER
    assert '.first())' in MANAGER
    assert "taken = {x.branch_id for x in EntryAssignmentBranch.query" not in MANAGER


def test_manager_permission_cleanup_is_filtered():
    assert 'UserPermission.permission.in_(removable_perms)' in MANAGER


def test_render_branch_scope_is_database_filtered():
    assert 'Branch.id.in_(visible_branch_ids)' in RENDER
    assert 'target_branch_ids = set(bids())' in RENDER
    assert 'for b in Branch.query.filter_by(is_active=True).all()' not in RENDER
