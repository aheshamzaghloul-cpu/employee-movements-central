"""Behavioral tests for the dependency-light Excel import schema service."""
from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "employee_movements" / "services" / "excel_import_schema.py"
_SPEC = importlib.util.spec_from_file_location("excel_import_schema_v6891", SCHEMA_PATH)
assert _SPEC and _SPEC.loader
schema = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(schema)


def test_excel_key_normalizes_arabic_variants_digits_and_excel_float_codes():
    assert schema._excel_key("  كود‏ ١٢٣ ") == "كود 123"
    assert schema._excel_key("١٢٣.٠٠") == "123"
    assert schema._excel_key("إدارة آمال") == "اداره امال"
    assert schema._excel_key("  ۰۰۷ ") == "007"




def test_excel_employee_code_normalization_does_not_apply_ocr_confusions():
    assert schema._excel_employee_code_key("٢٠٠-٢٠٣٥٣") == "20020353"
    assert schema._excel_employee_code_variants("٢٠٠-٢٠٣٥٣") == {"20020353", "20353"}
    assert schema._excel_employee_code_key("12O-345") == "12o345"
    assert schema._excel_employee_code_key("120-345") == "120345"
    assert schema._excel_employee_code_variants("12O-345") != schema._excel_employee_code_variants("120-345")


def test_excel_identifier_text_preserves_explicit_zero_padding_format():
    class Cell:
        value = 123
        number_format = "00000"

    cell = Cell()
    assert schema._excel_display_text(cell) == "00123"
    assert schema._excel_mapped_cell_text([cell], 1, "job_code") == "00123"
    assert schema._excel_mapped_cell_text([cell], 1, "branch_code") == "00123"


def test_exact_generic_code_header_wins_before_fuzzy_branch_code_matching():
    mapping = schema._auto_map_headers(
        ["Governorate", "Branch", "Code", "Name", "Job Title", "Hire Date"],
        schema.EMP_IMPORT_HEADERS,
    )
    assert mapping["job_code"] == 3
    assert "branch_code" not in mapping


def test_short_ambiguous_arabic_code_header_requires_explicit_mapping():
    mapping = schema._auto_map_headers(
        ["المحافظة", "الفرع", "كود", "اسم الموظف", "الوظيفة", "تاريخ التعيين"],
        schema.EMP_IMPORT_HEADERS,
    )
    assert "branch_code" not in mapping
    assert mapping["name"] == 4


def test_excel_date_helper_handles_supported_formats_without_guessing_invalid_dates():
    assert schema._excel_date(datetime(2025, 3, 4, 8, 30)) == date(2025, 3, 4)
    assert schema._excel_date("04/03/2025") == date(2025, 3, 4)
    assert schema._excel_date("2025-02-30") is None
    assert schema._excel_date(None) is None


class _Sheet:
    def __init__(self, rows, columns):
        self.max_row = rows
        self.max_column = columns


def test_excel_dimensions_enforce_both_configured_limits():
    schema._validate_excel_dimensions(_Sheet(50_001, 64))
    for sheet in (_Sheet(50_002, 64), _Sheet(50_001, 65)):
        try:
            schema._validate_excel_dimensions(sheet)
        except ValueError:
            pass
        else:
            raise AssertionError("oversized workbook dimensions should be rejected")


def test_excel_issue_classifier_keeps_duplicate_conflict_and_unresolved_categories_distinct():
    assert schema._excel_issue_category("فرع مطابق لم يُعثر عليه") == "unresolved"
    assert schema._excel_issue_category("تعارض: لم يُعثر على تطابق آمن") == "conflict"
    assert schema._excel_issue_category("الكود يعود لموظفًا آخر") == "conflict"
    assert schema._excel_issue_category("الاسم نفسه تكرر لموظف جديد داخل الفرع") == "duplicate"
    assert schema._excel_issue_category("الكود غير نشط") == "conflict"
    assert schema._excel_issue_category("مكرر داخل الملف") == "duplicate"
    assert schema._excel_issue_category("قيمة تاريخ غير صالحة") == "invalid"


def test_excel_import_blueprint_consumes_the_dependency_light_schema_service():
    blueprint = (ROOT / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    assert "from ..services.excel_import_schema import (" in blueprint
    assert "_auto_map_headers" in blueprint
    assert "_validate_excel_dimensions" in blueprint
    assert "def _auto_map_headers(" not in blueprint


def test_movement_search_payloads_are_separated_from_http_routes():
    routes = (ROOT / "employee_movements" / "blueprints" / "movements.py").read_text(encoding="utf-8")
    payloads = (ROOT / "employee_movements" / "services" / "movement_search_payloads.py").read_text(encoding="utf-8")
    for helper in ("_branch_search_payload", "_employee_search_aliases", "_movement_search_text_map"):
        assert f"def {helper}(" in payloads
    assert "from ..services.movement_search_payloads import (" in routes
    assert "def _branch_search_payload(" not in routes
    # Search scope stays in the route/query layer rather than moving into presentation helpers.
    assert "Branch.id.in_(allowed_bids)" in routes
