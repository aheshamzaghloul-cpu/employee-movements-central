from pathlib import Path


def test_governorate_assignment_rejects_invalid_values_before_delete():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    body = source.split("def user_update_governorates(i):", 1)[1].split("@bp.post('/users/<int:i>/branches')", 1)[0]
    assert "any(not x.isdigit() for x in raw_ids)" in body
    assert "not chosen.issubset(allowed)" in body
    assert body.index("not chosen.issubset(allowed)") < body.index("UserGovernorate.query.filter_by(user_id=i).delete()")


def test_branch_assignment_rejects_out_of_scope_ids_before_delete():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    body = source.split("def user_update_branches(i):", 1)[1].split("@bp.post('/users/<int:i>/grant-entry-role')", 1)[0]
    assert "any(not x.isdigit() for x in raw_ids)" in body
    assert "not submitted.issubset(allowed)" in body
    assert body.index("not submitted.issubset(allowed)") < body.index("UserBranch.query.filter_by(user_id=i).delete()")
