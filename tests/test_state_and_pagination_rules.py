from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from employee_movements.movement_state import (
    assignment_closed_filter,
    assignment_is_closed,
    assignment_open_filter,
)
from employee_movements.pagination import safe_page_number
from employee_movements.search import normalize_search_text

ROOT = Path(__file__).resolve().parents[1]


def test_legacy_closed_mission_flags_are_equivalent_in_python():
    assert assignment_is_closed(SimpleNamespace(assignment_state="مغلق", mission_state=None))
    assert assignment_is_closed(SimpleNamespace(assignment_state=None, mission_state="مغلقة"))
    assert assignment_is_closed(SimpleNamespace(assignment_state="مغلق", mission_state="مغلقة"))
    assert not assignment_is_closed(SimpleNamespace(assignment_state=None, mission_state=None))
    assert not assignment_is_closed(SimpleNamespace(assignment_state="ساري", mission_state="تحت التحرير"))
    assert not assignment_is_closed(None)


def test_sql_open_and_closed_predicates_match_legacy_state_semantics():
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "movement_state_cases",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("assignment_state", String),
        Column("mission_state", String),
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(table.insert(), [
            {"id": 1, "assignment_state": None, "mission_state": None},
            {"id": 2, "assignment_state": "ساري", "mission_state": "تحت التحرير"},
            {"id": 3, "assignment_state": "مغلق", "mission_state": "تحت التحرير"},
            {"id": 4, "assignment_state": None, "mission_state": "مغلقة"},
            {"id": 5, "assignment_state": "مغلق", "mission_state": "مغلقة"},
        ])
        open_ids = set(conn.execute(select(table.c.id).where(assignment_open_filter(table.c))).scalars())
        closed_ids = set(conn.execute(select(table.c.id).where(assignment_closed_filter(table.c))).scalars())
    assert open_ids == {1, 2}
    assert closed_ids == {3, 4, 5}
    assert open_ids.isdisjoint(closed_ids)


def test_safe_page_number_handles_hostile_and_arabic_digit_inputs():
    assert safe_page_number("3") == 3
    assert safe_page_number("٣") == 3
    assert safe_page_number(" 4 ", 3) == 3
    assert safe_page_number("0") == 1
    assert safe_page_number("1.5") == 1
    assert safe_page_number("9" * 5000) == 1
    assert safe_page_number("9999999999") == 1_000_000_000
    assert safe_page_number("bad", 17, default=6) == 6


def test_search_normalization_is_bounded_and_keeps_arabic_digit_normalization():
    assert normalize_search_text("أحمد ١٢٣") == normalize_search_text("احمد 123")
    assert len(normalize_search_text("x" * 20_000)) <= 256


def test_operational_queries_use_the_shared_open_assignment_predicate():
    files_and_markers = {
        "employee_movements/validation.py": "assignment_open_filter(Movement)",
        "employee_movements/blueprints/dashboard.py": "assignment_open_filter(Movement)",
        "employee_movements/blueprints/employees.py": "assignment_open_filter(Movement)",
        "employee_movements/blueprints/movements.py": "assignment_open_filter(Movement)",
        "employee_movements/assistant/read_helpers.py": "assignment_open_filter(Movement)",
        "employee_movements/services/mission_query.py": "assignment_open_filter(Movement)",
    }
    for relative, marker in files_and_markers.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert marker in text, f"Missing canonical assignment-state guard in {relative}"
