from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = ROOT / "employee_movements" / "access.py"
CATALOG = ROOT / "employee_movements" / "blueprints" / "catalog.py"


def test_governorate_scope_has_a_single_semantic_guard():
    text = ACCESS.read_text()
    assert "def governorate_ok(i):" in text
    assert "return i is not None and int(i) in set(gids())" in text


def test_catalog_uses_central_governorate_scope_guard():
    text = CATALOG.read_text()
    assert "governorate_ok" in text
    assert "g.id not in set(gids())" not in text
    assert "x.governorate_id not in set(gids())" not in text


def test_operational_scope_remains_selected_governorate_only():
    text = ACCESS.read_text()
    assert "if selected and (not Governorate.query.filter_by(id=int(selected), is_active=True).first()):" in text
    assert "return [int(selected)] if selected else []" in text


def test_movement_employee_selection_rule_is_centralized():
    text = (ROOT / "employee_movements" / "access.py").read_text(encoding="utf-8")
    assert "def can_manage_movement_employee(e, movement_type=None):" in text
    movement_text = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    assert "can_manage_movement_employee(employee, movement_type)" in movement_text
    assert "global_employee_access" not in movement_text


def test_mission_print_permission_is_centralized():
    text = (ROOT / "employee_movements" / "access.py").read_text(encoding="utf-8")
    assert "def can_print_mission(m=None):" in text
    missions = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
    assert "can_print_mission(m)" in missions
    assert "def employee_branch_in_scope" not in missions


def test_assistant_movement_scope_uses_central_employee_and_destination_guards():
    access = ACCESS.read_text(encoding="utf-8")
    routes = (ROOT / "employee_movements" / "assistant" / "routes.py").read_text(encoding="utf-8")
    assert "def can_manage_movement_destination(branch, movement_type=None):" in access
    assert "can_manage_movement_employee(e, mt)" in routes
    assert "can_manage_movement_employee(e, a.get('movement_type'))" in routes
    assert "can_manage_movement_destination(dest, mt)" in routes
    assert "can_manage_movement_destination(dest, a.get('movement_type'))" in routes
    assert "global_actor = 'مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles()" not in routes


def test_branch_management_routes_allow_scoped_supervisor_but_not_central_manager():
    text = CATALOG.read_text(encoding='utf-8')
    for route in (
        "@bp.route('/branches', methods=['GET', 'POST'])",
        "@bp.post('/branches/<int:i>/edit')",
        "@bp.post('/branches/<int:i>/toggle')",
        "@bp.post('/branches/<int:i>/delete')",
    ):
        start = text.index(route)
        section = text[max(0, start - 100):start]
        assert "@only('مسؤول التطبيق', 'مشرف محافظة')" in section
        assert "Manager Application Support" not in section


def test_branch_cannot_be_reactivated_under_inactive_governorate():
    text = CATALOG.read_text(encoding='utf-8')
    start = text.index("def branch_toggle(i):")
    end = text.index("@bp.post('/branches/<int:i>/delete')", start)
    block = text[start:end]
    assert "if not x.is_active:" in block
    assert "if not parent or not parent.is_active:" in block
    assert "لا يمكن تفعيل الفرع قبل تفعيل المحافظة التابعة له." in block


def test_branch_management_routes_allow_scoped_supervisor_but_not_central_manager():
    text = CATALOG.read_text(encoding='utf-8')
    for route in (
        "@bp.route('/branches', methods=['GET', 'POST'])",
        "@bp.post('/branches/<int:i>/edit')",
        "@bp.post('/branches/<int:i>/toggle')",
        "@bp.post('/branches/<int:i>/delete')",
    ):
        start = text.index(route)
        section = text[max(0, start - 100):start]
        assert "@only('مسؤول التطبيق', 'مشرف محافظة')" in section
        assert "Manager Application Support" not in section


def test_branch_cannot_be_reactivated_under_inactive_governorate():
    text = CATALOG.read_text(encoding='utf-8')
    start = text.index("def branch_toggle(i):")
    end = text.index("@bp.post('/branches/<int:i>/delete')", start)
    block = text[start:end]
    assert "if not x.is_active:" in block
    assert "if not parent or not parent.is_active:" in block
    assert "لا يمكن تفعيل الفرع قبل تفعيل المحافظة التابعة له." in block


def test_movement_post_and_preflight_share_destination_scope_guard():
    movement_text = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    assert "can_manage_movement_destination" in movement_text.splitlines()[7]
    assert "if not can_manage_movement_destination(destination, movement_type):" in movement_text


def test_mission_employee_filter_is_available_for_global_all_governorates_search():
    template = (ROOT / "employee_movements" / "templates" / "mission_reports.html").read_text(encoding="utf-8")
    assert "{% if not employees %}disabled{% endif %}" in template
    assert "{% if not selected_branch %}disabled{% endif %}" not in template
