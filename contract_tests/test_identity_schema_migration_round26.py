"""Source-only migration-readiness contract for the read-only reconciliation tool.

This contract is added for CI but is intentionally not executed during this static
review round. It does not import the Flask app or connect to a database.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "employee_movements" / "models.py"
TOOL = ROOT / "scripts" / "reconcile_identity_data.py"


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _literal_assignment(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing literal policy declaration: {name}")


def _model_inventory():
    tree = ast.parse(MODELS.read_text(encoding="utf-8"))
    foreign_keys = set()
    delete_actions = {}
    uniques = set()
    for cls in (node for node in tree.body if isinstance(node, ast.ClassDef)):
        table = _snake(cls.name)
        for node in cls.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and getattr(node.value.func, "attr", None) == "Column":
                column = next((item.id for item in node.targets if isinstance(item, ast.Name)), None)
                if not column:
                    continue
                for keyword in node.value.keywords:
                    if keyword.arg == "unique" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                        uniques.add((table, (column,)))
                for arg in node.value.args:
                    if not (isinstance(arg, ast.Call) and getattr(arg.func, "attr", None) == "ForeignKey" and arg.args and isinstance(arg.args[0], ast.Constant)):
                        continue
                    target_table, target_column = arg.args[0].value.rsplit(".", 1)
                    key = (table, column, target_table, target_column)
                    foreign_keys.add(key)
                    ondelete = next((kw.value.value for kw in arg.keywords if kw.arg == "ondelete" and isinstance(kw.value, ast.Constant)), "NO ACTION")
                    delete_actions[key] = str(ondelete).upper()
            elif isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__table_args__" for target in node.targets):
                for call in ast.walk(node.value):
                    if isinstance(call, ast.Call) and getattr(call.func, "id", None) == "UniqueConstraint":
                        columns = tuple(arg.value for arg in call.args if isinstance(arg, ast.Constant) and isinstance(arg.value, str))
                        if columns:
                            uniques.add((table, columns))
    return foreign_keys, delete_actions, uniques


def test_reconciliation_tool_declares_every_model_foreign_key_and_delete_action():
    tool_tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    expected_fks = {tuple(item) for item in _literal_assignment(tool_tree, "EXPECTED_FOREIGN_KEYS")}
    expected_actions = {tuple(key): value for key, value in _literal_assignment(tool_tree, "EXPECTED_FOREIGN_KEY_ACTIONS").items()}
    model_fks, model_actions, _ = _model_inventory()
    assert expected_fks == model_fks
    assert expected_actions == model_actions


def test_reconciliation_tool_declares_every_model_unique_constraint():
    tool_tree = ast.parse(TOOL.read_text(encoding="utf-8"))
    expected_uniques = {(table, tuple(columns)) for table, columns in _literal_assignment(tool_tree, "EXPECTED_UNIQUES")}
    _, _, model_uniques = _model_inventory()
    assert expected_uniques == model_uniques


def test_reconciliation_reports_missing_indexes_and_orphan_data_without_ddl():
    source = TOOL.read_text(encoding="utf-8")
    for required in (
        "schema_index_missing_or_mismatched",
        "schema_foreign_key_delete_action_mismatch",
        "foreign_key_orphan_data",
        "foreign_key_orphan_scan_unverifiable",
        "SET TRANSACTION READ ONLY",
        "PRAGMA query_only = ON",
        'mode != "ro" or not uri_enabled',
    ):
        assert required in source
    tree = ast.parse(source)
    ddl = ("ALTER", "CREATE", "DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "REPLACE")
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "exec_driver_sql" or not node.args:
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            assert not value.value.lstrip().upper().startswith(ddl)
