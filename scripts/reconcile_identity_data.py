#!/usr/bin/env python3
"""Generate a conservative, read-only identity/data-integrity reconciliation report.

Safety contract:
- Requires an explicit DATABASE_URL; never falls back to local.db.
- Supports PostgreSQL and SQLite only.
- PostgreSQL uses a READ ONLY transaction; SQLite enables PRAGMA query_only.
- Executes SELECTs/schema inspection only. It never changes, merges, deletes, or repairs rows.
- Values are omitted by default. --include-values opts into writing record values to the report.

Run from the repository root:
    DATABASE_URL='...' python scripts/reconcile_identity_data.py --output /safe/path/report.json

Optional CSV:
    DATABASE_URL='...' python scripts/reconcile_identity_data.py --output report.json --csv report.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import MetaData, Table, create_engine, inspect, select
from sqlalchemy.engine import make_url

MAX_FINDINGS = 50_000
DIGIT_MAP = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789"
)
FORMAT_CONTROLS = {chr(cp) for cp in (0x200E, 0x200F, *range(0x202A, 0x202F))}
DIACRITICS = {chr(cp) for cp in (*range(0x064B, 0x0660), 0x0670, *range(0x06D6, 0x06EE))}

TABLE_FIELDS: dict[str, tuple[str, ...]] = {
    "user": ("id", "username", "full_name", "email", "job_code", "is_active"),
    "employee": (
        "id", "employee_code", "user_id", "email", "full_name", "branch_id",
        "job_code", "is_active", "resignation_date", "rehire_date", "deleted_at",
    ),
    "branch": ("id", "governorate_id", "name", "code", "is_active"),
    "governorate": ("id", "name", "is_active"),
    "ticket_employee_code_alias": ("id", "employee_id", "alias_text", "normalized_alias"),
    "employee_name_alias": ("id", "employee_id", "alias_text", "normalized_alias"),
    "branch_name_alias": ("id", "branch_id", "alias_text", "normalized_alias"),
    "governorate_name_alias": ("id", "governorate_id", "alias_text", "normalized_alias"),
    "assistant_alias": ("id", "user_id", "employee_id", "alias_text", "normalized_alias"),
}

# These are schema invariants declared in the current SQLAlchemy models. This
# tool checks whether the connected database actually enforces them; it does not
# add any constraints or assume that db.create_all() altered an existing table.
EXPECTED_FOREIGN_KEYS: tuple[tuple[str, str, str, str], ...] = (
    # Full SQLAlchemy model-declared FK inventory. Keep this in sync with models.py;
    # absent constraints in a legacy schema are reported, never repaired automatically.
    ("user_permission", "user_id", "user", "id"),
    ("user_role", "user_id", "user", "id"),
    ("role_account", "user_id", "user", "id"),
    ("entry_assignment", "employee_id", "employee", "id"),
    ("entry_assignment", "supervisor_id", "user", "id"),
    ("entry_assignment_branch", "entry_assignment_id", "entry_assignment", "id"),
    ("entry_assignment_branch", "branch_id", "branch", "id"),
    ("branch", "governorate_id", "governorate", "id"),
    ("user_governorate", "user_id", "user", "id"),
    ("user_governorate", "governorate_id", "governorate", "id"),
    ("user_branch", "user_id", "user", "id"),
    ("user_branch", "branch_id", "branch", "id"),
    ("supervisor_entry", "supervisor_id", "user", "id"),
    ("supervisor_entry", "entry_id", "user", "id"),
    ("approval_delegation", "supervisor_id", "user", "id"),
    ("approval_delegation", "delegate_id", "user", "id"),
    ("approval_delegation", "governorate_id", "governorate", "id"),
    ("approval_delegation", "created_by", "user", "id"),
    ("approval_delegation", "revoked_by", "user", "id"),
    ("employee", "user_id", "user", "id"),
    ("employee", "branch_id", "branch", "id"),
    ("employee", "resignation_by", "user", "id"),
    ("employee", "deleted_by", "user", "id"),
    ("movement", "employee_id", "employee", "id"),
    ("movement", "destination_branch_id", "branch", "id"),
    ("movement", "deleted_by", "user", "id"),
    ("movement", "created_by", "user", "id"),
    ("movement", "modified_by", "user", "id"),
    ("movement", "reviewed_by", "user", "id"),
    ("movement", "approved_by", "user", "id"),
    ("movement", "approver_id", "user", "id"),
    ("movement", "closed_by", "user", "id"),
    ("mission_ticket_image", "movement_id", "movement", "id"),
    ("mission_ticket_image", "uploaded_by", "user", "id"),
    ("mission_ticket_image_draft", "uploaded_by", "user", "id"),
    ("mission_edit_request", "movement_id", "movement", "id"),
    ("mission_edit_request", "requested_by", "user", "id"),
    ("mission_edit_request", "reviewed_by", "user", "id"),
    ("movement_history", "movement_id", "movement", "id"),
    ("movement_history", "user_id", "user", "id"),
    ("audit", "user_id", "user", "id"),
    ("assistant_message", "user_id", "user", "id"),
    ("assistant_session_state", "user_id", "user", "id"),
    ("assistant_session_state", "context_employee_id", "employee", "id"),
    ("assistant_alias", "user_id", "user", "id"),
    ("assistant_alias", "employee_id", "employee", "id"),
    ("ticket_employee_code_alias", "employee_id", "employee", "id"),
    ("ticket_employee_code_alias", "created_by", "user", "id"),
    ("branch_name_alias", "branch_id", "branch", "id"),
    ("branch_name_alias", "created_by", "user", "id"),
    ("employee_name_alias", "employee_id", "employee", "id"),
    ("employee_name_alias", "created_by", "user", "id"),
    ("governorate_name_alias", "governorate_id", "governorate", "id"),
    ("governorate_name_alias", "created_by", "user", "id"),
)


# Model-declared ON DELETE semantics. Presence of an FK alone is insufficient:
# an incorrect CASCADE/RESTRICT/SET NULL action can delete or preserve the wrong records.
EXPECTED_FOREIGN_KEY_ACTIONS: dict[tuple[str, str, str, str], str] = {
    ('user_permission', 'user_id', 'user', 'id'): 'CASCADE',
    ('user_role', 'user_id', 'user', 'id'): 'CASCADE',
    ('role_account', 'user_id', 'user', 'id'): 'CASCADE',
    ('entry_assignment', 'employee_id', 'employee', 'id'): 'CASCADE',
    ('entry_assignment', 'supervisor_id', 'user', 'id'): 'RESTRICT',
    ('entry_assignment_branch', 'entry_assignment_id', 'entry_assignment', 'id'): 'CASCADE',
    ('entry_assignment_branch', 'branch_id', 'branch', 'id'): 'RESTRICT',
    ('branch', 'governorate_id', 'governorate', 'id'): 'RESTRICT',
    ('user_governorate', 'user_id', 'user', 'id'): 'CASCADE',
    ('user_governorate', 'governorate_id', 'governorate', 'id'): 'CASCADE',
    ('user_branch', 'user_id', 'user', 'id'): 'CASCADE',
    ('user_branch', 'branch_id', 'branch', 'id'): 'CASCADE',
    ('supervisor_entry', 'supervisor_id', 'user', 'id'): 'CASCADE',
    ('supervisor_entry', 'entry_id', 'user', 'id'): 'CASCADE',
    ('approval_delegation', 'supervisor_id', 'user', 'id'): 'RESTRICT',
    ('approval_delegation', 'delegate_id', 'user', 'id'): 'RESTRICT',
    ('approval_delegation', 'governorate_id', 'governorate', 'id'): 'RESTRICT',
    ('approval_delegation', 'created_by', 'user', 'id'): 'RESTRICT',
    ('approval_delegation', 'revoked_by', 'user', 'id'): 'SET NULL',
    ('employee', 'user_id', 'user', 'id'): 'SET NULL',
    ('employee', 'branch_id', 'branch', 'id'): 'RESTRICT',
    ('employee', 'resignation_by', 'user', 'id'): 'SET NULL',
    ('employee', 'deleted_by', 'user', 'id'): 'SET NULL',
    ('movement', 'employee_id', 'employee', 'id'): 'RESTRICT',
    ('movement', 'destination_branch_id', 'branch', 'id'): 'RESTRICT',
    ('movement', 'deleted_by', 'user', 'id'): 'SET NULL',
    ('movement', 'created_by', 'user', 'id'): 'RESTRICT',
    ('movement', 'modified_by', 'user', 'id'): 'SET NULL',
    ('movement', 'reviewed_by', 'user', 'id'): 'SET NULL',
    ('movement', 'approved_by', 'user', 'id'): 'SET NULL',
    ('movement', 'approver_id', 'user', 'id'): 'SET NULL',
    ('movement', 'closed_by', 'user', 'id'): 'SET NULL',
    ('mission_ticket_image', 'movement_id', 'movement', 'id'): 'CASCADE',
    ('mission_ticket_image', 'uploaded_by', 'user', 'id'): 'SET NULL',
    ('mission_ticket_image_draft', 'uploaded_by', 'user', 'id'): 'CASCADE',
    ('mission_edit_request', 'movement_id', 'movement', 'id'): 'CASCADE',
    ('mission_edit_request', 'requested_by', 'user', 'id'): 'RESTRICT',
    ('mission_edit_request', 'reviewed_by', 'user', 'id'): 'SET NULL',
    ('movement_history', 'movement_id', 'movement', 'id'): 'CASCADE',
    ('movement_history', 'user_id', 'user', 'id'): 'SET NULL',
    ('audit', 'user_id', 'user', 'id'): 'SET NULL',
    ('assistant_message', 'user_id', 'user', 'id'): 'CASCADE',
    ('assistant_session_state', 'user_id', 'user', 'id'): 'CASCADE',
    ('assistant_session_state', 'context_employee_id', 'employee', 'id'): 'SET NULL',
    ('assistant_alias', 'user_id', 'user', 'id'): 'CASCADE',
    ('assistant_alias', 'employee_id', 'employee', 'id'): 'CASCADE',
    ('ticket_employee_code_alias', 'employee_id', 'employee', 'id'): 'CASCADE',
    ('ticket_employee_code_alias', 'created_by', 'user', 'id'): 'SET NULL',
    ('branch_name_alias', 'branch_id', 'branch', 'id'): 'CASCADE',
    ('branch_name_alias', 'created_by', 'user', 'id'): 'SET NULL',
    ('employee_name_alias', 'employee_id', 'employee', 'id'): 'CASCADE',
    ('employee_name_alias', 'created_by', 'user', 'id'): 'SET NULL',
    ('governorate_name_alias', 'governorate_id', 'governorate', 'id'): 'CASCADE',
    ('governorate_name_alias', 'created_by', 'user', 'id'): 'SET NULL',
}


EXPECTED_UNIQUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("user", ("username",)),
    ("user", ("email",)),
    ("employee", ("employee_code",)),
    ("employee", ("user_id",)),
    ("employee", ("email",)),
    ("governorate", ("name",)),
    ("mission_ticket_image", ("movement_id",)),
    ("mission_ticket_image_draft", ("token",)),
    ("assistant_session_state", ("session_key_hash",)),
    ("user_permission", ("user_id", "permission")),
    ("user_role", ("user_id", "role")),
    ("role_account", ("user_id", "role")),
    ("entry_assignment", ("employee_id",)),
    ("entry_assignment_branch", ("entry_assignment_id", "branch_id")),
    ("user_governorate", ("user_id", "governorate_id")),
    ("user_branch", ("user_id", "branch_id")),
    ("supervisor_entry", ("entry_id", "supervisor_id")),
    ("approval_delegation", ("supervisor_id", "governorate_id", "starts_at", "ends_at")),
    ("assistant_alias", ("user_id", "normalized_alias")),
    ("ticket_employee_code_alias", ("normalized_alias",)),
    ("branch_name_alias", ("normalized_alias",)),
    ("employee_name_alias", ("normalized_alias",)),
    ("governorate_name_alias", ("normalized_alias",)),
    ("lookup", ("kind", "name")),
)

# Important indexes declared in models.py or bootstrap.py. A missing non-unique
# index is a performance/read-path concern; the pending-edit partial unique index
# is a correctness invariant and is reported as critical if absent.
EXPECTED_INDEXES: tuple[tuple[str, str, tuple[str, ...], bool], ...] = (
    ("branch", "ix_branch_governorate_active_code", ("governorate_id", "is_active", "code"), False),
    ("employee", "ix_employee_branch_active_name", ("branch_id", "is_active", "full_name"), False),
    ("employee", "ix_employee_job_code", ("job_code",), False),
    ("movement", "ix_movement_employee_active_from", ("employee_id", "is_active", "from_date"), False),
    ("movement", "ix_movement_active_created", ("is_active", "created_at"), False),
    ("movement", "ix_movement_type_active_from", ("movement_type", "is_active", "from_date"), False),
    ("mission_edit_request", "uq_mission_edit_request_pending", ("movement_id",), True),
    ("assistant_message", "ix_assistant_message_user_role_created", ("user_id", "active_role", "created_at"), False),
    ("assistant_session_state", "ix_assistant_session_state_user_updated", ("user_id", "updated_at"), False),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_database_url(raw: str) -> str:
    value = raw.strip()
    if value.startswith("postgres://"):
        return "postgresql+psycopg2://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg2://" + value[len("postgresql://"):]
    if value.startswith("postgresql+psycopg://"):
        return "postgresql+psycopg2://" + value[len("postgresql+psycopg://"):]
    return value


def normalize_search_text(value: Any) -> str:
    raw = str(value or "")[:1024]
    char_map = {
        **dict(zip("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")),
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي",
        "ة": "ه", "ئ": "ي", "ؤ": "و", "ـ": "",
    }
    text = unicodedata.normalize("NFKC", raw).translate(str.maketrans(char_map))
    text = "".join(ch for ch in text if ch not in DIACRITICS and ch not in FORMAT_CONTROLS)
    return re.sub(r"\s+", " ", text).strip().casefold()[:256]


def normalize_name(value: Any) -> str:
    text = normalize_search_text(value)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def strict_code_key(value: Any) -> str:
    """Conservative key for clear formatting variants; preserve punctuation/zeros."""
    return normalize_search_text(value)


def app_code_key(value: Any) -> str:
    """Approximate app lookup normalization; collisions remain review-only.

    The runtime lookup normalizer removes separators and may correct OCR O/0 and
    I/1 confusion for mostly numeric codes. We mirror that behavior only to flag
    possible collisions, never to declare identities equivalent automatically.
    """
    compact = "".join(ch for ch in normalize_search_text(value) if ch.isalnum())
    digits = sum(ch.isdigit() for ch in compact)
    if compact and digits >= min(4, max(1, len(compact) - 1)):
        compact = compact.translate(str.maketrans({"o": "0", "i": "1", "l": "1"}))
    return compact


def app_code_variants(value: Any) -> set[str]:
    key = app_code_key(value)
    if not key:
        return set()
    values = {key}
    if key.isdigit():
        if key.startswith("200") and len(key) > 3:
            values.add(key[3:])
        else:
            values.add("200" + key)
    return values


def branch_code_key(value: Any) -> str:
    key = str(value or "").replace("\u200f", "").replace("\u200e", "")
    key = key.translate(DIGIT_MAP).strip()
    if re.fullmatch(r"\d+\.0+", key):
        key = key.split(".", 1)[0]
    return re.sub(r"\s+", " ", key).casefold()


def email_key(value: Any) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def safe_int(value: Any) -> int | None:
    """Convert an identifier without crashing on SQLite's permissive typing."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


