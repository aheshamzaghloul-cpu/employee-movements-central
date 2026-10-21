from pathlib import Path


def _read(name):
    return (Path(__file__).resolve().parents[1] / "employee_movements" / "assistant" / name).read_text(encoding="utf-8")


def test_assistant_employee_search_is_db_narrowed():
    text = _read("tool_read_handlers.py")
    assert "employee_search_filter(" in text
    assert ".limit(max(limit * 5, 20))" in text
    assert "Employee.query.order_by(Employee.full_name).all()" not in text


def test_assistant_movement_search_joins_active_employee_branch_and_governorate_in_db():
    text = _read("tool_read_handlers.py")
    marker = 'if name == "search_movements":'
    section = text[text.index(marker):text.index('    return None', text.index(marker))]
    assert "Movement.query.join(Employee).join(Branch" in section
    assert "join(Governorate, Governorate.id == Branch.governorate_id)" in section
    assert "Branch.is_active == True" in section
    assert "Governorate.is_active == True" in section
    assert "if not visible_movement(m):" in section


def test_employee_status_uses_first_row():
    text = _read("read_helpers.py")
    marker = "def employee_status_text(e):"
    section = text[text.index(marker):]
    assert ".first()" in section
    assert ".all()" not in section


def test_assistant_branch_and_governorate_search_are_db_limited():
    text = _read("tool_read_handlers.py")
    branch_marker = 'if name == "search_branches":'
    gov_marker = 'if name == "search_governorates":'
    branch = text[text.index(branch_marker):text.index(gov_marker)]
    gov = text[text.index(gov_marker):text.index('if name == "search_movements":')]
    assert 'branch_search_filter(q, include_governorate=True)' in branch
    assert '.limit(limit).all()' in branch
    assert 'governorate_search_filter(q)' in gov
    assert 'Governorate.query.filter(Governorate.is_active == True)' in gov
    assert '.limit(limit).all()' in gov
    assert 'for b in Branch.query.filter_by(is_active=True)' not in branch
    assert 'for g in Governorate.query.filter_by(is_active=True)' not in gov


def test_governorate_assignment_report_avoids_employee_n_plus_one():
    text = _read("read_movement_handlers.py")
    marker = "def handle_governorate_assignments_today(a):"
    end = "\ndef handle_employee_status(a):"
    section = text[text.index(marker):text.index(end, text.index(marker))]
    assert 'Movement.query.join(Employee' in section
    assert 'current_assignment_for_employee(e.id' not in section
    assert 'for e in (' not in section



def test_branch_status_uses_one_current_movement_query():
    text = _read("read_directory_handlers.py")
    marker = "def handle_branch_status(a, intent):"
    end = "\ndef handle_employee_info(a):"
    section = text[text.index(marker):text.index(end, text.index(marker))]
    assert 'current_moves = {}' in section
    assert 'employee_status_text(e)' not in section
    assert 'current_assignment_for_employee(e.id)' not in section


def test_manager_name_and_lookup_searches_are_db_narrowed():
    root = Path(__file__).resolve().parents[1] / "employee_movements" / "assistant"
    manager = (root / "manager.py").read_text(encoding="utf-8")
    planning = (root / "manager_plan_structure.py").read_text(encoding="utf-8")
    executor = (root / "manager_execution.py").read_text(encoding="utf-8")
    resolvers = (root / "manager_resolvers.py").read_text(encoding="utf-8")
    assert 'User.full_name.ilike' in resolvers
    assert '.limit(limit)' in resolvers
    assert 'Lookup.name.ilike' in planning
    assert 'Lookup.query.filter_by(kind=kind).all()' not in manager
    assert 'EntryAssignmentBranch.branch_id.in_(branch_ids)' in executor


def test_render_employee_info_history_is_bounded_and_latest_fields_are_direct():
    text = _read("read_directory_handlers.py")
    marker = "def handle_employee_info(a):"
    section = text[text.index(marker):]
    assert '.limit(80).all()' in section
    assert 'visible_movement(m)' in section and '[:20]' in section
    assert "latest_by_kind[kind] = next((m for m in ms if m.movement_type == kind), None)" in section
    assert '.order_by(Movement.id.desc()).limit(80).all()' in section
    assert '.first()' not in section
    assert "filter_by(employee_id=e.id, is_active=True)\n            .order_by(Movement.id.desc())\n            .all()" not in section


def test_render_current_movement_reports_select_one_row_per_employee_in_db():
    text = _read("read_movement_handlers.py")
    assert "db.func.max(Movement.id).label('movement_id')" in text
    assert '.group_by(Movement.employee_id)' in text
    start = text.index("def handle_movement_people_today(a):")
    end = text.index("\ndef handle_governorate_assignments_today(a):", start)
    assert 'seen = set()' not in text[start:end]
