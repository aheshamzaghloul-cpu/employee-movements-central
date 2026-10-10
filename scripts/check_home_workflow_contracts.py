"""Dependency-free regression checks for global home assignment/mission workflows.

This is a source-contract audit, not a replacement for Flask integration tests.
Run: python scripts/check_home_workflow_contracts.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "access": ROOT / "employee_movements/access.py",
    "dashboard": ROOT / "employee_movements/blueprints/dashboard.py",
    "movements": ROOT / "employee_movements/blueprints/movements.py",
    "missions": ROOT / "employee_movements/blueprints/missions.py",
    "mission_query": ROOT / "employee_movements/services/mission_query.py",
    "home": ROOT / "employee_movements/templates/home.html",
}
TEXT = {name: path.read_text(encoding="utf-8") for name, path in FILES.items()}
checks = [
    ("home employee search is independent from work scope", "بحث الموظف من الصفحة الرئيسية مستقل عن نطاق العمل" in TEXT["dashboard"]),
    ("home assignment governorates are active and global", "home_assignment_governorates=(" in TEXT["dashboard"] and "Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()" in TEXT["dashboard"]),
    ("home destination picker has governorate and branch controls", 'id="homeAssignmentGovernorate"' in TEXT["home"] and 'id="homeAssignmentBranch"' in TEXT["home"]),
    ("assignment employee picker allows cross-governorate selection only for authorized roles", "global_assignment_picker = movement_type == 'انتداب' and bool(rs & {'مسؤول التطبيق', 'مشرف محافظة', 'Manager Application Support'})" in TEXT["movements"]),
    ("assignment destination validation checks branch and parent governorate active", "not destination.is_active or not destination.governorate or not destination.governorate.is_active" in TEXT["movements"] and "destination_governorate = getattr(branch, 'governorate', None)" in TEXT["access"]),
    ("global movement scope is assignment-only for supervisors", "if getattr(m, 'movement_type', None) == 'انتداب':" in TEXT["access"] and "return branch_ok(m.employee.branch_id)" in TEXT["access"]),
    ("mission listing delegates to cross-governorate query service", "build_mission_report_context(" in TEXT["missions"] and "global_actor = bool({'مسؤول التطبيق', 'Manager Application Support', 'مشرف محافظة'} & set(roles))" in TEXT["mission_query"]),
    ("mission filters include destination governorate and branch", "destination_governorate_id" in TEXT["mission_query"] and "destination_branch_id" in TEXT["mission_query"]),
    ("printing uses a dedicated read permission", "def can_print_mission(m=None):" in TEXT["access"] and "and can_view_movement(m)" in TEXT["access"] and "if not can_print_mission(m):" in TEXT["missions"]),
    ("closed-mission editing stays restricted", "المأمورية مغلقة. تعديلها بعد الإغلاق متاح للـManager ومسؤول التطبيق فقط." in TEXT["missions"] and "المأمورية المغلقة" in TEXT["missions"]),
    ("mission report is not gated by work-governorate selection", "scope_required and not scope_selected" not in (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8")),
    ("mission branch filters remain available across all governorates", "{% if not selected_governorate %}disabled{% endif %}" not in (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8") and "{% if not selected_destination_governorate %}disabled{% endif %}" not in (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8")),
    ("mission branch filter labels show parent governorate", (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8").count("{{b.name}} · {{b.governorate.name if b.governorate else '—'}}") >= 2),
]
failed = []
for name, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if not ok:
        failed.append(name)
print(f"\n{len(checks)-len(failed)}/{len(checks)} source-contract checks passed")
if failed:
    sys.exit(1)
