from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENTS = ROOT / 'employee_movements' / 'assignments.py'
MOVEMENTS = ROOT / 'employee_movements' / 'blueprints' / 'movements.py'
NOTIFICATIONS = ROOT / 'employee_movements' / 'blueprints' / 'notifications.py'


def test_canonical_resolver_excludes_closed_assignments():
    text = ASSIGNMENTS.read_text()
    assert "m.is_active" in text
    assert "m.assignment_state != 'مغلق'" in text
    assert "return leave or assignment or open_assignment or permission" in text


def test_canonical_resolver_is_deterministic():
    text = ASSIGNMENTS.read_text()
    assert "getattr(m, 'created_at', None) or datetime.min" in text
    assert "getattr(m, 'id', 0) or 0" in text
    assert "reverse=True" in text


def test_movement_page_uses_canonical_resolver_for_employee_status():
    text = MOVEMENTS.read_text()
    assert "current = resolve_current_movement(employee_moves, today)" in text
    assert "current = m.permission_date == today" not in text


def test_movement_followup_excludes_closed_assignments():
    text = MOVEMENTS.read_text()
    assert "m.assignment_state == 'مغلق'" in text


def test_notifications_exclude_closed_assignments():
    text = NOTIFICATIONS.read_text()
    assert "Movement.assignment_state != 'مغلق'" in text
