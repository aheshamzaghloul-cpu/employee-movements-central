from pathlib import Path


def _read(name):
    return (Path(__file__).resolve().parents[1] / "employee_movements" / "assistant" / name).read_text(encoding="utf-8")


def test_assistant_employee_search_is_db_narrowed():
    text = _read("agent.py")
    assert "Employee.full_name.ilike(pattern)" in text
    assert ".limit(max(limit * 5, 20))" in text
    assert "Employee.query.order_by(Employee.full_name).all()" not in text


def test_assistant_movement_search_pushes_branch_scope_to_db():
    text = _read("agent.py")
    assert "query = query.filter(Employee.branch_id.in_(allowed_branches))" in text


def test_employee_status_uses_first_row():
    text = _read("render.py")
    marker = "def employee_status_text(e):"
    section = text[text.index(marker):text.index("\ndef render_read", text.index(marker))]
    assert ".first()" in section
    assert ".all()" not in section


def test_assistant_branch_and_governorate_search_are_db_limited():
    text = _read("agent.py")
    branch_marker = 'if name == "search_branches":'
    gov_marker = 'if name == "search_governorates":'
    branch = text[text.index(branch_marker):text.index(gov_marker)]
    gov = text[text.index(gov_marker):text.index('if name == "search_movements":')]
    assert 'Branch.name.ilike(pattern)' in branch
    assert 'Branch.code.ilike(pattern)' in branch
    assert '.limit(limit).all()' in branch
    assert 'Governorate.name.ilike' in gov
    assert 'Governorate.id.in_(allowed)' in gov
    assert '.limit(limit).all()' in gov
    assert 'for b in Branch.query.filter_by(is_active=True)' not in branch
    assert 'for g in Governorate.query.filter_by(is_active=True)' not in gov


def test_governorate_assignment_report_avoids_employee_n_plus_one():
    text = _read("render.py")
    marker = "if intent == 'governorate_assignments_today':"
    end = "    if intent == 'governorate_employees':"
    section = text[text.index(marker):text.index(end, text.index(marker))]
    assert 'Movement.query.join(Employee' in section
    assert 'current_assignment_for_employee(e.id' not in section
    assert 'for e in (' not in section



def test_branch_status_uses_one_current_movement_query():
    text = _read("render.py")
    marker = "if intent in ('branch_status', 'branch_info'):"
    end = "        employees_html = ("
    section = text[text.index(marker):text.index(end, text.index(marker))]
    assert 'current_moves = {}' in section
    assert 'employee_status_text(e)' not in section
    assert 'current_assignment_for_employee(e.id)' not in section


def test_manager_name_and_lookup_searches_are_db_narrowed():
    root = Path(__file__).resolve().parents[1] / "employee_movements" / "assistant"
    manager = (root / "manager.py").read_text(encoding="utf-8")
    resolvers = (root / "manager_resolvers.py").read_text(encoding="utf-8")
    assert 'User.full_name.ilike' in resolvers
    assert '.limit(limit)' in resolvers
    assert 'Lookup.name.ilike' in manager
    assert 'Lookup.query.filter_by(kind=kind).all()' not in manager


def test_render_employee_info_history_is_bounded_and_latest_fields_are_direct():
    text = _read("render.py")
    marker = "if intent == 'employee_info':"
    end = "    if intent == 'employee_movements':"
    section = text[text.index(marker):text.index(end, text.index(marker))]
    assert '.limit(20)' in section
    assert "movement_type=kind" in section
    assert '.order_by(Movement.id.desc())' in section
    assert '.first()' in section
    assert "filter_by(employee_id=e.id, is_active=True)\n            .order_by(Movement.id.desc())\n            .all()" not in section


def test_render_current_movement_reports_select_one_row_per_employee_in_db():
    text = _read("render.py")
    assert "db.func.max(Movement.id).label('movement_id')" in text
    assert '.group_by(Movement.employee_id)' in text
    assert 'seen = set()' not in text[text.index("if intent == 'movement_people_today':"):text.index("if intent == 'governorate_employees':")]
