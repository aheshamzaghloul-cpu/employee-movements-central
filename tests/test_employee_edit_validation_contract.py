from pathlib import Path


def test_employee_edit_requires_active_matching_branch_and_governorate():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "employees.py").read_text(encoding="utf-8")
    start = source.index("def employee_edit(i):")
    end = source.index("@bp.route('/employees/<int:i>/convert-role'", start)
    body = source[start:end]
    assert "not branch_obj.is_active" in body
    assert "not branch_obj.governorate.is_active" in body
    assert "branch_obj.governorate_id != submitted_gid" in body


def test_linked_user_email_conflict_is_checked_before_employee_mutation():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "employees.py").read_text(encoding="utf-8")
    start = source.index("def employee_edit(i):")
    end = source.index("@bp.route('/employees/<int:i>/convert-role'", start)
    body = source[start:end]
    check = body.index("البريد الإلكتروني مستخدم بالفعل لحساب آخر.")
    mutation = body.index("e.full_name = name")
    assert check < mutation
