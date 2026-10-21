"""Dependency-light Excel import schema and normalization helpers.

This module intentionally contains no Flask or database dependencies so the
import mapping rules can be reviewed and tested independently from HTTP routes.
"""

import re
from datetime import date, datetime


_EXCEL_DIGIT_MAP = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')


def _excel_key(value):
    s = '' if value is None else str(value).strip()
    s = s.replace('\u200f', '').replace('\u200e', '')
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    s = s.replace('ة', 'ه').replace('ى', 'ي')
    # Excel may provide branch codes using Arabic-Indic digits while the
    # database stores Western digits (or vice versa). Normalize both forms.
    s = s.translate(_EXCEL_DIGIT_MAP)
    # Numeric Excel cells can arrive as a float-like string in some templates.
    if re.fullmatch(r'\d+\.0+', s):
        s = s.split('.', 1)[0]
    s = re.sub(r'\s+', ' ', s)
    return s.lower()


def _excel_issue_category(message):
    """Classify a row-level import issue for a clearer review summary."""
    value = str(message or '')
    # Explicit conflicts take precedence if a message also mentions that a
    # matching record could not be resolved.
    if any(token in value for token in (
        'تعارض', 'غير فريد', 'غير فريدة', 'موظفين مختلفين', 'موظفًا آخر',
        'أكثر من موظف', 'أكثر من سجل', 'أكثر من محافظة', 'يعودان لموظفين', 'غير نشط',
    )):
        return 'conflict'
    if any(token in value for token in ('لم يُعثر', 'غير موجودة أو خارج نطاقك', 'فرع مطابق')):
        return 'unresolved'
    if any(token in value for token in (
        'مكرر', 'مكررة', 'تكرر لموظف جديد', 'تكرر داخل',
        'موجودة بالفعل أو مكررة', 'مذكور أكثر من مرة داخل الملف',
    )):
        return 'duplicate'
    if any(token in value for token in ('مستخدم بالفعل', 'مسجل مسبقًا')):
        return 'conflict'
    return 'invalid'


def _excel_text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _excel_employee_code_key(value):
    """Normalize an employee code without OCR substitutions.

    Excel import is an authoritative data workflow, unlike ticket-image OCR.
    Therefore O/0 and I/1 are kept distinct; only Unicode digits, surrounding
    whitespace and visual separators are normalized. This prevents two valid
    alphanumeric personnel codes from being silently treated as one person.
    """
    text = '' if value is None else str(value).strip()
    text = text.replace('\u200f', '').replace('\u200e', '').translate(_EXCEL_DIGIT_MAP)
    if re.fullmatch(r'\d+\.0+', text):
        text = text.split('.', 1)[0]
    return ''.join(char for char in text.casefold() if char.isalnum())


def _excel_employee_code_variants(value):
    """Return strict Excel identity variants plus the documented legacy 200 prefix."""
    code = _excel_employee_code_key(value)
    if not code:
        return set()
    variants = {code}
    if code.isdigit():
        if code.startswith('200') and len(code) > 3:
            variants.add(code[3:])
        else:
            variants.add('200' + code)
    return variants


def _excel_display_text(cell):
    """Display numeric cells using simple zero-padding formats when present."""
    if cell is None:
        return ''
    value = getattr(cell, 'value', cell)
    number_format = str(getattr(cell, 'number_format', '') or '').strip()
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and re.fullmatch(r'0{2,}', number_format)
    ):
        try:
            numeric = int(value)
            if float(value).is_integer():
                sign = '-' if numeric < 0 else ''
                return sign + str(abs(numeric)).zfill(len(number_format))
        except (TypeError, ValueError, OverflowError):
            pass
    return _excel_text(value)


def _excel_mapped_cell_text(row, index, field):
    """Read mapped identifier columns without losing their displayed zero padding."""
    try:
        idx = int(index)
        if idx < 1 or idx > len(row):
            return ''
        cell = row[idx - 1]
    except (TypeError, ValueError):
        return ''
    if field in {'code', 'branch_code', 'job_code'}:
        return _excel_display_text(cell)
    return _excel_text(getattr(cell, 'value', cell))


def _excel_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    txt = _excel_text(value)
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y', '%Y/%m/%d', '%d.%m.%Y', '%m/%d/%Y', '%m-%d-%Y'):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


def _excel_headers(ws):
    return [_excel_text(c.value) for c in ws[1]]


# Bound spreadsheet dimensions as well as ZIP expansion and upload bytes.
# Read-only mode limits memory use, but a workbook with millions of declared
# rows can still consume excessive CPU during preview/confirmation.
MAX_EXCEL_ROWS = 50001  # header + at most 50,000 data rows
MAX_EXCEL_COLUMNS = 64


def _validate_excel_dimensions(ws):
    rows = getattr(ws, 'max_row', None)
    columns = getattr(ws, 'max_column', None)
    if rows is not None and rows > MAX_EXCEL_ROWS:
        raise ValueError('Excel workbook exceeds the permitted row limit')
    if columns is not None and columns > MAX_EXCEL_COLUMNS:
        raise ValueError('Excel workbook exceeds the permitted column limit')


