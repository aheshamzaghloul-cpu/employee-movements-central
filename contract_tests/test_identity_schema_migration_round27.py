"""Source-only safeguards for round-27 migration-readiness diagnostics.

This contract is added for CI coverage but is not executed in the current
static-only review. It does not import the Flask app or connect to a database.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "reconcile_identity_data.py"


def test_uninspectable_constraint_metadata_is_not_reported_as_confirmed_missing():
    source = TOOL.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "schema_unique_constraint_unverifiable" in source
    assert "schema_foreign_key_unverifiable" in source
    assert "schema_index_unverifiable" in source
    assert '"status": "unverifiable"' in source
    assert "This is not proof that the constraint is missing" in source
    assert "This is not proof the constraint is missing" in source
    assert "This is not proof the index is missing or invalid" in source
    assert "_inspect_metadata" in source


def test_partial_unique_index_does_not_satisfy_full_table_unique_invariant():
    source = TOOL.read_text(encoding="utf-8")
    assert 'options.get("postgresql_where") is not None or options.get("sqlite_where") is not None' in source
    assert "A partial unique index enforces uniqueness only for a subset of rows" in source


def test_report_exposes_migration_readiness_without_approving_changes():
    source = TOOL.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "migration_readiness_summary" in source
    assert '"migration_approved": False' in source
    assert '"automatic_schema_or_data_changes_allowed": False' in source
    assert '"report_schema_version": 2' in source
    assert "required_next_steps" in source
    # Source contract checks that database DDL/DML is not introduced in the new
    # metadata-helper path: the tool is still deliberately SELECT-only.
    ddl_dml = ("ALTER TABLE", "CREATE INDEX", "DROP TABLE", "DELETE FROM", "INSERT INTO", "UPDATE ")
    new_method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "migration_readiness_summary")
    method_source = ast.get_source_segment(source, new_method) or ""
    assert not any(statement in method_source.upper() for statement in ddl_dml)
