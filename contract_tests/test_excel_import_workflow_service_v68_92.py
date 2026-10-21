"""Focused behavior tests for dependency-light Excel import workflow helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "employee_movements" / "services" / "excel_import_workflow.py"
SPEC = importlib.util.spec_from_file_location("excel_import_workflow_v6892", SERVICE_PATH)
assert SPEC and SPEC.loader
WORKFLOW = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WORKFLOW
SPEC.loader.exec_module(WORKFLOW)


def test_parse_column_mapping_ignores_blank_and_non_integer_values():
    mapping = WORKFLOW.parse_excel_column_mapping(
        {"map_name": " 3 ", "map_email": "", "map_branch": "bogus"},
        {"name": "Name", "email": "Email", "branch": "Branch"},
    )
    assert mapping == {"name": 3}


def test_required_columns_and_duplicate_columns_have_stable_arabic_warnings():
    fields = {"name": "اسم الموظف", "branch": "الفرع"}
    spec = {"name": ("name",), "branch": ("branch",)}
    assert WORKFLOW.validate_excel_column_mapping("employees", spec, fields, {"name": 1}) == (
        "يجب مطابقة الأعمدة التالية: الفرع"
    )
    assert WORKFLOW.validate_excel_column_mapping("branches", spec, fields, {"name": 1, "branch": 1}) == (
        "لا يمكن استخدام نفس عمود Excel لأكثر من حقل. راجع المطابقة."
    )


def test_employee_contact_fields_are_optional_but_non_optional_fields_are_not():
    fields = {"name": "اسم الموظف", "email": "البريد الإلكتروني", "company_phone": "هاتف الشركة"}
    spec = {key: () for key in fields}
    assert WORKFLOW.validate_excel_column_mapping("employees", spec, fields, {"name": 1}) is None
    assert WORKFLOW.validate_excel_column_mapping("branches", spec, fields, {"name": 1}) == (
        "يجب مطابقة الأعمدة التالية: البريد الإلكتروني، هاتف الشركة"
    )


def test_column_indices_must_fall_inside_workbook_header_range():
    fields = {"name": "اسم الفرع"}
    spec = {"name": ()}
    assert WORKFLOW.validate_excel_column_mapping(
        "branches", spec, fields, {"name": 2}, header_count=1
    ) == "اختيار أحد الأعمدة غير صالح. أعد المطابقة."
    assert WORKFLOW.validate_excel_column_mapping(
        "branches", spec, fields, {"name": 1}, header_count=1
    ) is None


def test_selection_plan_counts_only_deselected_new_rows_as_skipped():
    add = {"type": "new_employee", "row": 4, "values": {"name": "A"}}
    match = {"type": "employee_match", "row": 5, "id": 20}
    plan = WORKFLOW.build_excel_import_selection_plan("employees", [add, match], [])
    assert plan.actions == (add, match)
    assert plan.selected_adds == ()
    assert plan.selected_updates == ()
    assert plan.skipped_adds == 1


def test_selection_plan_selects_only_requested_adds_and_update_fields():
    add = {"type": "new_branch", "row": 7, "values": {"name": "B"}}
    update = {
        "type": "branch",
        "id": 12,
        "row": 8,
        "changes": {"name": {"old": "Old", "new": "New"}, "code": {"old": "1", "new": "2"}},
    }
    plan = WORKFLOW.build_excel_import_selection_plan(
        "branches",
        [add, update],
        ["new_branch:7", "branch:12:8:code"],
    )
    assert plan.selected_adds == (add,)
    assert plan.selected_updates == (update,)
    assert plan.is_selected_add(add)
    assert not plan.is_selected_add(update)
    assert plan.selected_fields(update) == frozenset({"code"})
    assert plan.skipped_adds == 0


def test_selection_plan_rejects_wrong_kind_action_and_malformed_changes():
    try:
        WORKFLOW.build_excel_import_selection_plan(
            "branches", [{"type": "new_employee", "row": 1}], ["new_employee:1"]
        )
    except ValueError as exc:
        assert "Unexpected Excel review action type" in str(exc)
    else:
        raise AssertionError("cross-kind Excel action should be rejected")

    try:
        WORKFLOW.build_excel_import_selection_plan(
            "branches", [{"type": "branch", "id": 1, "row": 2, "changes": []}], ["branch:1:name"]
        )
    except ValueError as exc:
        assert "Invalid Excel review action changes" in str(exc)
    else:
        raise AssertionError("malformed change payload should be rejected")


def test_selection_plan_rejects_non_list_or_non_object_action_payloads():
    for actions in (None, {"type": "new_governorate"}, ["not-an-action"]):
        try:
            WORKFLOW.build_excel_import_selection_plan("governorates", actions, [])
        except ValueError:
            pass
        else:
            raise AssertionError(f"malformed action payload should be rejected: {actions!r}")


def test_import_route_delegates_mapping_and_selection_rules_to_the_service():
    source = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "parse_excel_column_mapping(request.form, fields)" in source
    assert "validate_excel_column_mapping(kind, spec, fields, mapping)" in source
    assert "build_excel_import_selection_plan(" in source
    assert "def _selected_fields(action):" not in source
    assert "def _is_selected_add(action):" not in source
