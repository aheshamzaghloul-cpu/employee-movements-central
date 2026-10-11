from pathlib import Path


def test_first_entry_appointment_branch_must_be_in_assigned_scope():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    start = source.index("def user_edit(i):")
    end = source.index("@bp.post('/users/<int:i>/delete')", start)
    block = source[start:end]
    assert block.count("appointment_bid not in chosen") == 2


def test_first_entry_supervisor_must_cover_assigned_governorates():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    start = source.index("def user_edit(i):")
    end = source.index("@bp.post('/users/<int:i>/delete')", start)
    block = source[start:end]
    assert "chosen_gids.issubset(user_gov_ids(sup))" in block
    assert "يجب اختيار مشرف نشط يغطي جميع المحافظات المسندة للمدخل الأول." in block
    assert "db.session.rollback()" in block
