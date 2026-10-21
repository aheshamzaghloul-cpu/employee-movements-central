"""Dependency-free regression checks for Home, shared reading and mission lifecycle.

This is a source-contract audit, not a replacement for Flask integration tests.
Run: python scripts/check_home_workflow_contracts.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "access": ROOT / "employee_movements/access.py",
    "constants": ROOT / "employee_movements/constants.py",
    "dashboard": ROOT / "employee_movements/blueprints/dashboard.py",
    "movements": ROOT / "employee_movements/blueprints/movements.py",
    "missions": ROOT / "employee_movements/blueprints/missions.py",
    "mission_query": ROOT / "employee_movements/services/mission_query.py",
    "home": ROOT / "employee_movements/templates/home.html",
    "home_search": ROOT / "employee_movements/templates/home_global_search.html",
    "movement_template": ROOT / "employee_movements/templates/movements.html",
    "mission_reports": ROOT / "employee_movements/templates/mission_reports.html",
}
TEXT = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
checks = [
    ("home employee search is independent from work scope", "بحث الموظف من الصفحة الرئيسية مستقل عن نطاق العمل" in TEXT["dashboard"]),
    ("home operational assignment rows use active global governorates", "home_assignment_governorates=(" in TEXT["dashboard"] and "Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()" in TEXT["dashboard"]),
    ("home shows search, ticket upload, then manual mission entry", "{% include 'home_global_search.html' %}" in TEXT["home"] and 'id="homeTicketUploadForm"' in TEXT["home"] and "url_for('movements.movements', movement_type='انتداب'" in TEXT["home"] and "return_to=url_for('dashboard.home'" in TEXT["home"]),
    ("manual form separates source and destination governorate/branch controls", 'id="movementCreateGovernorate"' in TEXT["movement_template"] and 'id="movementDestinationGovernorate"' in TEXT["movement_template"] and 'id="movementDestinationBranch"' in TEXT["movement_template"]),
    ("assignment employee source must match explicit work scope", "employee_governorate_id != int(selected)" in TEXT["access"] and "not branch_ok(e.branch_id)" in TEXT["access"]),
    ("manager and supervisor share assignment destination authorization", "rs & {'مشرف محافظة', 'Manager Application Support'} and movement_type == 'انتداب'" in TEXT["access"] and "can_manage_movement_destination(destination, mt)" in TEXT["movements"]),
    ("destination validation checks active branch and active parent governorate", "not destination.is_active or not destination.governorate or not destination.governorate.is_active" in TEXT["movements"] and "destination_governorate = getattr(branch, 'governorate', None)" in TEXT["access"]),
    ("global movement records are read separately from mutation scope", "Shared read directory" in TEXT["movements"] and "readable_branch_ids" in TEXT["access"]),
    ("mission listing uses cross-governorate query service", "build_mission_report_context(" in TEXT["missions"] and "global_actor = bool({'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'} & set(roles))" in TEXT["mission_query"]),
    ("mission report filters include destination governorate and branch", "destination_governorate_id" in TEXT["mission_query"] and "destination_branch_id" in TEXT["mission_query"]),
    ("printing is read-only and uses dedicated permission", "def can_print_mission(m=None):" in TEXT["access"] and "if not can_print_mission(m):" in TEXT["missions"]),
    ("closed mission metadata edits go through Manager review requests", "if mission_state_label(m) == 'مغلقة':" in TEXT["missions"] and "لا تعدّل المأمورية المغلقة مباشرة" in TEXT["missions"] and "if 'Manager Application Support' not in rs or not can('manage_movements'):" in TEXT["missions"]),
    ("mission report is not gated on work scope", "scope_required and not scope_selected" not in TEXT["mission_reports"]),
    ("mission branch filters stay enabled across governorates", "{% if not selected_governorate %}disabled{% endif %}" not in TEXT["mission_reports"] and "{% if not selected_destination_governorate %}disabled{% endif %}" not in TEXT["mission_reports"]),
    ("mission branch filter labels show their parent governorate", TEXT["mission_reports"].count("{{b.name}} · {{b.governorate.name if b.governorate else '—'}}") >= 2),
]
failed = []
for name, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failed.append(name)
print(f"\n{len(checks)-len(failed)}/{len(checks)} source-contract checks passed")
if failed:
    sys.exit(1)
