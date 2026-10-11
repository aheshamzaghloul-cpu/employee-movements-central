from pathlib import Path


def test_user_toggle_checks_missing_account_before_mutation():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    body = source.split("def user_toggle(i):", 1)[1].split("@bp.post('/users/<int:i>/reset')", 1)[0]
    assert "if not u:" in body
    assert "abort(404)" in body
    assert body.index("abort(404)") < body.index("u.is_active = not u.is_active")
    assert "تفعيل الحساب" in body and "تعطيل الحساب" in body


def test_governorate_assignment_validates_user_and_rejects_malformed_ids_safely():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    body = source.split("def user_update_governorates(i):", 1)[1].split("@bp.post('/users/<int:i>/branches')", 1)[0]
    assert "u = db.session.get(User, i)" in body
    assert "if not u:" in body and "abort(404)" in body
    assert "any(not x.isdigit() for x in raw_ids)" in body
    assert "not chosen.issubset(allowed)" in body
    assert body.index("not chosen.issubset(allowed)") < body.index("UserGovernorate.query.filter_by(user_id=i).delete()")