def _cell_by_index(row, index):
    try:
        idx = int(index)
        if idx < 1 or idx > len(row):
            return None
        return row[idx - 1].value
    except (TypeError, ValueError):
        return None


GOV_IMPORT_HEADERS = {
    'name': (
        'المحافظة',
        'اسم المحافظة',
        'المحافظه',
        'governorate',
        'governorate name',
        'governorate_name',
        'name',
    ),
}


BRANCH_IMPORT_HEADERS = {
    'governorate': (
        'المحافظة',
        'اسم المحافظة',
        'المحافظه',
        'governorate',
        'governorate name',
        'governorate_name',
    ),
    'name': ('اسم الفرع', 'الفرع', 'branch', 'branch name', 'branch_name'),
    'code': ('كود الفرع', 'كود الفرع/الفرع', 'كود', 'branch code', 'branch_code', 'code'),
}


EMP_IMPORT_HEADERS = {
    'governorate': (
        'المحافظة',
        'اسم المحافظة',
        'المحافظه',
        'governorate',
        'governorate name',
        'governorate_name',
    ),
    'branch': ('الفرع', 'اسم الفرع', 'branch', 'branch name', 'branch_name'),
    'branch_code': ('كود الفرع', 'كود الفرع/الفرع', 'كود الفرع للموظف', 'branch code', 'branch_code'),
    'name': (
        'اسم الموظف',
        'الموظف',
        'اسم الموظف بالكامل',
        'اسم الموظف كامل',
        'full name',
        'employee name',
        'name',
    ),
    'email': ('البريد الإلكتروني', 'البريد الالكتروني', 'البريد', 'email', 'e-mail'),
    'job_title': (
        'الوظيفة',
        'المسمى الوظيفي',
        'المسمى الوظيفى',
        'الوظيفه',
        'job title',
        'job_title',
        'title',
    ),
    'job_code': (
        'الكود الوظيفي',
        'كود الوظيفة',
        'كود شئون العاملين',
        'كود شؤون العاملين',
        'كود شئون العاملين للموظف',
        'كود العامل',
        'employee code',
        'employee_code',
        'job code',
        'job_code',
        'code',
    ),
    'hire_date': (
        'تاريخ التعيين',
        'تاريخ التعيين بالعمل',
        'تاريخ المباشرة',
        'hire date',
        'date of hire',
        'hire_date',
    ),
    'company_phone': (
        'هاتف الشركة',
        'تليفون الشركة',
        'هاتف العمل',
        'تليفون العمل',
        'company phone',
        'company_phone',
        'work phone',
    ),
    'personal_phone': (
        'الهاتف الشخصي',
        'تليفون شخصي',
        'الموبايل',
        'رقم الموبايل',
        'رقم الهاتف',
        'personal phone',
        'personal_phone',
        'mobile',
    ),
}


def _import_spec(kind):
    if kind == 'governorates':
        return GOV_IMPORT_HEADERS
    return BRANCH_IMPORT_HEADERS if kind == 'branches' else EMP_IMPORT_HEADERS


def _field_labels(kind):
    if kind == 'governorates':
        return {'name': 'اسم المحافظة'}
    if kind == 'branches':
        return {'governorate': 'المحافظة', 'name': 'اسم الفرع', 'code': 'كود الفرع'}
    return {
        'governorate': 'المحافظة',
        'branch': 'الفرع',
        'branch_code': 'كود الفرع',
        'name': 'اسم الموظف',
        'email': 'البريد الإلكتروني',
        'job_title': 'الوظيفة',
        'job_code': 'الكود الوظيفي',
        'hire_date': 'تاريخ التعيين',
        'company_phone': 'هاتف الشركة',
        'personal_phone': 'الهاتف الشخصي',
    }


def _auto_map_headers(headers, spec):
    """Return target field -> source column index, preferring all exact aliases before fuzzy matches."""
    mapping = {}
    used = set()
    normalized = [_excel_key(h) for h in headers]
    aliases_by_field = {field: [_excel_key(name) for name in names] for field, names in spec.items()}

    # Resolve every exact alias first. Otherwise an early field's fuzzy match
    # can steal a header (e.g. "Code") that exactly names a later field.
    for field, aliases in aliases_by_field.items():
        for i, header in enumerate(normalized, 1):
            if i in used or not header:
                continue
            if header in aliases:
                mapping[field] = i
                used.add(i)
                break

    # Only then use relaxed matching for longer descriptive labels. Short
    # generic headers such as "كود" need explicit user mapping to avoid guessing.
    for field, aliases in aliases_by_field.items():
        if field in mapping:
            continue
        for i, header in enumerate(normalized, 1):
            if i in used or not header or len(header) < 4:
                continue
            for alias in aliases:
                if len(alias) >= 4 and (alias in header or header in alias):
                    mapping[field] = i
                    used.add(i)
                    break
            if field in mapping:
                break
    return mapping
