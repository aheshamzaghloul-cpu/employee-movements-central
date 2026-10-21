from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STRUCTURE = ROOT / "employee_movements" / "blueprints" / "structure.py"
TEMPLATE = ROOT / "employee_movements" / "templates" / "structure.html"


def test_admin_role_and_assignment_counts_are_loaded_in_batches():
    source = STRUCTURE.read_text(encoding="utf-8")
    route = source[source.index("def structure():"):source.index("@bp.post('/entry-role/<int:employee_id>/branches')")]
    assert "UserRole.query.with_entities(UserRole.user_id, UserRole.role)" in route
    assert "roles_by_user.setdefault(user_id, set()).add(role)" in route
    assert "entry_assignment_links = (" in route
    assert "entry_assignments_with_branches = {link.entry_assignment_id for link in entry_assignment_links}" in route
    assert "EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).first()" not in route
    assert "UserGovernorate.query.filter_by(user_id=user.id).first()" not in route


def test_admin_template_does_not_receive_duplicate_unused_entry_picklists():
    source = STRUCTURE.read_text(encoding="utf-8")
    template = TEMPLATE.read_text(encoding="utf-8")
    route = source[source.index("def structure():"):source.index("@bp.post('/entry-role/<int:employee_id>/branches')")]
    assert "entry_supervisors=entry_supervisors" not in route
    assert "available_entry_employees=available_entry_employees" not in route
    assert "entry_supervisors" not in template
    assert "available_entry_employees" not in template


def test_admin_structure_route_no_longer_builds_an_unused_operational_tree():
    source = STRUCTURE.read_text(encoding="utf-8")
    route = source[source.index("def structure():"):source.index("@bp.post('/entry-role/<int:employee_id>/branches')")]
    assert "for governorate in governorates" not in route
    assert "tree=tree" not in route
    assert "admin_view=True" in route
    assert "if 'مسؤول التطبيق' not in roles(current):" in route
