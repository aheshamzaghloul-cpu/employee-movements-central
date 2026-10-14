"""Local OCR for the seven approved fields on a ServiceDesk Plus transfer ticket.

The image reaches Tesseract through stdin and is processed locally in memory. No
full OCR transcript or unrelated ticket fields are returned or persisted.
"""
from __future__ import annotations

import csv
import re
import subprocess
from datetime import datetime
from difflib import SequenceMatcher
from io import BytesIO, StringIO

from PIL import Image, ImageOps

from ..search import normalize_search_text

MAX_IMAGE_PIXELS = 12_000_000
SUPPORTED_FORMATS = {"PNG", "JPEG", "WEBP"}
_MISSING_VALUES = {"not specified", "not_specified", "غير محدد", "غير محدده", "لا يوجد"}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4,
    "أبريل": 4, "مايو": 5, "يونيو": 6, "يونيه": 6, "يوليو": 7,
    "اغسطس": 8, "أغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "أكتوبر": 10,
    "نوفمبر": 11, "ديسمبر": 12,
}


def _norm(value: object) -> str:
    value = normalize_search_text(value)
    value = value.replace("ة", "ه")
    value = re.sub(r"[^\w\s./:-]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def parse_ticket_date(value: str) -> str:
    """Convert common ServiceDesk date text to ISO; return empty if unrecognised."""
    text = str(value or "").translate(_DIGITS).strip()
    if not text:
        return ""
    # ISO is unambiguous and preferred.
    m = re.search(r"(?<!\d)(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)", text)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            return ""
    # ServiceDesk date-time picker commonly renders e.g. Apr 16, 2026 11:16 AM.
    months = {name.casefold(): number for number, names in enumerate((
        ("jan", "january"), ("feb", "february"), ("mar", "march"),
        ("apr", "april"), ("may",), ("jun", "june"), ("jul", "july"),
        ("aug", "august"), ("sep", "sept", "september"),
        ("oct", "october"), ("nov", "november"), ("dec", "december"),
    ), start=1) for name in names}
    english = re.search(r"\b([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})\b", text)
    if english:
        month = months.get(english.group(1).casefold())
        if month:
            try:
                return datetime(int(english.group(3)), month, int(english.group(2))).date().isoformat()
            except ValueError:
                return ""
    # Numeric day-first forms are also common in local deployments.
    m = re.search(r"(?<!\d)(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})(?!\d)", text)
    if m:
        a, b, y = map(int, m.groups())
        try:
            # A four-digit year at the end is taken as day/month/year.
            return datetime(y, b, a).date().isoformat()
        except ValueError:
            return ""
    # Arabic month labels if rendered in Arabic rather than English.
    normalized = _norm(text)
    for month_name, month_number in _MONTHS.items():
        m = re.search(rf"(\d{{1,2}})\s+{re.escape(_norm(month_name))}\s+(\d{{4}})", normalized)
        if m:
            try:
                return datetime(int(m.group(2)), month_number, int(m.group(1))).date().isoformat()
            except ValueError:
                return ""
    return ""


def _similar(token: str, target: str, threshold: float = 0.62) -> bool:
    token = _norm(token)
    target = _norm(target)
    return token == target or SequenceMatcher(None, token, target).ratio() >= threshold


def _row_groups(words: list[dict], tolerance: int) -> list[list[dict]]:
    groups: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["cy"], w["x"])):
        target = next((row for row in reversed(groups) if abs(word["cy"] - sum(x["cy"] for x in row) / len(row)) <= tolerance), None)
        if target is None:
            groups.append([word])
        else:
            target.append(word)
    return groups


def _half_words(row: list[dict], width: int, half: str) -> list[dict]:
    split = width * 0.52
    if half == "left":
        return [w for w in row if w["cx"] < split]
    return [w for w in row if w["cx"] >= split]


def _row_has(row_words: list[dict], phrase: str) -> bool:
    text = " ".join(_norm(w["text"]) for w in sorted(row_words, key=lambda x: x["x"]))
    normalized_phrase = _norm(phrase)
    if normalized_phrase in text:
        return True
    tokens = [_norm(w["text"]) for w in row_words]
    return all(any(_similar(token, wanted, 0.58) for token in tokens) for wanted in normalized_phrase.split())


