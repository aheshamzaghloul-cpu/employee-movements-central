#!/usr/bin/env python3
"""CI-only HTTP smoke test for the mission center, XLSX export and mission PDF.

This script intentionally refuses to run unless CI_SMOKE is explicitly enabled
and DATABASE_URL points at the ephemeral Docker smoke database. It seeds 55
missions to exercise pagination parity, signs the admin into the running
production container over loopback, and exercises the same HTTP endpoints a browser uses.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, timedelta
from http.cookiejar import CookieJar, DefaultCookiePolicy
from io import BytesIO
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from openpyxl import load_workbook
from sqlalchemy.engine import make_url


def require_ci_database(app) -> None:
    if os.environ.get("CI_MISSION_CENTER_SMOKE") != "1":
        raise SystemExit("Refusing to seed data: set CI_MISSION_CENTER_SMOKE=1 in the isolated CI job.")
    parsed = make_url(app.config.get("SQLALCHEMY_DATABASE_URI", ""))
    if parsed.host != "emc-smoke-db" or parsed.database != "movements_smoke":
        raise SystemExit(
            "Refusing to seed data: this smoke test is only allowed against the isolated "
            "emc-smoke-db/movements_smoke database."
        )


MISSION_SMOKE_RESULT_COUNT = 55


def seed_missions(app) -> tuple[int, int, int, str, str, str, list[int], int, int]:
    from employee_movements.extensions import db
    from employee_movements.models import Branch, Employee, Governorate, Movement, User

    suffix = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("CI_MISSION_CENTER_SUFFIX", "local"))[:50] or "local"
    gov_name = f"CI Mission Center {suffix}"
    branch_code = f"CI-MISSION-{suffix}"
    employee_code = f"CI-MISSION-EMP-{suffix}"
    marker_prefix = f"CI_MISSION_CENTER_SMOKE:{suffix}"
    employee_name = f"\u0645\u0648\u0638\u0641 \u0627\u062e\u062a\u0628\u0627\u0631 \u0645\u0631\u0643\u0632 \u0627\u0644\u0645\u0623\u0645\u0648\u0631\u064a\u0627\u062a {suffix}"

    with app.app_context():
        require_ci_database(app)
        admin = User.query.filter_by(username=app.config["ADMIN_USERNAME"]).first()
        if admin is None or not admin.is_active:
            raise RuntimeError("CI administrator account was not initialized.")
        governorate = Governorate.query.filter_by(name=gov_name).first()
        if governorate is None:
            governorate = Governorate(name=gov_name, is_active=True)
            db.session.add(governorate)
            db.session.flush()
        else:
            governorate.is_active = True
        branch = Branch.query.filter_by(code=branch_code).first()
        if branch is None:
            branch = Branch(
                governorate_id=governorate.id,
                name=f"\u0641\u0631\u0639 \u0627\u062e\u062a\u0628\u0627\u0631 \u0627\u0644\u0645\u0623\u0645\u0648\u0631\u064a\u0627\u062a {suffix}",
                code=branch_code,
                is_active=True,
            )
            db.session.add(branch)
            db.session.flush()
        else:
            branch.governorate_id = governorate.id
            branch.is_active = True
        employee = Employee.query.filter_by(employee_code=employee_code).first()
        if employee is None:
            employee = Employee(
                employee_code=employee_code,
                job_code=f"JOB-{suffix}",
                full_name=employee_name,
                branch_id=branch.id,
                is_active=True,
            )
            db.session.add(employee)
            db.session.flush()
        else:
            employee.branch_id = branch.id
            employee.full_name = employee_name
            employee.is_active = True

        today = date.today()
        mission_ids: list[int] = []
        primary_mission_id = None
        for index in range(MISSION_SMOKE_RESULT_COUNT):
            marker = marker_prefix if index == 0 else f"{marker_prefix}:bulk:{index:02d}"
            mission = Movement.query.filter_by(notes=marker).first()
            if mission is None:
                mission = Movement(
                    employee_id=employee.id,
                    movement_type="\u0627\u0646\u062a\u062f\u0627\u0628",
                    destination_branch_id=branch.id,
                    from_date=today,
                    to_date=today + timedelta(days=5),
                    status="\u0645\u0633\u062c\u0644\u0629",
                    is_active=True,
                    created_by=admin.id,
                    assignment_state="\u0633\u0627\u0631\u064a",
                    mission_state="\u062a\u062d\u062a \u0627\u0644\u062a\u062d\u0631\u064a\u0631",
                    notes=marker,
                )
                db.session.add(mission)
                db.session.flush()
            else:
                # Reset only this synthetic CI fixture so repeat runs remain deterministic.
                mission.employee_id = employee.id
                mission.movement_type = "\u0627\u0646\u062a\u062f\u0627\u0628"
                mission.destination_branch_id = branch.id
                mission.from_date = today
                mission.to_date = today + timedelta(days=5)
                mission.status = "\u0645\u0633\u062c\u0644\u0629"
                mission.is_active = True
                mission.created_by = admin.id
                mission.assignment_state = "\u0633\u0627\u0631\u064a"
                mission.mission_state = "\u062a\u062d\u062a \u0627\u0644\u062a\u062d\u0631\u064a\u0631"
                mission.closed_by = None
                mission.closed_at = None
                mission.closure_reason = None
            mission_ids.append(mission.id)
            if index == 0:
                primary_mission_id = mission.id

        db.session.commit()
        result = (
            admin.id, employee.id, int(primary_mission_id), employee_code,
            employee_name, admin.full_name, mission_ids, governorate.id, branch.id,
        )
        db.session.remove()
        return result


class LoopbackSecureCookiePolicy(DefaultCookiePolicy):
    """Permit Secure cookies over loopback HTTP only in this local CI smoke test."""

    def set_ok_secure(self, cookie, request):
        host = urlsplit(request.get_full_url()).hostname
        if host in {"127.0.0.1", "localhost"}:
            return True
        return super().set_ok_secure(cookie, request)

    def return_ok_secure(self, cookie, request):
        host = urlsplit(request.get_full_url()).hostname
        if host in {"127.0.0.1", "localhost"}:
            return True
        return super().return_ok_secure(cookie, request)


def main() -> int:
    from employee_movements import create_app

    app = create_app({"INIT_DATABASE": False})
    _, employee_id, mission_id, employee_code, employee_name, creator_name, mission_ids, governorate_id, branch_id = seed_missions(app)
    base = "http://127.0.0.1:8000"
    jar = CookieJar(policy=LoopbackSecureCookiePolicy())
    opener = build_opener(HTTPCookieProcessor(jar))

    def get(path: str):
        return opener.open(Request(base + path, headers={"Accept": "text/html,application/pdf,*/*"}), timeout=15)

    def assert_private_no_store(response, label: str) -> None:
        cache_control = response.headers.get("Cache-Control", "").lower()
        if "private" not in cache_control or "no-store" not in cache_control:
            raise AssertionError(f"{label} response did not include private/no-store cache controls.")
        if response.headers.get("Pragma", "").lower() != "no-cache":
            raise AssertionError(f"{label} response did not include Pragma: no-cache.")

    login_page = get("/login").read().decode("utf-8", "replace")
    csrf_match = re.search(r'name="_csrf"\s+value="([^"]+)"', login_page)
    if not csrf_match:
        raise AssertionError("Login page did not include a CSRF token.")
    credentials = urlencode({
        "username": os.environ["ADMIN_USERNAME"],
        "password": os.environ["ADMIN_PASSWORD"],
        "_csrf": csrf_match.group(1),
    }).encode()
    login_response = opener.open(Request(
        base + "/login",
        data=credentials,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "text/html"},
    ), timeout=15)
    if urlsplit(login_response.geturl()).path in {"/login", "/change-password"}:
        raise AssertionError("CI administrator could not complete login for the mission-center smoke test.")

    report_filters = urlencode({
        "employee_id": employee_id,
        "governorate_id": governorate_id,
        "branch_id": branch_id,
        "destination_governorate_id": governorate_id,
        "destination_branch_id": branch_id,
        "date_from": date.today().isoformat(),
        "date_to": (date.today() + timedelta(days=5)).isoformat(),
        "mission_state": "\u062a\u062d\u062a \u0627\u0644\u062a\u062d\u0631\u064a\u0631",
        "duration": "dated",
    })
    report_url = f"/reports/assignments/print-missions?{report_filters}"
    report_response = get(report_url)
    assert_private_no_store(report_response, "Mission center")
    report_html = report_response.read().decode("utf-8", "replace")
    if report_response.status != 200:
        raise AssertionError(f"Mission center returned HTTP {report_response.status}.")
    for expected in (employee_name, employee_code, 'name="mission_state"', 'name="date_from"'):
        if expected not in report_html:
            raise AssertionError(f"Mission center did not render expected content: {expected!r}")
    page_ids = [int(value) for value in re.findall(r'data-mission-id="(\d+)"', report_html)]
    if len(page_ids) != 50:
        raise AssertionError(f"Paginated mission center should render exactly 50 rows; found {len(page_ids)}.")
    if f"{MISSION_SMOKE_RESULT_COUNT} مأمورية ضمن المرشحات الحالية" not in report_html:
        raise AssertionError("Mission center total count did not reflect all 55 filtered results.")
    print("MISSION_CENTER_HTTP=OK: 50-row page with the full filtered count")

    print_response = get(f"/reports/assignments/print-missions/print?{report_filters}")
    assert_private_no_store(print_response, "All-results mission print")
    print_html = print_response.read().decode("utf-8", "replace")
    if print_response.status != 200:
        raise AssertionError(f"All-results mission print returned HTTP {print_response.status}.")
    for expected in (employee_name, employee_code, f'data-mission-id="{mission_id}"', 'الموظف'):
        if expected not in print_html:
            raise AssertionError(f"All-results mission print omitted expected content: {expected!r}")
    print_ids = [int(value) for value in re.findall(r'data-mission-id="(\d+)"', print_html)]
    if len(print_ids) != MISSION_SMOKE_RESULT_COUNT or set(print_ids) != set(mission_ids):
        raise AssertionError("All-results print did not include each filtered mission exactly once across pages.")
    if f"إجمالي السجلات المطابقة: {MISSION_SMOKE_RESULT_COUNT}" not in print_html:
        raise AssertionError("All-results print did not show the exact filtered row count.")
    print("MISSION_CENTER_PRINT_ALL=OK: all 55 filtered rows included exactly once")

    export_response = get(f"/reports/assignments/export.xlsx?{report_filters}")
    assert_private_no_store(export_response, "Mission XLSX export")
    exported_bytes = export_response.read()
    if export_response.status != 200 or "spreadsheetml.sheet" not in export_response.headers.get("Content-Type", ""):
        raise AssertionError("Mission XLSX export did not return a successful spreadsheet response.")
    if not exported_bytes.startswith(b"PK"):
        raise AssertionError("Mission XLSX export is not a ZIP-based Office workbook.")
    workbook = load_workbook(BytesIO(exported_bytes), read_only=True, data_only=True)
    try:
        headers = list(workbook.active.iter_rows(min_row=1, max_row=1, values_only=True))[0]
        rows = list(workbook.active.iter_rows(min_row=2, values_only=True))
    finally:
        workbook.close()
    if len(headers) != 16 or headers[3:7] != ('محافظة الموظف', 'فرع الموظف', 'محافظة جهة المأمورية', 'فرع جهة المأمورية'):
        raise AssertionError("Mission XLSX does not use the normalized 16-column source/destination layout.")
    exported_ids = [int(row[0]) for row in rows if row and row[0] is not None]
    if len(rows) != MISSION_SMOKE_RESULT_COUNT or set(exported_ids) != set(mission_ids):
        raise AssertionError("Mission XLSX rows do not match the full filtered print result set.")
    matching = [row for row in rows if row and row[0] == mission_id]
    if len(matching) != 1 or matching[0][1] != employee_code or matching[0][2] != employee_name:
        raise AssertionError("Mission XLSX export did not preserve filter scope or employee identity.")
    if matching[0][13] != creator_name:
        raise AssertionError("Mission XLSX creator column does not show the actual user who created the mission.")
    print("MISSION_CENTER_XLSX=OK: all 55 filtered rows match print, with normalized metadata")

    pdf_response = get(f"/reports/assignments/mission-pdf/{mission_id}")
    assert_private_no_store(pdf_response, "Mission PDF")
    pdf_bytes = pdf_response.read()
    if pdf_response.status != 200 or "application/pdf" not in pdf_response.headers.get("Content-Type", ""):
        raise AssertionError("Mission PDF endpoint did not return a successful PDF response.")
    if not pdf_bytes.startswith(b"%PDF"):
        raise AssertionError("Mission PDF response does not contain a valid PDF signature.")
    print("MISSION_CENTER_PDF=OK: mission PDF generated")
    print("MISSION_CENTER_RUNTIME_SMOKE=PASS: screen pagination, full print, and XLSX IDs match")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"MISSION_CENTER_RUNTIME_SMOKE=FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise
