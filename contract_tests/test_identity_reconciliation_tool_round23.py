"""Source-only safety contract for the read-only reconciliation utility.

This contract is intentionally added but not executed during the user's
static-only review rounds. It does not connect to or inspect a live database.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "scripts" / "reconcile_identity_data.py"


def _source() -> str:
    return TOOL.read_text(encoding="utf-8")


def test_tool_requires_explicit_database_url_and_does_not_import_the_app():
    source = _source()
    tree = ast.parse(source)
    imports = []
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
        elif isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.append(node.func.attr)
    assert not any(name == "employee_movements" or name.startswith("employee_movements.") for name in imports)
    assert "create_app" not in calls
    assert 'os.getenv("DATABASE_URL", "").strip()' in source
    assert "local.db" in source  # documented as a forbidden implicit fallback


def test_database_sql_is_read_only_and_sqlite_requires_opt_in():
    source = _source()
    tree = ast.parse(source)
    statements = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "exec_driver_sql" or not node.args:
            continue
        value = node.args[0]
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            statements.append(value.value)
    assert "SET TRANSACTION READ ONLY" in statements
    assert "PRAGMA query_only = ON" in statements
    forbidden = ("INSERT", "UPDATE", "DELETE", "ALTER", "DROP", "CREATE", "TRUNCATE", "REPLACE")
    assert all(not statement.lstrip().upper().startswith(forbidden) for statement in statements)
    assert 'parser.add_argument("--allow-sqlite"' in source
    assert 'parser.add_argument("--include-values"' in source
    assert 'mode != "ro" or not uri_enabled' in source
    assert 'safe_url.database == ":memory:"' in source
    assert "لا يُسمح بإنشاء قاعدة فارغة تلقائيًا" in source


def test_identity_report_covers_code_alias_lifecycle_and_schema_findings():
    source = _source()
    for rule in (
        "duplicate_employee_code_normalized",
        "possible_code_collision_after_prefix_or_ocr_variants",
        "duplicate_user_email_casefold",
        "dangling_ticket_employee_code_alias_owner",
        "employee_branch_orphan",
        "deleted_employee_marked_active",
        "schema_unique_constraint_missing",
        "schema_foreign_key_missing",
    ):
        assert rule in source
    assert 'if self.include_values and values' in source
    assert "read_only_no_data_changes" in source
    assert "suppressed_by_severity" in source
    assert 'by_severity.update(self.suppressed_by_severity)' in source
    assert 'finding_count": len(self.findings) + self.suppressed_findings' in source


def test_current_release_manifest_points_to_full_round_32_candidate_and_gate_remains_closed():
    source = (ROOT / "contract_tests" / "test_release_manifest_consistency.py").read_text(encoding="utf-8")
    manifest = (ROOT / "REVIEW_MANIFEST.json").read_text(encoding="utf-8")
    assert "REVIEW_MANIFEST_v69.00.2_round32.json" in source
    assert "employee-movements-v69.00.2-full-source-upload-round32.zip" in source
    assert "NOT CLEARED FOR PRODUCTION" in manifest
