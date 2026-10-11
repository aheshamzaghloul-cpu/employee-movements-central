from pathlib import Path


def test_supervisor_entry_edit_requires_full_governorate_coverage():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    start = source.index("def user_edit(i):")
    end = source.index("@bp.post('/users/<int:i>/delete')", start)
    block = source[start:end]
    assert "chosen_gids.issubset(user_gov_ids(sup))" in block
    assert "تعذر حفظ المدخل الأول: يجب أن يغطي نطاقك جميع المحافظات التابعة للفروع المسندة." in block
    assert "db.session.rollback()" in block
