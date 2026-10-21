"""Regression contracts for safer Excel branch matching and filtered directory performance."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMPORTER = (ROOT / "employee_movements/blueprints/excel_import.py").read_text(encoding="utf-8")
MATCHER_PATH = ROOT / "employee_movements/services/excel_import_matching.py"
MATCHER = MATCHER_PATH.read_text(encoding="utf-8")
EXCEL_SCHEMA = (ROOT / "employee_movements/services/excel_import_schema.py").read_text(encoding="utf-8")
EMPLOYEES = (ROOT / "employee_movements/blueprints/employees.py").read_text(encoding="utf-8")


def test_supplied_unknown_branch_code_cannot_silently_fall_back_to_branch_name():
    assert "if code_key:" in MATCHER
    assert "if not code_matches:" in MATCHER
    assert "return None, 'unknown_code'" in MATCHER
    assert "return candidate, 'code_label_mismatch'" in MATCHER
    assert "كود الفرع" in IMPORTER and "لم تتم المطابقة بالاسم" in IMPORTER


def test_excel_branch_label_disagreement_is_a_review_conflict_not_an_import_action():
    assert "if b and branch_match_method == 'code_label_mismatch':" in IMPORTER
    assert "تعارض يحتاج مراجعة" in IMPORTER
    assert "continue" in IMPORTER.split("if b and branch_match_method == 'code_label_mismatch':", 1)[1].split("if not b:", 1)[0]
    assert "if any(token in value for token in ('تعارض'," in EXCEL_SCHEMA


def test_employee_id_filter_is_applied_in_sql_before_materializing_results():
    route = EMPLOYEES.split("def employees():", 1)[1].split("@bp.", 1)[0]
    assert "query = query.filter(Employee.id == int(employee_filter))" in route
    assert "employee_server_paginated = not employee_filter" in route


def test_branch_filter_uses_sql_current_assignment_and_server_pagination_not_n_plus_one():
    route = EMPLOYEES.split("def employees():", 1)[1].split("@bp.", 1)[0]
    assert "select(func.max(Movement.id))" in route
    assert "current_assignment_row = aliased(Movement)" in route
    assert "current_assignment_row.destination_branch_id == int(branch_filter)" in route
    assert "query.count()" in route
    assert ".limit(employee_page_size).offset(" in route
    assert "employee_is_effectively_in_branch(e, int(branch_filter))" not in route