def _row_label_type(row_words: list[dict], field: str) -> bool:
    tokens = [_norm(w["text"]) for w in row_words]
    all_text = " ".join(tokens)
    has = lambda word: any(_similar(token, word, 0.60) for token in tokens)
    if field == "basic_branch_name":
        # Require the distinctive word "اسم" exactly; do not let fuzzy matches
        # against other question labels suppress the basic-branch row.
        tokens_exact = [_norm(w["text"]) for w in row_words]
        return "اسم" in tokens_exact and "المحول" not in tokens_exact and "هل" not in tokens_exact
    if field == "destination_branch_name":
        return has("المحول") and has("list") and not has("منه") and (has("اليه") or has("اليد") or has("المحوليه"))
    if field == "job_code":
        code_label = any(_norm(w["text"]) in {"الكود", "كود", "الكرد"} for w in row_words)
        job_label = any(_similar(_norm(w["text"]), "الوظيفي", 0.70) or _norm(w["text"]) in {"الوظيفى", "الوظيقي"} for w in row_words)
        return code_label and job_label
    if field == "destination_is_basic":
        return has("هل") and has("المحول") and (has("الاساسي") or has("الاساسى") or has("فرعك"))
    if field == "needs_mission":
        return has("هل") and has("تحتاج") and (has("مأمورية") or has("مأموريه") or has("ماموريه"))
    return False


def _candidate_value(row: list[dict], width: int, field: str) -> str:
    left_column_fields = {"destination_branch_name", "job_code", "destination_is_basic"}
    # Recent ServiceDesk screenshots may be exported at roughly half size. Their
    # labels sit closer to the values proportionally, so use separate cutoffs for
    # compact screenshots and full-width exports to keep question text out.
    compact_screenshot = width < 1200
    left_value_start = 0.20 if compact_screenshot else 0.16
    right_value_start = 0.79 if compact_screenshot else 0.675
    values = []
    for word in row:
        if word["conf"] < 18:
            continue
        if field in left_column_fields:
            if not (word["cx"] >= width * left_value_start and word["cx"] < width * 0.51):
                continue
        else:
            if not (word["cx"] >= width * right_value_start and word["cx"] < width * 0.995):
                continue
        raw = str(word["text"]).strip()
        if not raw or raw in {"+", "*", "-", "|"}:
            continue
        values.append((word["x"], raw))
    # Arabic values are visually laid out right-to-left. Job codes remain
    # left-to-right; reversing the other fields preserves answer phrases such as
    # "لا ليس فرعي الأساسي" and branch names.
    reverse_rtl = field != "job_code"
    value = " ".join(v for _, v in sorted(values, key=lambda item: item[0], reverse=reverse_rtl))
    value = re.sub(r"\s+", " ", value).strip(" :|—-\t")
    if _norm(value) in {_norm(x) for x in _MISSING_VALUES}:
        return ""
    return value

def _normal_yes_no(value: str) -> str:
    normalized = _norm(value)
    compact = normalized.replace(" ", "")
    if (compact in {"نعم", "yes", "y", "العم"}
            or normalized.startswith("نعم ") or normalized.startswith("yes ")):
        # On compact Arabic screenshots, Tesseract 5 can confuse the initial
        # letter in "نعم" and emit "العم". This field is a yes/no dropdown only.
        return "yes"
    # ServiceDesk may render the selected option as the full explanatory label:
    # "لا ليس فرعي الأساسي" rather than the isolated value "لا"; OCR may add an
    # alef and emit "الا" for the first word, so accept that bounded variant.
    if (compact in {"لا", "no", "n", "الا"}
            or normalized.startswith("لا ") or normalized.startswith("الا ") or normalized.startswith("no ")):
        return "no"
    return ""


def extract_ticket_fields(image: Image.Image) -> dict[str, str]:
    """Extract only the seven requested fields from an uploaded form screenshot."""
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError("أبعاد الصورة أكبر من الحد المسموح.")
    image = ImageOps.exif_transpose(image).convert("RGB")
    if image.width < 800:
        scale = min(1.8, 1200 / max(1, image.width))
        image = image.resize((int(image.width * scale), int(image.height * scale)))

    try:
        # Use Tesseract's stdin/stdout interface so the uploaded image is not
        # written to a temporary file by the Python wrapper.
        encoded = BytesIO()
        image.save(encoded, format="PNG", optimize=True)
        completed = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "ara+eng", "--psm", "11", "tsv"],
            input=encoded.getvalue(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=12,
            check=False,
        )
        if completed.returncode != 0 or not completed.stdout:
            raise RuntimeError("محرك القراءة المحلية لم يستطع تحليل الصورة.")
        rows = csv.DictReader(StringIO(completed.stdout.decode("utf-8", errors="replace")), delimiter="\t")
    except Exception as exc:  # Keep OCR engine errors from becoming a 500 page.
        raise RuntimeError("تعذرت قراءة الصورة آليًا. يمكنك إعادة رفع صورة أوضح أو إدخال الحقول يدويًا.") from exc

    words = []
    for raw in rows:
        if raw.get("level") != "5":
            continue
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        try:
            conf = float(raw.get("conf", "-1"))
            x = int(raw["left"]); y = int(raw["top"])
            w = int(raw["width"]); h = int(raw["height"])
        except (ValueError, TypeError, KeyError):
            continue
        words.append({"text": text, "conf": conf, "x": x, "y": y, "w": w, "h": h,
                      "cx": x + w / 2, "cy": y + h / 2})

    groups = _row_groups(words, max(12, int(image.height * 0.035)))
    field_row: dict[str, list[dict]] = {}
    for field in ("basic_branch_name", "destination_branch_name", "job_code", "destination_is_basic", "needs_mission"):
        preferred_half = "left" if field in {"destination_branch_name", "job_code", "destination_is_basic"} else "right"
        candidates = []
        for row in groups:
            half_words = _half_words(row, image.width, preferred_half)
            if _row_label_type(half_words, field):
                # More distinct label words and better OCR confidence beat weak incidental matches.
                label_words = [w for w in half_words if _norm(w["text"]) not in {"+", "*"}]
                score = sum(max(0, w["conf"]) for w in label_words) + len(label_words) * 4
                candidates.append((score, row))
        if candidates:
            field_row[field] = max(candidates, key=lambda item: item[0])[1]

    result = {"basic_branch_name": "", "destination_branch_name": "", "job_code": "",
              "destination_is_basic": "", "needs_mission": "", "from_date": "", "to_date": ""}
    for field, row in field_row.items():
        value = _candidate_value(row, image.width, field)
        if field in {"destination_is_basic", "needs_mission"}:
            result[field] = _normal_yes_no(value)
        elif field == "job_code":
            result[field] = value.translate(_DIGITS).strip()
        else:
            result[field] = value

    # The visible form displays the two date-time controls vertically in this order.
    date_rows = []
    for row in groups:
        right = [w for w in row if w["cx"] >= image.width * 0.675 and w["conf"] >= 18]
        if not right:
            continue
        text = " ".join(w["text"] for w in sorted(right, key=lambda x: x["x"]))
        iso = parse_ticket_date(text)
        if iso:
            date_rows.append((sum(w["cy"] for w in right) / len(right), iso))
    ordered_dates = []
    previous_y = None
    row_tolerance = max(12, int(image.height * 0.035))
    for y, iso in sorted(date_rows):
        # Deduplicate OCR fragments from the same visual row, not equal dates:
        # a valid transfer can begin and end on the same calendar day.
        if previous_y is None or abs(y - previous_y) > row_tolerance:
            ordered_dates.append(iso)
            previous_y = y
    if ordered_dates:
        result["from_date"] = ordered_dates[0]
    if len(ordered_dates) > 1:
        result["to_date"] = ordered_dates[1]

    # Date parsing is a strong signal independent of OCR label confidence.
    result["destination_is_basic"] = _normal_yes_no(result["destination_is_basic"])
    result["needs_mission"] = _normal_yes_no(result["needs_mission"])
    return result
