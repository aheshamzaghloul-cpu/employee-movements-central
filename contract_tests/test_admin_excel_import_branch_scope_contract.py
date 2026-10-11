"""Regression contract for administrator-wide employee Excel imports."""
from pathlib import Path


def test_employee_import_does_not_limit_admin_branches_to_operational_bids():
    source = (Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "excel_import.py").read_text(encoding="utf-8")
    employee_import = source.split("        else:\n            # This importer is restricted", 1)[1].split("            emails = {", 1)[0]
    assert "Branch.id.in_(managed_branch_ids)" not in employee_import
    assert "Branch.governorate_id.in_(allowed_gids)" in employee_import
    assert "Do not use bids() here" in employee_import
