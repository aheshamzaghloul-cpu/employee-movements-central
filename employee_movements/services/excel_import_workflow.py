"""Pure workflow helpers for the Excel import wizard.

This module keeps form mapping and review-selection policy independent from
Flask request handling and ORM mutations. Database authorization and apply-time
reference validation deliberately remain in the blueprint/service layer that
has access to the active request and transaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


_OPTIONAL_EMPLOYEE_FIELDS = frozenset(
    {"email", "company_phone", "personal_phone", "branch_code"}
)
_ADD_TYPES = frozenset({"new_governorate", "new_branch", "new_employee"})
_UPDATE_TYPES = frozenset({"branch", "employee"})
_ALLOWED_TYPES_BY_KIND = {
    "governorates": frozenset({"new_governorate"}),
    "branches": frozenset({"new_branch", "branch", "branch_match"}),
    "employees": frozenset({"new_employee", "employee", "employee_match"}),
}
_ALLOWED_FIELDS_BY_UPDATE_TYPE = {
    "branch": frozenset({"name", "code"}),
    "employee": frozenset({
        "branch_id", "full_name", "email", "job_title", "job_code",
        "hire_date", "company_phone", "personal_phone",
    }),
}


def parse_excel_column_mapping(raw_fields: Mapping[str, Any], fields: Mapping[str, str]) -> dict[str, int]:
    """Parse ``map_<field>`` form values, ignoring blank or non-integer values.

    Invalid values are handled by the normal required-field and index checks;
    this preserves the import wizard's existing user-facing validation flow.
    """
    mapping: dict[str, int] = {}
    for field in fields:
        raw = raw_fields.get(f"map_{field}", "")
        raw_text = str(raw or "").strip()
        if not raw_text:
            continue
        try:
            mapping[field] = int(raw_text)
        except (TypeError, ValueError):
            continue
    return mapping


def validate_excel_column_mapping(
    kind: str,
    spec: Mapping[str, Any],
    fields: Mapping[str, str],
    mapping: Mapping[str, int],
    header_count: int | None = None,
) -> str | None:
    """Return the wizard warning for missing, duplicated, or invalid columns."""
    if kind not in _ALLOWED_TYPES_BY_KIND:
        raise ValueError("Unknown Excel import kind")

    optional_fields = _OPTIONAL_EMPLOYEE_FIELDS if kind == "employees" else frozenset()
    missing = [fields[key] for key in spec if key not in mapping and key not in optional_fields]
    if missing:
        return "يجب مطابقة الأعمدة التالية: " + "، ".join(missing)
    if len(set(mapping.values())) != len(mapping):
        return "لا يمكن استخدام نفس عمود Excel لأكثر من حقل. راجع المطابقة."
    if header_count is not None and any(index < 1 or index > header_count for index in mapping.values()):
        return "اختيار أحد الأعمدة غير صالح. أعد المطابقة."
    return None


def _selected_fields_for_action(action: Mapping[str, Any], selected: frozenset[str]) -> frozenset[str]:
    changes = action.get("changes") or {}
    if not isinstance(changes, dict):
        raise ValueError("Invalid Excel review action changes")
    action_type = str(action.get("type") or "")
    action_id = action.get("id")
    return frozenset(
        field
        for field in changes
        if isinstance(field, str)
        and f"{action_type}:{action_id}:{action.get('row')}:{field}" in selected
    )


@dataclass(frozen=True)
class ExcelImportSelectionPlan:
    """Immutable selection view over validated review actions."""

    actions: tuple[dict[str, Any], ...]
    selected: frozenset[str]
    selected_adds: tuple[dict[str, Any], ...]
    selected_updates: tuple[dict[str, Any], ...]
    skipped_adds: int
    fields_by_action_identity: dict[int, frozenset[str]]

    def is_selected_add(self, action: Mapping[str, Any]) -> bool:
        return f"{action.get('type')}:{action.get('row')}" in self.selected

    def selected_fields(self, action: Mapping[str, Any]) -> frozenset[str]:
        return self.fields_by_action_identity.get(id(action), frozenset())


def build_excel_import_selection_plan(
    kind: str,
    actions: Any,
    selected_values: Iterable[str],
) -> ExcelImportSelectionPlan:
    """Validate review action structure and calculate selected adds/updates.

    The function performs no ORM work and does not authorize access. Callers
    must check the user's role and revalidate all referenced database records
    before applying any selected action.
    """
    allowed_types = _ALLOWED_TYPES_BY_KIND.get(kind)
    if allowed_types is None:
        raise ValueError("Unknown Excel import kind")
    if not isinstance(actions, list):
        raise ValueError("Invalid Excel review actions structure")

    valid_actions: list[dict[str, Any]] = []
    fields_by_identity: dict[int, frozenset[str]] = {}
    seen_source_rows: set[int] = set()
    seen_record_targets: set[tuple[str, int]] = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("Invalid Excel review action")
        action_type = action.get("type")
        if not isinstance(action_type, str) or action_type not in allowed_types:
            raise ValueError("Unexpected Excel review action type")
        if action_type in _UPDATE_TYPES:
            changes = action.get("changes")
            if not isinstance(changes, dict) or not changes:
                raise ValueError("Invalid Excel review action changes")
            if set(changes) - _ALLOWED_FIELDS_BY_UPDATE_TYPE[action_type]:
                raise ValueError("Excel review action contains an unsupported update field")
            for field_name, change in changes.items():
                if not isinstance(field_name, str) or not isinstance(change, dict) or not {"old", "new"}.issubset(change):
                    raise ValueError("Invalid Excel review action changes")
            row_no = action.get("row")
            record_id = action.get("id")
            if not isinstance(row_no, int) or isinstance(row_no, bool) or row_no < 2:
                raise ValueError("Invalid Excel review action row")
            if not isinstance(record_id, int) or isinstance(record_id, bool) or record_id <= 0:
                raise ValueError("Invalid Excel review action record id")
        elif action_type in _ADD_TYPES:
            values = action.get("values")
            row_no = action.get("row")
            if not isinstance(values, dict) or not isinstance(row_no, int) or isinstance(row_no, bool) or row_no < 2:
                raise ValueError("Invalid Excel review addition action")
            if action_type == "new_governorate" and not str(values.get("name") or "").strip():
                raise ValueError("Invalid Excel review governorate name")
            if action_type == "new_branch":
                gov_id = action.get("governorate_id")
                if not isinstance(gov_id, int) or isinstance(gov_id, bool) or gov_id <= 0:
                    raise ValueError("Invalid Excel review governorate reference")
                if not str(values.get("name") or "").strip() or not str(values.get("code") or "").strip():
                    raise ValueError("Invalid Excel review branch values")
            if action_type == "new_employee":
                branch_id = action.get("branch_id")
                if not isinstance(branch_id, int) or isinstance(branch_id, bool) or branch_id <= 0:
                    raise ValueError("Invalid Excel review branch reference")
                for required in ("name", "job_title", "job_code"):
                    if not str(values.get(required) or "").strip():
                        raise ValueError("Invalid Excel review employee values")
                if not str(action.get("hire_date") or "").strip():
                    raise ValueError("Invalid Excel review employee hire date")
        elif action_type in {"branch_match", "employee_match"}:
            record_id = action.get("id")
            row_no = action.get("row")
            if not isinstance(record_id, int) or isinstance(record_id, bool) or record_id <= 0:
                raise ValueError("Invalid Excel review match record id")
            if not isinstance(row_no, int) or isinstance(row_no, bool) or row_no < 2:
                raise ValueError("Invalid Excel review match row")
        row_no = action.get("row")
        if not isinstance(row_no, int) or isinstance(row_no, bool) or row_no < 2:
            raise ValueError("Invalid Excel review action row")
        if row_no in seen_source_rows:
            raise ValueError("Multiple Excel review actions refer to the same source row")
        seen_source_rows.add(row_no)
        if action_type in {"branch", "branch_match", "employee", "employee_match"}:
            record_id = action.get("id")
            entity_type = "branch" if action_type in {"branch", "branch_match"} else "employee"
            target_key = (entity_type, record_id)
            if target_key in seen_record_targets:
                raise ValueError("Multiple Excel review actions refer to the same existing record")
            seen_record_targets.add(target_key)
        valid_actions.append(action)

    # Only exact checkbox tokens emitted by this validated manifest are valid.
    # Silently ignoring unknown values makes a stale/tampered form look partly
    # successful and hides broken UI/manifest contracts from the caller.
    allowed_selection_tokens: set[str] = set()
    for action in valid_actions:
        action_type = action["type"]
        if action_type in _ADD_TYPES:
            allowed_selection_tokens.add(f"{action_type}:{action.get('row')}")
        elif action_type in _UPDATE_TYPES:
            for field_name in (action.get("changes") or {}):
                allowed_selection_tokens.add(
                    f"{action_type}:{action.get('id')}:{action.get('row')}:{field_name}"
                )
    selected = frozenset(value for value in selected_values if isinstance(value, str))
    if selected - allowed_selection_tokens:
        raise ValueError("Excel review selection contains an unknown or stale action token")

    selected_adds: list[dict[str, Any]] = []
    selected_updates: list[dict[str, Any]] = []
    skipped_adds = 0

    for action in valid_actions:
        action_type = action["type"]
        if action_type in _ADD_TYPES:
            if f"{action_type}:{action.get('row')}" in selected:
                selected_adds.append(action)
            else:
                skipped_adds += 1
        elif action_type in _UPDATE_TYPES:
            selected_fields = _selected_fields_for_action(action, selected)
            fields_by_identity[id(action)] = selected_fields
            if selected_fields:
                selected_updates.append(action)

    return ExcelImportSelectionPlan(
        actions=tuple(valid_actions),
        selected=selected,
        selected_adds=tuple(selected_adds),
        selected_updates=tuple(selected_updates),
        skipped_adds=skipped_adds,
        fields_by_action_identity=fields_by_identity,
    )