class Reconciler:
    def __init__(self, connection, include_values: bool = False):
        self.connection = connection
        self.include_values = include_values
        self.inspector = inspect(connection)
        self.table_names = set(self.inspector.get_table_names())
        self.tables: dict[str, list[dict[str, Any]]] = {}
        self.columns: dict[str, set[str]] = {}
        self.findings: list[dict[str, Any]] = []
        self.suppressed_findings = 0
        self.suppressed_by_severity: Counter[str] = Counter()
        self.suppressed_by_rule: Counter[str] = Counter()
        self.schema_checks: list[dict[str, Any]] = []
        self.scan_counts: dict[str, int] = {}
        # Inspector calls can be expensive and can fail for limited database roles.
        # Cache both successful metadata and failures so one failed inspection does
        # not turn into repeated queries or get misreported as a confirmed absence.
        self._metadata_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def _inspect_metadata(self, kind: str, table_name: str) -> dict[str, Any]:
        cache_key = (kind, table_name)
        if cache_key not in self._metadata_cache:
            method_name = {
                "unique_constraints": "get_unique_constraints",
                "indexes": "get_indexes",
                "foreign_keys": "get_foreign_keys",
            }.get(kind)
            if method_name is None:
                raise ValueError(f"Unsupported schema metadata kind: {kind}")
            try:
                rows = getattr(self.inspector, method_name)(table_name)
                self._metadata_cache[cache_key] = {"rows": rows, "error_type": None}
            except Exception as exc:
                # Keep only the exception class; driver errors can expose schema
                # names, SQL text, host details, or credentials in their messages.
                self._metadata_cache[cache_key] = {"rows": None, "error_type": type(exc).__name__}
        return self._metadata_cache[cache_key]

    def add(
        self,
        rule: str,
        severity: str,
        entity: str,
        field: str,
        record_ids: Iterable[Any],
        detail: str,
        *,
        key: str | None = None,
        values: dict[str, Any] | None = None,
    ) -> None:
        ids = sorted({str(value) for value in record_ids if value is not None})
        # The key is used only for grouping during analysis; do not persist hashes
        # of low-entropy personnel data because they can be dictionary-attacked.
        _ = key
        issue = {
            "rule": rule,
            "severity": severity,
            "entity": entity,
            "field": field,
            "record_ids": ids,
            "detail": detail,
        }
        if self.include_values and values:
            issue["values_by_record_id"] = {str(k): v for k, v in values.items() if v is not None}
        if len(self.findings) < MAX_FINDINGS:
            self.findings.append(issue)
        else:
            # Keep severity/rule tallies even when detail emission is capped. A
            # critical finding beyond the cap must not be hidden from the exit code.
            self.suppressed_findings += 1
            self.suppressed_by_severity[severity] += 1
            self.suppressed_by_rule[rule] += 1

    def load_tables(self) -> None:
        required_core = {"user", "employee", "branch", "governorate"}
        for name, requested_fields in TABLE_FIELDS.items():
            if name not in self.table_names:
                severity = "critical" if name in required_core else "warning"
                self.add(
                    "schema_table_missing", severity, "schema", name, [],
                    "Expected table is absent; related data checks were skipped.",
                )
                self.tables[name] = []
                self.columns[name] = set()
                self.scan_counts[name] = 0
                continue
            table = Table(name, MetaData(), autoload_with=self.connection)
            present_columns = {column.name for column in table.columns}
            self.columns[name] = present_columns
            chosen = [table.c[field] for field in requested_fields if field in present_columns]
            missing = sorted(set(requested_fields) - present_columns)
            for field in missing:
                if field == "rehire_date" or field == "deleted_at" or field == "resignation_date":
                    # Newer lifecycle columns may not exist on not-yet-migrated DBs.
                    severity = "critical"
                else:
                    severity = "critical" if name in required_core else "warning"
                self.add(
                    "schema_column_missing", severity, "schema", f"{name}.{field}", [],
                    "Expected column is absent; migrate the schema before relying on this check.",
                )
            if chosen:
                rows = self.connection.execute(select(*chosen).execution_options(stream_results=True)).mappings()
                self.tables[name] = [dict(row) for row in rows]
            else:
                self.tables[name] = []
            self.scan_counts[name] = len(self.tables[name])

    def audit_schema_constraints(self) -> None:
        for table_name, columns in EXPECTED_UNIQUES:
            if table_name not in self.table_names:
                # The missing-table finding is already emitted in load_tables when
                # it is an identity table; expected relation tables get an explicit finding.
                self.add(
                    "schema_unique_constraint_unverifiable", "critical", "schema",
                    f"{table_name}.{','.join(columns)}", [],
                    "Expected unique invariant cannot be verified because its table is absent.",
                )
                self.schema_checks.append({"table": table_name, "columns": list(columns), "status": "table_missing"})
                continue
            constraint_meta = self._inspect_metadata("unique_constraints", table_name)
            index_meta = self._inspect_metadata("indexes", table_name)
            if constraint_meta["rows"] is None or index_meta["rows"] is None:
                error_types = sorted({
                    value for value in (constraint_meta.get("error_type"), index_meta.get("error_type"))
                    if value
                })
                self.schema_checks.append({
                    "table": table_name,
                    "columns": list(columns),
                    "status": "unverifiable",
                    "inspection_error_types": error_types,
                })
                self.add(
                    "schema_unique_constraint_unverifiable", "warning", "schema",
                    f"{table_name}.{','.join(columns)}", [],
                    "Could not inspect unique-constraint metadata with this database role. This is not proof that the constraint is missing; retry with an approved read-only role that can inspect schema metadata.",
                )
                continue

            actual: list[set[str]] = []
            for item in constraint_meta["rows"]:
                actual.append(set(item.get("column_names") or []))
            for item in index_meta["rows"]:
                if not item.get("unique"):
                    continue
                options = item.get("dialect_options") or {}
                # A partial unique index enforces uniqueness only for a subset of
                # rows and cannot satisfy a model-wide UNIQUE invariant.
                if options.get("postgresql_where") is not None or options.get("sqlite_where") is not None:
                    continue
                actual.append(set(item.get("column_names") or []))
            expected = set(columns)
            found = expected in actual
            check = {
                "table": table_name,
                "columns": list(columns),
                "status": "present" if found else "missing",
            }
            self.schema_checks.append(check)
            if not found:
                self.add(
                    "schema_unique_constraint_missing", "critical", "schema",
                    f"{table_name}.{','.join(columns)}", [],
                    "The inspected database does not expose the full-table unique constraint/index declared by the model. Review duplicate data first, then plan a reversible migration.",
                )

    def audit_schema_indexes(self) -> None:
        for table_name, index_name, columns, unique in EXPECTED_INDEXES:
            status = "present"
            inspection_error_type = None
            if table_name not in self.table_names:
                status = "table_missing"
                indexes = []
            else:
                index_meta = self._inspect_metadata("indexes", table_name)
                if index_meta["rows"] is None:
                    indexes = []
                    status = "unverifiable"
                    inspection_error_type = index_meta.get("error_type")
                else:
                    indexes = index_meta["rows"]
                    inspection_error_type = None
                match = next((item for item in indexes if item.get("name") == index_name), None)
                if status != "unverifiable":
                    if match is None:
                        status = "missing"
                    elif tuple(match.get("column_names") or ()) != columns or bool(match.get("unique")) != unique:
                        status = "definition_mismatch"
                    elif index_name == "uq_mission_edit_request_pending":
                        options = match.get("dialect_options") or {}
                        predicate = options.get("postgresql_where") or options.get("sqlite_where")
                        predicate_text = str(predicate or "").casefold()
                        if "status" not in predicate_text or "قيد المراجعة" not in predicate_text:
                            status = "definition_mismatch"
                    if status == "present" and self.connection.dialect.name == "postgresql":
                        try:
                            valid_row = self.connection.execute(
                                text("""
                                    SELECT i.indisvalid, i.indisready
                                    FROM pg_class idx
                                    JOIN pg_index i ON i.indexrelid = idx.oid
                                    JOIN pg_class tbl ON tbl.oid = i.indrelid
                                    WHERE idx.relname = :index_name
                                      AND tbl.relname = :table_name
                                      AND idx.relnamespace = tbl.relnamespace
                                      AND pg_table_is_visible(tbl.oid)
                                """),
                                {"index_name": index_name, "table_name": table_name},
                            ).first()
                            if valid_row is None:
                                # The index is present in SQLAlchemy's inspector but
                                # is not visible in the catalog query. This can be a
                                # permissions/schema-visibility issue, not proof of invalidity.
                                status = "unverifiable"
                            elif not bool(valid_row[0]) or not bool(valid_row[1]):
                                status = "invalid"
                        except Exception as exc:
                            status = "unverifiable"
                            inspection_error_type = type(exc).__name__
            self.schema_checks.append({
                "table": table_name,
                "index": index_name,
                "columns": list(columns),
                "unique": unique,
                "status": status,
                **({"inspection_error_type": inspection_error_type} if table_name in self.table_names and status == "unverifiable" and inspection_error_type else {}),
            })
            if status == "present":
                continue
            if status == "unverifiable":
                self.add(
                    "schema_index_unverifiable", "warning", "schema", f"{table_name}.{index_name}", [],
                    "Could not fully verify this index with the current schema-inspection permissions. This is not proof the index is missing or invalid; retry with an approved read-only role that can inspect index metadata.",
                )
                continue
            severity = "critical" if index_name == "uq_mission_edit_request_pending" else "warning"
            self.add(
                "schema_index_missing_or_mismatched", severity, "schema", f"{table_name}.{index_name}", [],
                ("The one-pending-edit-request-per-mission partial unique index is confirmed missing, invalid, or different from policy; "
                 "review duplicate pending rows and create a reversible migration." if severity == "critical" else
                 "A performance index declared by the model/bootstrap is confirmed missing or differs from the expected name, columns, or uniqueness; review query plans before adding it."),
            )

    def grouped_findings(
        self, rows: list[dict[str, Any]], *, value_getter, key_fn, rule: str,
        severity: str, entity: str, field: str, detail: str,
        scope_fn=None, value_label: str | None = None,
    ) -> None:
        groups: dict[tuple[Any, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = value_getter(row)
            key = key_fn(value)
            if not key:
                continue
            scope = scope_fn(row) if scope_fn else None
            groups[(scope, key)].append(row)
        for (_scope, key), group in groups.items():
            ids = [row.get("id") for row in group]
            unique_ids = {str(row_id) for row_id in ids if row_id is not None}
            if len(unique_ids) < 2:
                continue
            values = None
            if self.include_values:
                values = {row.get("id"): value_getter(row) for row in group}
            self.add(rule, severity, entity, field, ids, detail, key=key, values=values)

    def audit_identity_codes(self) -> None:
        employees = self.tables.get("employee", [])
        self.grouped_findings(
            employees, value_getter=lambda row: row.get("employee_code"), key_fn=strict_code_key,
            rule="duplicate_employee_code_normalized", severity="critical", entity="employee",
            field="employee_code", detail="Multiple employee rows share the same conservative normalized employee_code.",
        )
        self.grouped_findings(
            employees, value_getter=lambda row: row.get("job_code"), key_fn=strict_code_key,
            rule="duplicate_job_code_normalized", severity="review", entity="employee",
            field="job_code", detail="Multiple employee rows share the same normalized job_code; confirm whether this field is meant to be unique before changing data.",
        )
        self.grouped_findings(
            self.tables.get("user", []), value_getter=lambda row: row.get("email"), key_fn=email_key,
            rule="duplicate_user_email_casefold", severity="critical", entity="user",
            field="email", detail="User emails collide after trim/case normalization although an exact-value UNIQUE constraint may allow this.",
        )
        self.grouped_findings(
            employees, value_getter=lambda row: row.get("email"), key_fn=email_key,
            rule="duplicate_employee_email_casefold", severity="critical", entity="employee",
            field="email", detail="Employee emails collide after trim/case normalization although an exact-value UNIQUE constraint may allow this.",
        )

        # Strict aliases duplicated in the alias catalogue.
        aliases = self.tables.get("ticket_employee_code_alias", [])
        employee_ids = {parsed for row in employees if (parsed := safe_int(row.get("id"))) is not None}
        for alias in aliases:
            alias_id = alias.get("id")
            owner_id = alias.get("employee_id")
            if safe_int(owner_id) is None or safe_int(owner_id) not in employee_ids:
                self.add(
                    "dangling_ticket_employee_code_alias_owner", "critical",
                    "ticket_employee_code_alias", "employee_id", [alias_id, owner_id],
                    "Confirmed personnel-code alias points to a missing employee record.",
                )
            raw_alias = alias.get("alias_text")
            stored_key = str(alias.get("normalized_alias") or "").strip()
            expected_key = app_code_key(raw_alias)
            if raw_alias and not stored_key:
                self.add(
                    "empty_ticket_employee_code_alias_key", "warning",
                    "ticket_employee_code_alias", "normalized_alias", [alias_id, owner_id],
                    "Confirmed personnel-code alias has no stored normalized key.",
                )
            if raw_alias and stored_key and expected_key and stored_key != expected_key:
                self.add(
                    "confirmed_employee_code_alias_normalization_mismatch", "review",
                    "ticket_employee_code_alias", "normalized_alias", [alias.get("id"), alias.get("employee_id")],
                    "Stored normalized_alias differs from the current application's normalized alias_text; do not rewrite it automatically.",
                    key=expected_key,
                    values=({alias.get("id"): {"alias_text": raw_alias, "normalized_alias": stored_key}} if self.include_values else None),
                )
        self.grouped_findings(
            aliases, value_getter=lambda row: row.get("normalized_alias"), key_fn=app_code_key,
            rule="duplicate_confirmed_employee_code_alias", severity="critical", entity="ticket_employee_code_alias",
            field="normalized_alias", detail="Confirmed alternate personnel-code aliases collide after the application's code normalization.",
        )

        code_owners: dict[str, set[int]] = defaultdict(set)
        for row in employees:
            employee_id = row.get("id")
            employee_key = safe_int(employee_id)
            if employee_key is None:
                continue
            for field in ("employee_code", "job_code"):
                raw = row.get(field)
                for variant in app_code_variants(raw):
                    code_owners[variant].add(employee_key)
        for row in aliases:
            employee_id = row.get("employee_id")
            raw = row.get("normalized_alias") or row.get("alias_text")
            employee_key = safe_int(employee_id)
            if employee_key is None or not raw:
                continue
            for variant in app_code_variants(raw):
                owners = code_owners.get(variant, set()) - {employee_key}
                if owners:
                    self.add(
                        "employee_code_alias_shadows_other_employee_code", "critical",
                        "ticket_employee_code_alias", "normalized_alias",
                        [row.get("id"), employee_id, *owners],
                        "A confirmed code alias matches an official employee_code/job_code owned by a different employee under runtime lookup variants.",
                        key=variant,
                        values=({row.get("id"): row.get("alias_text")} if self.include_values else None),
                    )

        # Detect prefix/OCR lookup collisions that may be distinct in raw storage.
        # These are review-only because the compatibility variants are not proof of identity.
        by_lookup_variant: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
        for row in employees:
            emp_id = safe_int(row.get("id"))
            if emp_id is None:
                continue
            for field in ("employee_code", "job_code"):
                raw = row.get(field)
                strict = strict_code_key(raw)
                for variant in app_code_variants(raw):
                    by_lookup_variant[variant].append((emp_id, field, str(raw or ""), strict))
        seen_variant_issues: set[tuple[str, tuple[int, ...]]] = set()
        for variant, group in by_lookup_variant.items():
            owners = {entry[0] for entry in group}
            strict_keys = {entry[3] for entry in group if entry[3]}
            if len(owners) < 2 or len(strict_keys) < 2:
                continue
            ids = tuple(sorted(owners))
            marker = (variant, ids)
            if marker in seen_variant_issues:
                continue
            seen_variant_issues.add(marker)
            self.add(
                "possible_code_collision_after_prefix_or_ocr_variants", "review", "employee",
                "employee_code/job_code", ids,
                "Different official code values share a lookup variant (including legacy 200-prefix or OCR normalization). Confirm the policy manually; do not merge automatically.",
                key=variant,
                values=({str(i): [entry[2] for entry in group if entry[0] == i] for i in ids} if self.include_values else None),
            )

        # A strict key can differ while the application/OCR key overlaps. Keep this review-only.
        by_runtime_key: dict[str, list[tuple[int, str, str, str]]] = defaultdict(list)
        for row in employees:
            emp_id = safe_int(row.get("id"))
            if emp_id is None:
                continue
            for field in ("employee_code", "job_code"):
                raw = row.get(field)
                strict = strict_code_key(raw)
                runtime = app_code_key(raw)
                if runtime:
                    by_runtime_key[runtime].append((emp_id, field, str(raw or ""), strict))
        emitted: set[tuple[str, tuple[int, ...]]] = set()
        for runtime, group in by_runtime_key.items():
            owners = {entry[0] for entry in group}
            strict_keys = {entry[3] for entry in group}
            if len(owners) < 2 or len(strict_keys) < 2:
                continue
            ids = tuple(sorted(owners))
            stamp = (runtime, ids)
            if stamp in emitted:
                continue
            emitted.add(stamp)
            self.add(
                "possible_code_collision_after_ocr_normalization", "review", "employee",
                "employee_code/job_code", ids,
                "Different raw code spellings collapse to the same runtime/OCR lookup key. Review manually; no identities were merged.",
                key=runtime,
                values=({str(i): [entry[2] for entry in group if entry[0] == i] for i in ids} if self.include_values else None),
            )

    def audit_assistant_aliases(self) -> None:
        users = {parsed for row in self.tables.get("user", []) if (parsed := safe_int(row.get("id"))) is not None}
        employees = {parsed for row in self.tables.get("employee", []) if (parsed := safe_int(row.get("id"))) is not None}
        for alias in self.tables.get("assistant_alias", []):
            alias_id = alias.get("id")
            user_id, employee_id = alias.get("user_id"), alias.get("employee_id")
            if safe_int(user_id) is None or safe_int(user_id) not in users:
                self.add("assistant_alias_user_orphan", "critical", "assistant_alias", "user_id", [alias_id, user_id], "Private assistant alias points to a missing user account.")
            if safe_int(employee_id) is None or safe_int(employee_id) not in employees:
                self.add("assistant_alias_employee_orphan", "critical", "assistant_alias", "employee_id", [alias_id, employee_id], "Private assistant alias points to a missing employee record.")
            raw_alias = alias.get("alias_text")
            stored_key = str(alias.get("normalized_alias") or "").strip()
            expected_key = normalize_name(raw_alias)
            if raw_alias and not stored_key:
                self.add("assistant_alias_key_empty", "warning", "assistant_alias", "normalized_alias", [alias_id], "Private alias text exists but its stored normalized key is empty.")
            elif raw_alias and stored_key and expected_key and stored_key != expected_key:
                self.add("assistant_alias_key_mismatch", "review", "assistant_alias", "normalized_alias", [alias_id, user_id, employee_id], "Private alias stored key differs from the normalized alias text; do not rewrite it automatically.", values=({alias_id: {"alias_text": raw_alias, "normalized_alias": stored_key}} if self.include_values else None))

    def audit_catalogs(self) -> None:
        governors = self.tables.get("governorate", [])
        branches = self.tables.get("branch", [])
        employees = self.tables.get("employee", [])
        gov_aliases = self.tables.get("governorate_name_alias", [])
        branch_aliases = self.tables.get("branch_name_alias", [])
        employee_aliases = self.tables.get("employee_name_alias", [])
        gov_by_id = {parsed: row for row in governors if (parsed := safe_int(row.get("id"))) is not None}
        branch_by_id = {parsed: row for row in branches if (parsed := safe_int(row.get("id"))) is not None}
        employee_by_id = {parsed: row for row in employees if (parsed := safe_int(row.get("id"))) is not None}

        self.grouped_findings(
            governors, value_getter=lambda row: row.get("name"), key_fn=normalize_name,
            rule="duplicate_governorate_name_normalized", severity="critical", entity="governorate",
            field="name", detail="Governorates share the same normalized canonical name.",
        )
        self.grouped_findings(
            branches, value_getter=lambda row: row.get("name"), key_fn=normalize_name,
            scope_fn=lambda row: row.get("governorate_id"),
            rule="duplicate_branch_name_within_governorate", severity="critical", entity="branch",
            field="name", detail="Branches in one governorate share the same normalized canonical name.",
        )
        self.grouped_findings(
            branches, value_getter=lambda row: row.get("code"), key_fn=branch_code_key,
            scope_fn=lambda row: row.get("governorate_id"),
            rule="duplicate_branch_code_within_governorate", severity="critical", entity="branch",
            field="code", detail="Branch codes collide within a governorate after the application's conservative branch-code normalization.",
        )
        self.grouped_findings(
            employees, value_getter=lambda row: row.get("full_name"), key_fn=normalize_name,
            scope_fn=lambda row: row.get("branch_id"),
            rule="duplicate_employee_name_within_branch", severity="review", entity="employee",
            field="full_name", detail="Employee names collide within a branch. Names are not global identifiers; do not merge records automatically.",
        )

        # Canonical name maps support alias-shadow checks. Canonical branch names are
        # scope-local for duplicate policy, but an alias may not shadow a different
        # branch's official name according to the current shared validation policy.
        def audit_aliases(alias_rows, owner_field, entity, value_field, key_fn, canonical_owner_map, global_shadow, normalized_field="normalized_alias"):
            self.grouped_findings(
                alias_rows, value_getter=lambda row: row.get(normalized_field), key_fn=key_fn,
                rule=f"duplicate_{entity}_alias_normalized", severity="critical", entity=entity,
                field=normalized_field, detail="Multiple alias rows share the same normalized alias value.",
            )
            # When the owner entity's table naming differs from its model label.
            for alias in alias_rows:
                alias_id, owner_id = alias.get("id"), alias.get(owner_field)
                owner_key = safe_int(owner_id)
                if owner_key is None or owner_key not in canonical_owner_map.get("ids", set()):
                    self.add(
                        f"dangling_{entity}_alias_owner", "critical", f"{entity}_alias", owner_field,
                        [alias_id, owner_id], "Alias points to an owner record that is absent from the current entity table.",
                    )
                    continue
                key = key_fn(alias.get(normalized_field) or alias.get(value_field))
                if not key:
                    self.add(
                        f"empty_{entity}_alias_key", "warning", f"{entity}_alias", normalized_field,
                        [alias_id, owner_id], "Alias has no usable normalized key.",
                    )
                    continue
                other_ids = set(canonical_owner_map.get("by_key", {}).get(key, set())) - {owner_key}
                if global_shadow and other_ids:
                    self.add(
                        f"{entity}_alias_shadows_canonical_name", "critical", f"{entity}_alias",
                        normalized_field, [alias_id, owner_id, *other_ids],
                        "Confirmed alias collides with another record's official name under the current lookup normalization.",
                        key=key,
                        values=({alias_id: alias.get(value_field)} if self.include_values else None),
                    )

        # Each owner map carries explicit IDs and key -> IDs to report orphan and shadow issues.
        gov_owner_map = {"ids": set(gov_by_id), "by_key": defaultdict(set)}
        for row in governors:
            row_id = safe_int(row.get("id"))
            if row_id is not None and normalize_name(row.get("name")):
                gov_owner_map["by_key"][normalize_name(row.get("name"))].add(row_id)
        branch_owner_map = {"ids": set(branch_by_id), "by_key": defaultdict(set)}
        for row in branches:
            row_id = safe_int(row.get("id"))
            if row_id is not None and normalize_name(row.get("name")):
                branch_owner_map["by_key"][normalize_name(row.get("name"))].add(row_id)
        employee_owner_map = {"ids": set(employee_by_id), "by_key": defaultdict(set)}
        for row in employees:
            row_id = safe_int(row.get("id"))
            if row_id is not None and normalize_name(row.get("full_name")):
                employee_owner_map["by_key"][normalize_name(row.get("full_name"))].add(row_id)

        audit_aliases(gov_aliases, "governorate_id", "governorate", "alias_text", normalize_name, gov_owner_map, True)
        audit_aliases(branch_aliases, "branch_id", "branch", "alias_text", normalize_name, branch_owner_map, True)
        audit_aliases(employee_aliases, "employee_id", "employee", "alias_text", normalize_name, employee_owner_map, True)

        # Stored alias keys must correspond to their display text. A mismatch
        # can make the displayed alias resolve differently than its stored key.
        for alias_rows, entity, value_field, key_field, key_fn in (
            (gov_aliases, "governorate", "alias_text", "normalized_alias", normalize_name),
            (branch_aliases, "branch", "alias_text", "normalized_alias", normalize_name),
            (employee_aliases, "employee", "alias_text", "normalized_alias", normalize_name),
        ):
            for alias in alias_rows:
                raw_value = alias.get(value_field)
                stored_key = str(alias.get(key_field) or "").strip()
                expected_key = key_fn(raw_value)
                if raw_value and not stored_key:
                    self.add(
                        f"empty_{entity}_alias_key", "warning", f"{entity}_alias", key_field,
                        [alias.get("id")], "Alias text exists but its stored normalized key is empty.",
                    )
                if raw_value and stored_key and expected_key and stored_key != expected_key:
                    self.add(
                        f"{entity}_alias_normalization_mismatch", "review", f"{entity}_alias", key_field,
                        [alias.get("id"), alias.get({"governorate": "governorate_id", "branch": "branch_id", "employee": "employee_id"}[entity])],
                        "Stored normalized_alias differs from the normalized alias_text; keep both values intact until reviewed.",
                        key=expected_key,
                        values=({alias.get("id"): {"alias_text": raw_value, "normalized_alias": stored_key}} if self.include_values else None),
                    )

        # Cross-catalog scope and referential checks.
        for branch in branches:
            branch_id = branch.get("id")
            raw_gov_id = branch.get("governorate_id")
            gov_id = safe_int(raw_gov_id)
            if raw_gov_id is None:
                self.add("branch_governorate_missing_reference", "critical", "branch", "governorate_id", [branch_id], "Branch has no governorate_id reference.")
            elif gov_id is None:
                self.add("branch_governorate_invalid_reference", "critical", "branch", "governorate_id", [branch_id, raw_gov_id], "Branch governorate_id is not a usable integer identifier.")
            elif gov_id not in gov_by_id:
                self.add("branch_governorate_orphan", "critical", "branch", "governorate_id", [branch_id, gov_id], "Branch references a missing governorate.")
            elif gov_id is not None and gov_id in gov_by_id and not bool(gov_by_id[gov_id].get("is_active", True)) and bool(branch.get("is_active", True)):
                self.add("active_branch_under_inactive_governorate", "review", "branch", "is_active", [branch_id, gov_id], "Branch is active while its governorate is inactive.")
        for employee in employees:
            emp_id, raw_branch_id = employee.get("id"), employee.get("branch_id")
            branch_id = safe_int(raw_branch_id)
            branch = branch_by_id.get(branch_id) if branch_id is not None else None
            if raw_branch_id is not None and branch_id is None:
                self.add("employee_branch_invalid_reference", "critical", "employee", "branch_id", [emp_id, raw_branch_id], "Employee branch_id is not a usable integer identifier.")
            elif not branch:
                self.add("employee_branch_orphan", "critical", "employee", "branch_id", [emp_id, raw_branch_id], "Employee references a missing branch.")
            elif bool(employee.get("is_active", True)) and not bool(branch.get("is_active", True)):
                self.add("active_employee_under_inactive_branch", "review", "employee", "branch_id", [emp_id, branch_id], "Employee is active while the assigned branch is inactive.")
            else:
                gov_id = safe_int(branch.get("governorate_id"))
                if gov_id is not None and gov_id in gov_by_id and not bool(gov_by_id[gov_id].get("is_active", True)) and bool(employee.get("is_active", True)):
                    self.add("active_employee_under_inactive_governorate", "review", "employee", "branch_id", [emp_id, branch_id, gov_id], "Employee is active under an inactive governorate.")

    def audit_lifecycle_and_accounts(self) -> None:
        employees = self.tables.get("employee", [])
        users = self.tables.get("user", [])
        user_by_id = {parsed: row for row in users if (parsed := safe_int(row.get("id"))) is not None}
        employee_by_id = {parsed: row for row in employees if (parsed := safe_int(row.get("id"))) is not None}

        for row in employees:
            emp_id = row.get("id")
            active = bool(row.get("is_active", True))
            if row.get("deleted_at") is not None and active:
                self.add("deleted_employee_marked_active", "critical", "employee", "is_active/deleted_at", [emp_id], "Employee has deleted_at set but is_active remains true.")
            if row.get("resignation_date") is not None and active:
                self.add("resigned_employee_marked_active", "review", "employee", "is_active/resignation_date", [emp_id], "Employee has a resignation date but is_active remains true; confirm lifecycle policy.")
            user_id = safe_int(row.get("user_id"))
            if row.get("user_id") is not None and (user_id is None or user_id not in user_by_id):
                self.add("employee_user_link_orphan", "critical", "employee", "user_id", [emp_id, row.get("user_id")], "Employee points to a missing or invalid user account identifier.")
            if active and not str(row.get("employee_code") or "").strip() and not str(row.get("job_code") or "").strip():
                self.add("active_employee_without_any_code", "review", "employee", "employee_code/job_code", [emp_id], "Active employee has neither employee_code nor job_code; confirm the approved identity policy.")

        self.grouped_findings(
            employees, value_getter=lambda row: row.get("user_id"),
            key_fn=lambda v: str(v).strip() if v is not None else "",
            rule="multiple_employees_linked_to_user", severity="critical", entity="employee",
            field="user_id", detail="More than one employee row is linked to the same user account.",
        )
        for employee in employees:
            uid = safe_int(employee.get("user_id"))
            if uid is None or uid not in user_by_id:
                continue
            user = user_by_id[uid]
            eid = employee.get("id")
            emp_email, user_email = email_key(employee.get("email")), email_key(user.get("email"))
            if emp_email and user_email and emp_email != user_email:
                self.add("linked_account_email_mismatch", "review", "employee/user", "email", [eid, uid], "Linked employee and user account have different normalized emails; do not sync automatically.")
            emp_code, user_code = strict_code_key(employee.get("job_code")), strict_code_key(user.get("job_code"))
            if emp_code and user_code and emp_code != user_code:
                self.add("linked_account_job_code_mismatch", "review", "employee/user", "job_code", [eid, uid], "Linked employee and user account have different job_code values; confirm whether synchronization is expected.")
            emp_name, user_name = normalize_name(employee.get("full_name")), normalize_name(user.get("full_name"))
            if emp_name and user_name and emp_name != user_name:
                self.add("linked_account_name_mismatch", "info", "employee/user", "full_name", [eid, uid], "Linked employee and user account names differ after normalization.")

        employee_email_owners: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for employee in employees:
            key = email_key(employee.get("email"))
            if key:
                employee_email_owners[key].append(employee)
        for user in users:
            key = email_key(user.get("email"))
            if not key:
                continue
            for employee in employee_email_owners.get(key, []):
                linked_user_id = safe_int(employee.get("user_id"))
                candidate_user_id = safe_int(user.get("id"))
                if linked_user_id is not None and linked_user_id == candidate_user_id:
                    continue
                self.add(
                    "email_matches_unlinked_or_different_employee", "review", "employee/user", "email",
                    [user.get("id"), employee.get("id")],
                    "A user email matches an employee email but their explicit user_id link does not confirm the relationship.",
                    key=key,
                )

    def audit_foreign_key_integrity(self) -> None:
        # Model-declared FKs may be absent in an older live schema: bootstrap's
        # ALTER TABLE column backfills do not recreate every original constraint.
        for table_name, source_column, target_table, target_column in EXPECTED_FOREIGN_KEYS:
            if table_name not in self.table_names or target_table not in self.table_names:
                self.schema_checks.append({
                    "table": table_name, "foreign_key": f"{source_column}->{target_table}.{target_column}",
                    "status": "table_missing",
                })
                absent = []
                if table_name not in self.table_names:
                    absent.append(f"source table {table_name}")
                if target_table not in self.table_names:
                    absent.append(f"target table {target_table}")
                self.add(
                    "schema_foreign_key_table_missing", "critical", "schema",
                    f"{table_name}.{source_column}", [],
                    "Cannot verify the model-declared relationship because " + " and ".join(absent) + " is absent.",
                )
                continue
            fk_meta = self._inspect_metadata("foreign_keys", table_name)
            found_fk = None
            if fk_meta["rows"] is not None:
                for item in fk_meta["rows"]:
                    source_columns = item.get("constrained_columns") or []
                    target_columns = item.get("referred_columns") or []
                    if (
                        source_columns == [source_column]
                        and item.get("referred_table") == target_table
                        and target_columns == [target_column]
                    ):
                        found_fk = item
                        break
            expected_action = EXPECTED_FOREIGN_KEY_ACTIONS.get(
                (table_name, source_column, target_table, target_column), "NO ACTION"
            ).upper()
            actual_action = str(((found_fk or {}).get("options") or {}).get("ondelete") or "NO ACTION").upper()
            if fk_meta["rows"] is None:
                status = "unverifiable"
            elif found_fk is None:
                status = "missing"
            elif actual_action != expected_action:
                status = "delete_action_mismatch"
            else:
                status = "present"
            self.schema_checks.append({
                "table": table_name,
                "foreign_key": f"{source_column}->{target_table}.{target_column}",
                "expected_ondelete": expected_action,
                "actual_ondelete": actual_action if found_fk is not None else None,
                "status": status,
                **({"inspection_error_type": fk_meta.get("error_type")} if status == "unverifiable" and fk_meta.get("error_type") else {}),
            })
            if status != "present":
                if status == "unverifiable":
                    rule = "schema_foreign_key_unverifiable"
                    detail = "Could not inspect foreign-key metadata with this database role. This is not proof the constraint is missing; retry with an approved read-only role that can inspect schema metadata."
                    severity = "warning"
                elif found_fk is None:
                    rule = "schema_foreign_key_missing"
                    detail = f"The inspected schema does not expose the model-declared foreign key to {target_table}.{target_column}. Review orphan rows and plan a reversible migration; this tool makes no schema changes."
                    severity = "critical"
                else:
                    rule = "schema_foreign_key_delete_action_mismatch"
                    detail = f"The foreign key delete action is {actual_action}, but the model declares {expected_action}; review data-retention semantics before migration."
                    severity = "critical"
                self.add(
                    rule, severity, "schema", f"{table_name}.{source_column}", [], detail,
                )
        # Independently scan orphan rows for every declared FK, even when the
        # deployed schema lacks the FK constraint. Some core catalog/alias links
        # are already checked by focused diagnostics; skip those duplicates here.
        already_checked_data_links = {
            ("branch", "governorate_id"),
            ("employee", "branch_id"),
            ("employee", "user_id"),
            ("ticket_employee_code_alias", "employee_id"),
            ("assistant_alias", "user_id"),
            ("assistant_alias", "employee_id"),
            ("branch_name_alias", "branch_id"),
            ("employee_name_alias", "employee_id"),
            ("governorate_name_alias", "governorate_id"),
        }
        for table_name, source_column, target_table, target_column in EXPECTED_FOREIGN_KEYS:
            if (table_name, source_column) in already_checked_data_links:
                continue
            if table_name not in self.table_names or target_table not in self.table_names:
                continue
            try:
                source = Table(table_name, MetaData(), autoload_with=self.connection)
                target = Table(target_table, MetaData(), autoload_with=self.connection)
                if source_column not in source.c or target_column not in target.c:
                    continue  # The missing schema is recorded above; do not guess.
                primary_key_columns = list(source.primary_key.columns)
                if not primary_key_columns:
                    continue
                source_pk = primary_key_columns[0]
                orphan_stmt = select(source_pk, source.c[source_column]).where(
                    source.c[source_column].is_not(None),
                    ~select(1).select_from(target).where(
                        target.c[target_column] == source.c[source_column]
                    ).correlate(source).exists(),
                ).execution_options(stream_results=True)
                for source_id, _reference_id in self.connection.execute(orphan_stmt):
                    self.add(
                        "foreign_key_orphan_data", "critical", table_name, source_column,
                        [source_id],
                        f"Record references a missing {target_table}.{target_column}; reconcile this row before adding/enabling the foreign-key constraint.",
                    )
            except Exception:
                # Schema presence is already reported separately. Never silently
                # claim the data scan succeeded when introspection/query fails.
                self.add(
                    "foreign_key_orphan_scan_unverifiable", "warning", "schema",
                    f"{table_name}.{source_column}", [],
                    "Could not complete the read-only orphan scan for this declared relationship; confirm column types and permissions on a staging/replica database.",
                )

        if self.connection.dialect.name == "sqlite":
            try:
                enabled = int(self.connection.exec_driver_sql("PRAGMA foreign_keys").scalar() or 0)
            except Exception:
                enabled = 0
            if not enabled:
                self.add(
                    "sqlite_foreign_keys_disabled_on_audit_connection", "warning", "schema", "foreign_keys", [],
                    "SQLite foreign-key enforcement is disabled for this connection; orphan queries remain useful but DB-level enforcement is not confirmed.",
                )

    def migration_readiness_summary(self, by_severity: Counter[str], by_rule: Counter[str]) -> dict[str, Any]:
        """Summarize blockers for planning only; never authorizes an automatic migration."""
        unique_checks = [
            item for item in self.schema_checks
            if "columns" in item and "index" not in item and "foreign_key" not in item
        ]
        index_checks = [item for item in self.schema_checks if "index" in item]
        foreign_key_checks = [item for item in self.schema_checks if "foreign_key" in item]

        def count_status(items: list[dict[str, Any]]) -> dict[str, int]:
            return dict(sorted(Counter(str(item.get("status", "unknown")) for item in items).items()))

        unverifiable_rules = {
            rule: count for rule, count in by_rule.items()
            if "unverifiable" in rule or rule.endswith("_scan_failed")
        }
        data_scan_incomplete = bool(unverifiable_rules) or any(
            item.get("status") in {"unverifiable", "missing_or_unverifiable", "invalid_or_unverifiable", "table_missing"}
            for item in self.schema_checks
        ) or any(
            rule in by_rule
            for rule in ("schema_column_missing", "schema_table_missing", "foreign_key_orphan_scan_unverifiable")
        )
        critical_count = int(by_severity.get("critical", 0))
        review_count = int(by_severity.get("review", 0))
        warning_count = int(by_severity.get("warning", 0))
        if critical_count:
            status = "blocked_by_critical_findings"
        elif data_scan_incomplete or review_count or warning_count:
            status = "manual_review_required"
        else:
            status = "no_critical_findings_staging_review_still_required"

        return {
            "status": status,
            "migration_approved": False,
            "automatic_schema_or_data_changes_allowed": False,
            "database_scan_completeness": "partial_or_unverifiable" if data_scan_incomplete else "declared_checks_completed_without_known_inspection_errors",
            "findings_by_severity": {
                "critical": critical_count,
                "review": review_count,
                "warning": warning_count,
                "info": int(by_severity.get("info", 0)),
            },
            "schema_inventory": {
                "expected_unique_invariants": len(EXPECTED_UNIQUES),
                "unique_invariant_statuses": count_status(unique_checks),
                "expected_foreign_keys": len(EXPECTED_FOREIGN_KEYS),
                "foreign_key_statuses": count_status(foreign_key_checks),
                "expected_indexes": len(EXPECTED_INDEXES),
                "index_statuses": count_status(index_checks),
                "unverifiable_rule_counts": dict(sorted(unverifiable_rules.items())),
            },
            "required_next_steps": [
                "Run only against a staging clone or an approved read-only database role; do not run with production write credentials.",
                "Resolve or formally disposition critical identity collisions, duplicate key candidates, and orphan references before drafting DDL.",
                "Treat metadata inspection failures as unknown, not as proof a constraint is absent; correct permissions and repeat the report.",
                "Obtain an explicit policy decision for job_code, branch.code, case-insensitive email, alias ownership, and lifecycle uniqueness before adding constraints.",
                "Generate a numbered reversible migration only after reviewed data findings and verified backups; never derive destructive changes automatically from this report.",
                "Re-run this report after the staging migration and compare schema checks and data findings before any production approval.",
            ],
            "caveat": "This is a planning summary, not a migration executor, data repair plan, or production-readiness approval.",
        }

    def run(self) -> dict[str, Any]:
        self.load_tables()
        self.audit_schema_constraints()
        self.audit_schema_indexes()
        self.audit_identity_codes()
        self.audit_assistant_aliases()
        self.audit_catalogs()
        self.audit_lifecycle_and_accounts()
        self.audit_foreign_key_integrity()
        by_severity = Counter(item["severity"] for item in self.findings)
        by_severity.update(self.suppressed_by_severity)
        by_rule = Counter(item["rule"] for item in self.findings)
        by_rule.update(self.suppressed_by_rule)
        return {
            "report_type": "identity_data_reconciliation",
            "report_schema_version": 2,
            "generated_at_utc": utc_now(),
            "mode": "read_only_no_data_changes",
            "database_dialect": self.connection.dialect.name,
            "values_included": self.include_values,
            "scan_counts": self.scan_counts,
            "schema_constraint_checks": self.schema_checks,
            "schema_policy_notes": [
                {
                    "field": "user.email / employee.email",
                    "status": "casefold_uniqueness_not_declared_by_model",
                    "detail": "Exact-value UNIQUE constraints do not necessarily prevent collisions that differ only by case or surrounding whitespace.",
                },
                {
                    "field": "employee.job_code",
                    "status": "domain_uniqueness_policy_unresolved",
                    "detail": "The model has a non-unique index; duplicate values are reported for human review, not treated as automatic identity conflicts.",
                },
                {
                    "field": "branch.code",
                    "status": "database_uniqueness_constraint_not_declared",
                    "detail": "The model declares a non-unique lookup index. The application checks duplicates within a governorate, but this tool does not migrate or impose that rule.",
                },
                {
                    "field": "normalized aliases",
                    "status": "stored_key_must_match_display_text",
                    "detail": "This report checks selected confirmed alias tables; it does not rewrite stale normalized_alias values or prove every application lookup uses the same rule.",
                },
                {
                    "field": "model-declared foreign keys",
                    "status": "full_inventory_with_delete_action_checks",
                    "detail": "The report compares all model-declared foreign keys and ON DELETE actions, and separately scans for orphan rows where columns are available. Missing constraints are never applied automatically.",
                },
                {
                    "field": "foreign keys and unique constraints",
                    "status": "legacy_schema_may_not_match_models",
                    "detail": "db.create_all() creates missing tables but does not add constraints to existing tables; bootstrap's additive ALTER TABLE path adds columns only. Review this report's missing constraints and orphan rows before preparing any migration.",
                },
            ],
            "migration_readiness": self.migration_readiness_summary(by_severity, by_rule),
            "summary": {
                "finding_count": len(self.findings) + self.suppressed_findings,
                "findings_emitted": len(self.findings),
                "suppressed_after_safety_cap": self.suppressed_findings,
                "suppressed_by_severity": dict(sorted(self.suppressed_by_severity.items())),
                "suppressed_by_rule": dict(sorted(self.suppressed_by_rule.items())),
                "by_severity": dict(sorted(by_severity.items())),
                "by_rule": dict(sorted(by_rule.items())),
            },
            "findings": self.findings,
            "interpretation": {
                "critical": "Resolve or formally disposition before migration; do not auto-merge records.",
                "review": "Human review required; fields such as job_code and duplicate names may have domain-specific rules.",
                "warning": "Inspect before relying on the affected validation path.",
                "info": "Non-blocking observation; never apply automatic synchronization from this report alone.",
            },
        }


def write_csv(path: Path, report: dict[str, Any]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=("severity", "rule", "entity", "field", "record_ids", "detail"))
        writer.writeheader()
        for item in report["findings"]:
            writer.writerow({
                "severity": item.get("severity", ""),
                "rule": item.get("rule", ""),
                "entity": item.get("entity", ""),
                "field": item.get("field", ""),
                "record_ids": ";".join(item.get("record_ids") or []),
                "detail": item.get("detail", ""),
            })


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None, help="JSON report path (default: timestamped file in current directory)")
    parser.add_argument("--csv", type=Path, default=None, help="Optional CSV findings export")
    parser.add_argument("--include-values", action="store_true", help="Include raw names/codes/emails in JSON; use only in a trusted secure location")
    parser.add_argument("--allow-sqlite", action="store_true", help="Allow scanning the explicitly configured SQLite DATABASE_URL")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    raw_url = os.getenv("DATABASE_URL", "").strip()
    if not raw_url:
        print("خطأ: يجب ضبط DATABASE_URL صراحةً. لن يتم استخدام local.db افتراضيًا.", file=sys.stderr)
        return 2
    url = normalize_database_url(raw_url)
    safe_url = make_url(url)
    if safe_url.drivername.startswith("sqlite") and not args.allow_sqlite:
        print("خطأ: قاعدة SQLite غير مسموحة افتراضيًا. استخدم --allow-sqlite فقط لقاعدة محلية/تجريبية مقصودة.", file=sys.stderr)
        return 2
    if safe_url.drivername.startswith("sqlite"):
        # PRAGMA query_only blocks DML after connection, but a normal SQLite
        # URL can create a missing file before that pragma is applied. Require
        # SQLite's native read-only URI mode as a second independent safeguard.
        query = {str(key).casefold(): value for key, value in safe_url.query.items()}
        uri_enabled = str(query.get("uri", "")).strip().casefold() in {"true", "1", "yes"}
        mode = str(query.get("mode", "")).strip().casefold()
        if not safe_url.database or safe_url.database == ":memory:" or mode != "ro" or not uri_enabled:
            print(
                "خطأ: يتطلب فحص SQLite ملفًا محددًا بصيغة URI للقراءة فقط (mode=ro&uri=true) مع --allow-sqlite؛ لا يُسمح بإنشاء قاعدة فارغة تلقائيًا.",
                file=sys.stderr,
            )
            return 2
    if not (safe_url.drivername.startswith("postgresql") or safe_url.drivername.startswith("sqlite")):
        print("خطأ: هذا التقرير يدعم PostgreSQL وSQLite فقط.", file=sys.stderr)
        return 2

    engine = None
    transaction = None
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                transaction = connection.begin()
                connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            elif connection.dialect.name == "sqlite":
                connection.exec_driver_sql("PRAGMA query_only = ON")
                transaction = connection.get_transaction()
                if transaction is None:
                    transaction = connection.begin()
            else:
                print("خطأ: محرك قاعدة البيانات غير مدعوم.", file=sys.stderr)
                return 2

            report = Reconciler(connection, include_values=args.include_values).run()
            if transaction is not None and transaction.is_active:
                transaction.rollback()
                transaction = None

        output = args.output or Path(f"IDENTITY_RECONCILIATION_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        if args.csv:
            args.csv.parent.mkdir(parents=True, exist_ok=True)
            write_csv(args.csv, report)

        summary = report["summary"]
        print(f"تم إنشاء تقرير قراءة فقط: {output}")
        print(f"قاعدة البيانات: {report['database_dialect']} (لم يتم تعديل أي سجل)")
        print(f"النتائج: {summary['finding_count']}؛ حرج: {summary['by_severity'].get('critical', 0)}؛ للمراجعة: {summary['by_severity'].get('review', 0)}؛ تحذير: {summary['by_severity'].get('warning', 0)}")
        if args.csv:
            print(f"CSV: {args.csv}")
        return 1 if summary["by_severity"].get("critical", 0) else 0
    except Exception as exc:
        if transaction is not None and transaction.is_active:
            try:
                transaction.rollback()
            except Exception:
                pass
        # Do not echo URLs, credentials, SQL values, or raw driver error details.
        print(f"تعذر إنشاء تقرير التصالح ({type(exc).__name__}). تحقق من DATABASE_URL وصلاحية القراءة ومخطط القاعدة.", file=sys.stderr)
        return 2
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
