"""Source contract: alias audit attribution uses the authenticated user ID.

Added for CI regression protection; not executed during the static-only review.
"""
from pathlib import Path


def test_catalog_alias_creation_records_authenticated_creator():
    source_path = (
        Path(__file__).resolve().parents[1]
        / "employee_movements"
        / "blueprints"
        / "catalog.py"
    )
    source = source_path.read_text(encoding="utf-8")
    assert "created_by=me().id" in source
    assert "session.get('user_id')" not in source
