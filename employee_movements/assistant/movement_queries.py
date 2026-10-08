"""Read-only movement lookup helpers for Basyouni.

These helpers deliberately return the same resolution states the manager expects:
unique movement, multiple matches, or no match. They do not perform authorization
or mutations; those remain in the assistant manager.
"""
from ..models import Movement


def resolve_movement_for_employee(employee_id, movement_type=None):
    q = Movement.query.filter_by(employee_id=int(employee_id), is_active=True)
    if movement_type:
        q = q.filter_by(movement_type=movement_type)
    rows = q.order_by(Movement.created_at.desc(), Movement.id.desc()).limit(2).all()
    if len(rows) == 1:
        return rows[0], False
    return None, len(rows) > 1
