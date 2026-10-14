from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "employee_movements" / "templates"


def read(name):
    return (TEMPLATES / name).read_text(encoding="utf-8")


def test_employee_edit_groups_identity_job_work_and_contact_fields():
    source = read("employee_edit.html")
    for heading in ["هوية الموظف", "البيانات الوظيفية", "جهة العمل", "بيانات الاتصال"]:
        assert f"<legend>{heading}</legend>" in source
    assert 'id="employee_governorate"' in source and 'id="employee_branch"' in source


def test_delegation_groups_people_scope_separately_from_period():
    source = read("delegations.html")
    assert "أطراف التفويض ونطاقه" in source
    assert "مدة التفويض" in source
    assert 'name="starts_at"' in source and 'name="ends_at"' in source


def test_mission_filters_keep_employee_context_separate_from_destination_filters():
    source = read("mission_reports.html")
    assert "الموظف والفرع الأساسي" in source
    assert "تصفية إضافية" in source
    for field in ["destination_governorate_id", "destination_branch_id", "mission_state", "date_from", "date_to"]:
        assert f'name="{field}"' in source


def test_movement_log_filters_are_grouped_by_employee_scope_and_search_type():
    source = read("movements.html")
    assert "نطاق الموظف" in source and "نوع الحركة والبحث" in source
    for field_id in ["movementGovernorateFilter", "movementBranchFilter", "movementEmployeeFilter", "movementRecordsSearch", "movementRecordsType"]:
        assert f'id="{field_id}"' in source


def test_excel_mapping_separates_required_from_optional_employee_fields():
    source = read("excel_import.html")
    assert "البيانات الأساسية" in source and "بيانات اختيارية" in source
    assert "field in ['email','company_phone','personal_phone','branch_code']" in source


def test_shared_option_group_design_is_loaded_from_base_stylesheet():
    css = (ROOT / "employee_movements" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    base = read("base.html")
    for selector in [".smart-option-group-grid", ".smart-option-group", ".smart-option-fields", ".smart-option-actions"]:
        assert selector in css
    assert f"v={ (ROOT / 'VERSION.md').read_text(encoding='utf-8').strip() }" in base


def test_project_version_is_consistent():
    version = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    init = (ROOT / "employee_movements" / "__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert version == (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
    assert f"__version__ = '{version}'" in init
    assert f'version = "{version}"' in pyproject


def test_mission_edit_groups_destination_separately_from_period():
    source = read("mission_edit.html")
    assert "الموظف وجهة المأمورية" in source and "مدة المأمورية" in source
    assert 'id="missionDestinationGovernorate"' in source and 'id="missionDestinationBranch"' in source
    assert 'id="missionEditFromDate"' in source and 'id="missionEditToDate"' in source


def test_mission_review_groups_decision_and_notes():
    source = read("mission_edit_request_review.html")
    assert "قرار المراجعة وملاحظات المدير" in source
    assert 'id="reviewMissionFinalState"' in source and 'id="reviewMissionManagerNotes"' in source


def test_temporary_print_end_date_is_explicitly_separate_from_saved_mission():
    source = read("mission_print_date.html")
    assert "بيانات الطباعة المؤقتة" in source
    assert 'form="missionPrintDateForm"' in source and "لن يُحفظ على الانتداب ولن يغلقه" in source


def test_entry_role_conversion_groups_supervisor_and_branch_scope():
    source = read("employee_role_convert.html")
    assert "المسؤول التنظيمي" in source and "فروع المسؤولية" in source
    assert 'name="supervisor_id"' in source and 'name="branch_id"' in source


def test_replacement_flows_pair_source_and_destination_and_confirm_action():
    source = read("replacement.html")
    assert source.count("<legend>من → إلى</legend>") == 2
    assert "تنفيذ الاستبدال" in source and "data-confirm=" in source


def test_lookups_group_list_kind_with_item_name():
    source = read("lookups.html")
    assert "<legend>بيانات العنصر</legend>" in source
    assert 'name="kind"' in source and 'name="name"' in source
