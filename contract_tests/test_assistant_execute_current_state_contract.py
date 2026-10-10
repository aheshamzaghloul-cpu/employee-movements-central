from pathlib import Path


MANAGER = Path(__file__).resolve().parents[1] / 'employee_movements' / 'assistant' / 'manager.py'


def _source():
    return MANAGER.read_text(encoding='utf-8')


def test_execute_reloads_mutation_entities_from_database():
    src = _source()
    start = src.index('def _execute(plan):')
    execute = src[start:]
    required = {
        'governorate_edit': "db.session.get(Governorate, plan['id'])",
        'governorate_toggle': "db.session.get(Governorate, plan['id'])",
        'branch_edit': "db.session.get(Branch, plan['id'])",
        'employee_edit': "db.session.get(Employee, plan['id'])",
        'user_edit': "db.session.get(User, plan['id'])",
        'movement_edit': "db.session.get(Movement, plan['id'])",
        'delegation_revoke': "db.session.get(ApprovalDelegation,plan['id'])",
        'entry_remove': "db.session.get(EntryAssignment, plan['id'])",
        'entry_replace': "db.session.get(EntryAssignment, plan['assignment_id'])",
    }
    for kind, lookup in required.items():
        assert (f"kind == '{kind}'" in execute or f"kind in ('{kind}'" in execute or (kind == 'employee_edit' and "'employee_edit'" in execute and "kind in ('employee_delete','employee_restore','employee_edit')" in execute))
        assert lookup in execute, f'{kind} must reload its current DB row before mutation'


def test_execute_rechecks_current_role_for_sensitive_role_mutations():
    src = _source()
    start = src.index("elif kind in ('role_grant','role_revoke'):")
    block = src[start:]
    assert "db.session.get(User, plan['user_id'])" in block
    assert "UserRole.query.filter_by(user_id=u.id, role=role).first()" in block
    assert "sync_role_accounts(u)" in block


def test_execute_revalidates_current_movement_before_mutation():
    src = _source()
    start = src.index("elif kind == 'movement_edit':")
    block = src[start:]
    assert "db.session.get(Movement, plan['id'])" in block
    assert 'movement_overlaps(' in block
    assert "db.session.add(MovementHistory" in block



def test_assistant_cannot_reactivate_branch_under_inactive_governorate():
    src = _source()
    start = src.index("elif kind in ('branch_edit','branch_toggle'):")
    end = src.index("elif kind in ('employee_delete','employee_restore','employee_edit'):", start)
    block = src[start:end]
    assert "if new_active:" in block
    assert "db.session.get(Governorate, x.governorate_id)" in block
    assert "not parent.is_active" in block


def test_assistant_cannot_move_employee_to_branch_under_inactive_governorate():
    src = _source()
    start = src.index("elif kind in ('employee_delete','employee_restore','employee_edit'):")
    end = src.index("elif kind == 'employee_create':", start)
    block = src[start:end]
    assert "db.session.get(Governorate, b.governorate_id)" in block
    assert "not parent.is_active" in block
