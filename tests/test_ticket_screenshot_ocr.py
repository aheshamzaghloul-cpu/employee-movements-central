from unittest.mock import patch

from PIL import Image

from employee_movements.services.ticket_screenshot_ocr import (
    extract_ticket_fields,
    parse_ticket_date,
)


def _tsv(rows):
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    values = [header]
    for i, (text, x, y, width, height) in enumerate(rows, start=1):
        values.append(f"5\t1\t{i}\t1\t1\t{i}\t{x}\t{y}\t{width}\t{height}\t95\t{text}")
    return ("\n".join(values) + "\n").encode()


def test_ticket_dates_parse_service_desk_and_arabic_numeric_formats():
    assert parse_ticket_date("Apr 16, 2026 11:16 AM") == "2026-04-16"
    assert parse_ticket_date("١٦/٠٤/٢٠٢٦") == "2026-04-16"
    assert parse_ticket_date("not a date") == ""


def test_ocr_returns_only_the_seven_requested_fields_and_separates_same_day_dates():
    # Word coordinates mimic the two-column ServiceDesk form screenshot.
    rows = [
        ("اليه", 155, 87, 22, 14), ("المحول", 185, 87, 35, 14),
        ("الفرع", 225, 87, 30, 14), ("list", 265, 87, 20, 14),
        ("جهينة", 325, 87, 38, 14), ("فرع", 375, 87, 20, 14),
        ("الأساسي", 1110, 87, 48, 14), ("الفرع", 1165, 87, 30, 14),
        ("اسم", 1200, 87, 20, 14), ("جهينة", 1270, 87, 38, 14),
        ("فرع", 1310, 87, 20, 14),
        ("الكود", 250, 137, 30, 14), ("الوظيفي", 205, 137, 38, 14), ("12345", 325, 137, 35, 14),
        ("مأمورية", 1120, 137, 45, 14), ("تحتاج", 1170, 137, 35, 14),
        ("هل", 1205, 137, 15, 14), ("نعم", 1265, 137, 24, 14),
        ("الأساسي", 90, 181, 40, 14), ("فرعك", 135, 181, 30, 14),
        ("إليه", 175, 181, 20, 14), ("المحول", 200, 181, 35, 14),
        ("الفرع", 240, 181, 30, 14), ("هل", 270, 181, 15, 14),
        ("الأساسي", 325, 181, 40, 14), ("فرعي", 365, 181, 25, 14),
        ("ليس", 390, 181, 22, 14), ("لا", 412, 181, 14, 14),
        ("يوم", 1185, 185, 20, 14), ("من", 1210, 185, 15, 14),
        ("Apr", 1267, 185, 24, 25), ("16,", 1298, 185, 19, 14),
        ("2026", 1322, 185, 35, 12), ("11:16", 1363, 185, 39, 25), ("AM", 1413, 185, 16, 12),
        ("يوم", 1185, 236, 20, 14), ("إلى", 1210, 236, 15, 14),
        ("Apr", 1267, 236, 24, 25), ("16,", 1298, 236, 19, 14),
        ("2026", 1322, 236, 35, 12), ("11:18", 1363, 236, 39, 25), ("AM", 1413, 236, 16, 12),
    ]
    with patch("employee_movements.services.ticket_screenshot_ocr.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = _tsv(rows)
        run.return_value.stderr = b""
        result = extract_ticket_fields(Image.new("RGB", (1855, 409), "white"))

    assert set(result) == {
        "basic_branch_name", "destination_branch_name", "job_code",
        "destination_is_basic", "needs_mission", "from_date", "to_date",
    }
    assert result["basic_branch_name"] == "فرع جهينة"
    assert result["destination_branch_name"] == "فرع جهينة"
    assert result["job_code"] == "12345"
    assert result["destination_is_basic"] == "no"
    assert result["needs_mission"] == "yes"
    assert result["from_date"] == "2026-04-16"
    assert result["to_date"] == "2026-04-16"
