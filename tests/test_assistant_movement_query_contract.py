from pathlib import Path


def test_assistant_movement_lookup_is_centralized_and_bounded():
    root = Path(__file__).resolve().parents[1]
    manager = (root / "employee_movements/assistant/manager.py").read_text()
    helper = (root / "employee_movements/assistant/movement_queries.py").read_text()
    assert "resolve_movement_for_employee" in manager
    assert ".limit(2).all()" in helper
    assert "q.order_by(Movement.created_at.desc(), Movement.id.desc()).all()" not in manager
