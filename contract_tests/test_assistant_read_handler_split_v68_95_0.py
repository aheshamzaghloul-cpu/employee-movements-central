from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "employee_movements" / "assistant"


def read(name):
    return (ASSISTANT / name).read_text(encoding="utf-8")


def test_read_dispatcher_keeps_capability_gates_before_handler_dispatch():
    source = read("render_read.py")
    report_gate = "if intent in report_intents and not can('view_reports')"
    employee_gate = "if intent == 'employee_info' and not (can('manage_employees') or can('view_reports'))"
    assert report_gate in source
    assert employee_gate in source
    assert source.index(report_gate) < source.index("handlers = {")
    assert source.index(employee_gate) < source.index("handlers = {")


def test_read_intents_are_split_into_focused_handler_modules():
    dispatcher = read("render_read.py")
    movement = read("read_movement_handlers.py")
    directory = read("read_directory_handlers.py")
    required = {
        "movement_people_today": "handle_movement_people_today",
        "governorate_assignments_today": "handle_governorate_assignments_today",
        "employee_status": "handle_employee_status",
        "employee_movements": "handle_employee_movements",
        "governorate_employees": "handle_governorate_employees",
        "employee_info": "handle_employee_info",
        "branch_status": "handle_branch_status",
    }
    for intent, handler in required.items():
        assert handler in dispatcher, (intent, handler)
        assert handler in (movement + directory), (intent, handler)
    assert "def render_read(a):" in dispatcher
    assert len(dispatcher.splitlines()) < 100


def test_read_handlers_preserve_employee_and_movement_visibility_filtering():
    movement = read("read_movement_handlers.py")
    directory = read("read_directory_handlers.py")
    assert "if not visible_employee(e):" in movement
    assert "if not visible_employee(e):" in directory
    assert "visible_movement(m)" in movement
    assert "visible_movement(m)" in directory
    assert "can_read_movement_details = can('view_reports')" in directory
    assert "and not can_read_movement_details" in directory


def test_read_handlers_are_read_only_and_do_not_commit_mutations():
    for name in ("read_movement_handlers.py", "read_directory_handlers.py", "read_helpers.py"):
        source = read(name)
        for forbidden in ("db.session.add(", "db.session.commit(", "db.session.delete(", "db.session.bulk_save_objects("):
            assert forbidden not in source, (name, forbidden)


def test_render_helpers_remain_reexported_for_backward_compatibility():
    renderer = read("render_read.py")
    compatibility = read("render.py")
    for symbol in ("_load_candidate_records", "_latest_current_movements", "_movement_status_text", "_visible_branch", "employee_status_text", "render_branch_entry"):
        assert f"{symbol} as {symbol}" in renderer
        assert symbol in compatibility
