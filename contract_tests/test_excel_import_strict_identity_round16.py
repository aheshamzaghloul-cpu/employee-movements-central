"""Round 16 source guards for deterministic Excel identity matching and approvals."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_excel_import_uses_strict_job_code_normalization_not_ticket_ocr_normalization():
    schema = (ROOT / "employee_movements/services/excel_import_schema.py").read_text(encoding="utf-8")
    importer = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    apply_service = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    assert "def _excel_employee_code_key(value):" in schema
    assert "def _excel_employee_code_variants(value):" in schema
    assert "_excel_employee_code_variants" in importer
    assert "for b in scoped_import_branches:" in importer
    assert "return candidate, 'inactive_code'" in (ROOT / "employee_movements/services/excel_import_matching.py").read_text(encoding="utf-8")
    assert "TicketEmployeeCodeAlias.alias_text" in importer
    assert "TicketEmployeeCodeAlias.alias_text" in apply_service
    assert "TicketEmployeeCodeAlias.normalized_alias.in_(" not in apply_service
    assert "from ..services.ticket_matching import job_code_lookup_variants, normalize_job_code" not in importer


def test_excel_code_cells_keep_zero_padding_from_explicit_number_format():
    schema = (ROOT / "employee_movements/services/excel_import_schema.py").read_text(encoding="utf-8")
    importer = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "def _excel_display_text(cell):" in schema
    assert "re.fullmatch(r'0{2,}', number_format)" in schema
    assert "return _excel_mapped_cell_text(row, mapping.get(field), field)" in importer


def test_update_checkbox_identity_includes_source_row_and_update_fields_are_allowlisted():
    workflow = (ROOT / "employee_movements/services/excel_import_workflow.py").read_text(encoding="utf-8")
    template = (ROOT / "employee_movements/templates/excel_import.html").read_text(encoding="utf-8")
    importer = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    assert "_ALLOWED_FIELDS_BY_UPDATE_TYPE" in workflow
    assert "action.get('row')}:{field}" in workflow
    assert "_ALLOWED_FIELDS_BY_UPDATE_TYPE[action_type]" in workflow
    assert 'value="{{a.type}}:{{a.id}}:{{a.row}}:{{f}}"' in template
    assert "matched_employee_rows = {}" in importer
    assert "هذا الموظف نفسه حُدد بالفعل" in importer


def test_existing_record_updates_are_row_locked_and_rejected_when_preview_values_are_stale():
    apply_service = (ROOT / "employee_movements/services/excel_import_apply.py").read_text(encoding="utf-8")
    blueprint = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
    template = (ROOT / "employee_movements/templates/excel_import.html").read_text(encoding="utf-8")
    assert "populate_existing().with_for_update()" in apply_service
    assert "_assert_reviewed_old_value(action, Employee, employee, field)" in apply_service
    assert "_assert_reviewed_old_value(action, Branch, branch, field)" in apply_service
    assert "An existing record changed after Excel preview" in apply_service
    assert "لم تُحفظ تغييرات" in blueprint
    assert "display_old" in blueprint and "display_new" in blueprint
    assert "ch.display_old if ch.display_old is defined else ch.old" in template
    assert "ch.display_new if ch.display_new is defined else ch.new" in template
