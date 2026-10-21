"""Source-only guards for safe user-account writes; not executed during static rounds."""
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_account_create_deduplicates_roles_and_normalizes_email_before_insert():
    source = (ROOT / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    create_body = source.split("def users():", 1)[1].split("@bp.route('/users/<int:i>/edit'", 1)[0]
    assert "selected_roles = list(dict.fromkeys(" in create_body
    assert "request.form.get('email', '').strip().lower()" in create_body
    assert "func.lower(func.trim(User.email)) == email" in create_body
    assert "except IntegrityError:" in create_body
    assert "db.session.rollback()" in create_body


def test_account_edit_deduplicates_roles_normalizes_email_and_rolls_back_integrity_conflicts():
    source = (ROOT / "employee_movements" / "blueprints" / "users.py").read_text(encoding="utf-8")
    edit_body = source.split("def user_edit(i):", 1)[1].split("@bp.post('/users/<int:i>/delete')", 1)[0]
    assert "selected = list(dict.fromkeys(" in edit_body
    assert "request.form.get('email', '').strip().lower()" in edit_body
    assert "func.lower(func.trim(User.email)) == email" in edit_body
    assert "except IntegrityError:" in edit_body
    assert "تعذر حفظ التعديلات بسبب تعارض في البيانات" in edit_body
