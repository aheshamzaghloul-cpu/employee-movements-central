"""Excel import wizard for governorates, branches, and employees."""

import io
import json
import logging
import os
import re
import secrets
import zipfile
from datetime import date, datetime

from flask import abort, Blueprint, flash, redirect, render_template, request, session, url_for
from openpyxl import load_workbook, Workbook
from sqlalchemy import func

from ..access import bids, can, gids, has_role, log, req, roles
from ..extensions import db
from ..models import Branch, Employee, Governorate
from ..validation import valid_email

bp = Blueprint('excel_import', __name__)
logger = logging.getLogger(__name__)


# ---------- Excel import helpers ----------
def _excel_key(value):
    s = '' if value is None else str(value).strip()
    s = s.replace('\u200f', '').replace('\u200e', '')
    s = s.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    s = s.replace('ة', 'ه').replace('ى', 'ي')
    # Excel may provide branch codes using Arabic-Indic digits while the
    # database stores Western digits (or vice versa). Normalize both forms.
    digit_map = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
    s = s.translate(digit_map)
    # Numeric Excel cells can arrive as a float-like string in some templates.
    if re.fullmatch(r'\d+\.0+', s):
        s = s.split('.', 1)[0]
    s = re.sub(r'\s+', ' ', s)
    return s.lower()


def _excel_text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


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


def _header_map(ws):
    headers = {}
    for (idx, cell) in enumerate(ws[1], 1):
        k = _excel_key(cell.value)
        if k and k not in headers:
            headers[k] = idx
    return headers


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


def _excel_import_permissions(kind):
    if kind not in ('governorates', 'branches', 'employees'):
        abort(404)
    if kind == 'governorates' and not has_role('مسؤول التطبيق'):
        abort(403)
    if kind == 'branches' and 'مسؤول التطبيق' not in roles():
        abort(403)
    if kind == 'employees' and not has_role('مسؤول التطبيق'):
        abort(403)


def _excel_scope_governorates():
    return (
        {g.id for g in Governorate.query.filter_by(is_active=True).all()}
        if 'مسؤول التطبيق' in roles()
        else set(gids())
    )


def _excel_import_page(kind, **ctx):
    _excel_import_permissions(kind)
    return render_template('excel_import.html', kind=kind, **ctx)


@bp.get('/excel-import/<kind>')
@req
def excel_import_page(kind):
    return _excel_import_page(kind)


@bp.get('/excel-import/<kind>/template')
@req
def excel_import_template(kind):
    _excel_import_permissions(kind)
    wb = Workbook()
    ws = wb.active
    ws.title = 'بيانات'
    if kind == 'governorates':
        headers = ['اسم المحافظة']
        ws.append(headers)
    elif kind == 'branches':
        headers = ['المحافظة', 'اسم الفرع', 'كود الفرع']
        ws.append(headers)
    else:
        headers = [
            'المحافظة',
            'الفرع',
            'كود الفرع',
            'اسم الموظف',
            'البريد الإلكتروني',
            'الوظيفة',
            'الكود الوظيفي',
            'تاريخ التعيين',
            'هاتف الشركة',
            'الهاتف الشخصي',
        ]
        ws.append(headers)
    for c in ws[1]:
        c.font = c.font.copy(bold=True)
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for col in ws.columns:
        letter = col[0].column_letter
        ws.column_dimensions[letter].width = max(
            16,
            min(32, max((len(_excel_text(c.value)) for c in col)) + 2),
        )
    data = io.BytesIO()
    wb.save(data)
    data.seek(0)
    from flask import send_file
    return send_file(
        data,
        as_attachment=True,
        download_name=f'{kind}-template.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


def _pending_excel_dir():
    d = os.path.join(os.getenv('TMPDIR', '/tmp'), 'employee_movements_excel_imports')
    os.makedirs(d, exist_ok=True)
    return d


def _pending_excel_path(token):
    return os.path.join(_pending_excel_dir(), f'{token}.xlsx')


def _pending_excel_review_path(token):
    return os.path.join(_pending_excel_dir(), f'{token}.json')


def _validate_excel_archive(path):
    """Reject malformed or suspiciously expansive XLSX ZIP containers before parsing.

    Upload size is capped at the HTTP layer; these limits also bound decompressed
    workbook contents so a tiny ZIP bomb cannot consume excessive resources.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > 256:
                raise ValueError('Excel archive has an invalid number of entries')
            total_uncompressed = 0
            for info in infos:
                if info.flag_bits & 0x1:
                    raise ValueError('Encrypted Excel archives are not supported')
                if info.file_size < 0 or info.compress_size < 0:
                    raise ValueError('Excel archive contains invalid size metadata')
                total_uncompressed += info.file_size
                if total_uncompressed > 64 * 1024 * 1024:
                    raise ValueError('Excel archive expands beyond the permitted limit')
                if info.file_size > 1024 * 1024 and info.compress_size == 0:
                    raise ValueError('Excel archive contains suspicious compression metadata')
                if info.compress_size and info.file_size / info.compress_size > 1000:
                    raise ValueError('Excel archive compression ratio is excessive')
            required = {'[Content_Types].xml', 'xl/workbook.xml'}
            if not required.issubset({info.filename for info in infos}):
                raise ValueError('File is not a valid Excel workbook')
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError('File is not a valid Excel ZIP archive') from exc


def _save_pending_excel(f):
    token = secrets.token_urlsafe(24)
    path = _pending_excel_path(token)
    f.save(path)
    try:
        _validate_excel_archive(path)
    except Exception:
        _remove_pending_excel(token)
        raise
    return token, path


def _remove_pending_excel(token):
    if not token:
        return
    for path in (_pending_excel_path(token), _pending_excel_review_path(token)):
        try:
            os.remove(path)
        except OSError:
            pass


def _get_pending_excel():
    token = session.get('excel_import_token')
    if not token:
        return None, None
    path = _pending_excel_path(token)
    if not os.path.isfile(path):
        session.pop('excel_import_token', None)
        return None, None
    return token, path


def _render_mapping(kind, token, path, warning=None):
    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    headers = _excel_headers(ws)
    preview = []
    for row in ws.iter_rows(min_row=2, max_row=6, values_only=True):
        vals = [_excel_text(v) for v in row]
        if any(vals):
            preview.append(vals[:len(headers)])
    wb.close()
    spec = _import_spec(kind)
    mapping = _auto_map_headers(headers, spec)
    labels = _field_labels(kind)
    return _excel_import_page(
        kind,
        mapping_step=True,
        token=token,
        headers=headers,
        preview=preview,
        fields=labels,
        suggested=mapping,
        warning=warning,
    )


@bp.post('/excel-import/<kind>/preview')
@req
def excel_import_preview(kind):
    _excel_import_permissions(kind)
    f = request.files.get('file')
    if not f or not f.filename.lower().endswith(('.xlsx', '.xlsm', '.xltx')):
        flash('اختر ملف Excel بصيغة .xlsx أو .xlsm أو .xltx.')
        return redirect(url_for('excel_import.excel_import_page', kind=kind))
    token = None
    try:
        old = session.pop('excel_import_token', None)
        _remove_pending_excel(old)
        (token, path) = _save_pending_excel(f)
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        _validate_excel_dimensions(ws)
        headers = _excel_headers(ws)
        wb.close()
        if not headers or not any(headers):
            _remove_pending_excel(token)
            flash('ملف Excel لا يحتوي على صف عناوين صالح.')
            return redirect(url_for('excel_import.excel_import_page', kind=kind))
        session['excel_import_token'] = token
        return _render_mapping(kind, token, path)
    except Exception as exc:
        logger.error('Excel import preview failed (kind=%s, error=%s)', kind, type(exc).__name__)
        # If the upload was persisted but parsing/mapping failed, remove both
        # temporary artifacts so repeated invalid uploads cannot accumulate.
        _remove_pending_excel(token)
        session.pop('excel_import_token', None)
        session.pop('excel_review_token', None)
        flash('تعذر قراءة ملف Excel. تحقق من سلامة الملف وحجمه ثم حاول مرة أخرى.')
        return redirect(url_for('excel_import.excel_import_page', kind=kind))


def _mapped_value(row, mapping, field):
    return _excel_text(_cell_by_index(row, mapping.get(field)))


@bp.post('/excel-import/<kind>/confirm')
@req
def excel_import_confirm(kind):
    _excel_import_permissions(kind)
    (token, path) = _get_pending_excel()
    if not token or not path:
        flash('انتهت جلسة مطابقة ملف Excel. ارفع الملف مرة أخرى.')
        return redirect(url_for('excel_import.excel_import_page', kind=kind))
    spec = _import_spec(kind)
    fields = _field_labels(kind)
    mapping = {}
    for field in fields:
        raw = request.form.get(f'map_{field}', '').strip()
        if raw:
            try:
                mapping[field] = int(raw)
            except ValueError:
                pass
    # Contact fields are optional in employee imports; many HR spreadsheets
    # legitimately omit personal/company phones and email addresses.
    optional_employee_fields = {'email', 'company_phone', 'personal_phone', 'branch_code'} if kind == 'employees' else set()
    missing = [fields[k] for k in spec if k not in mapping and k not in optional_employee_fields]
    if missing:
        return _render_mapping(
            kind,
            token,
            path,
            warning='يجب مطابقة الأعمدة التالية: ' + '، '.join(missing),
        )
    if len(set(mapping.values())) != len(mapping):
        return _render_mapping(
            kind,
            token,
            path,
            warning='لا يمكن استخدام نفس عمود Excel لأكثر من حقل. راجع المطابقة.',
        )
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        _validate_excel_dimensions(ws)
        headers = _excel_headers(ws)
        if any((i < 1 or i > len(headers) for i in mapping.values())):
            wb.close()
            return _render_mapping(
                kind,
                token,
                path,
                warning='اختيار أحد الأعمدة غير صالح. أعد المطابقة.',
            )
        allowed_gids = _excel_scope_governorates()
        errors = []
        govs = {
            _excel_key(g.name): g
            for g in Governorate.query.filter(Governorate.is_active == True, Governorate.id.in_(allowed_gids)).all()
        }
        branches_by_gov = {}
        for b in (
            Branch.query.filter(Branch.is_active == True, Branch.governorate_id.in_(allowed_gids))
            .all()
        ):
            branches_by_gov.setdefault(b.governorate_id, {})[_excel_key(b.name)] = b
        actions = []
        if kind == 'governorates':
            existing = {_excel_key(g.name): g for g in Governorate.query.filter_by(is_active=True).all()}
            pending = set(existing)
            for (rno, row) in enumerate(ws.iter_rows(min_row=2, values_only=False), 2):
                vals = {k: _mapped_value(row, mapping, k) for k in spec}
                name = vals.get('name', '')
                if not name:
                    continue
                key = _excel_key(name)
                if key in pending:
                    errors.append(f'صف {rno}: المحافظة موجودة بالفعل أو مكررة داخل الملف: {name}')
                    continue
                actions.append({
                    'type': 'new_governorate',
                    'row': rno,
                    'values': {'name': name},
                })
                pending.add(key)
        elif kind == 'branches':
            for (rno, row) in enumerate(ws.iter_rows(min_row=2, values_only=False), 2):
                vals = {k: _mapped_value(row, mapping, k) for k in spec}
                if not any(vals.values()):
                    continue
                g = govs.get(_excel_key(vals['governorate']))
                if not g:
                    errors.append(
                        f'صف {rno}: المحافظة غير موجودة أو خارج نطاقك: {vals['governorate']}',
                    )
                    continue
                if not vals['name'] or not vals['code']:
                    errors.append(f'صف {rno}: اسم الفرع وكوده مطلوبان.')
                    continue
                existing = branches_by_gov.setdefault(g.id, {})
                b = (
                    existing.get(_excel_key(vals['name']))
                    or Branch.query.filter_by(governorate_id=g.id, code=vals['code']).first()
                )
                if b:
                    changes = {}
                    if vals['name'] and vals['name'] != b.name:
                        changes['name'] = {'old': b.name, 'new': vals['name']}
                    if vals['code'] and vals['code'] != b.code:
                        dup = (
                            Branch.query.filter(
                                Branch.governorate_id == g.id,
                                Branch.code == vals['code'],
                                Branch.id != b.id,
                            )
                            .first()
                        )
                        if dup:
                            errors.append(
                                f'صف {rno}: كود الفرع {vals['code']} مستخدم بالفعل في فرع آخر.',
                            )
                            continue
                        changes['code'] = {'old': b.code or '—', 'new': vals['code']}
                    if changes:
                        actions.append(
                            {
                                'type': 'branch',
                                'id': b.id,
                                'row': rno,
                                'name': b.name,
                                'governorate': g.name,
                                'changes': changes,
                            },
                        )
                else:
                    dup = Branch.query.filter_by(governorate_id=g.id, code=vals['code']).first()
                    if dup:
                        errors.append(f'صف {rno}: كود الفرع {vals['code']} مستخدم بالفعل.')
                        continue
                    if (
                        _excel_key(vals['name']) in existing
                        or any(
                            a.get('type') == 'new_branch' and a.get('governorate_id') == g.id and (_excel_key(a.get('values', {}).get('name')) == _excel_key(vals['name']))
                            for a in actions
                        )
                    ):
                        errors.append(f'صف {rno}: الفرع مكرر داخل ملف Excel.')
                        continue
                    actions.append(
                        {
                            'type': 'new_branch',
                            'row': rno,
                            'values': vals,
                            'governorate_id': g.id,
                            'governorate': g.name,
                        },
                    )
        else:
            # This importer is restricted to the application administrator.
            # Do not use bids() here: that helper represents the active
            # operational/work scope for ordinary users and can be narrowed
            # to the currently selected governorate. Employee administration
            # imports must resolve every active branch in every active
            # governorate the administrator manages, independent of the
            # current workspace selector.
            branch_cache = {}
            branches_by_code = {}
            branches_by_name = {}
            active_import_branches = (
                Branch.query.filter(
                    Branch.is_active == True,
                    Branch.governorate_id.in_(allowed_gids),
                )
                .all()
            )
            for b in active_import_branches:
                governorate_key = _excel_key(b.governorate.name)
                # Names are a compatibility fallback; normalized branch codes
                # are the primary identifier whenever the workbook supplies one.
                branch_cache[(governorate_key, _excel_key(b.name))] = b
                branches_by_name.setdefault(_excel_key(b.name), []).append(b)
                if b.code not in (None, ''):
                    code_key = _excel_key(b.code)
                    branches_by_code.setdefault(code_key, []).append(b)
                    branch_cache[(governorate_key, code_key)] = b

            def _resolve_employee_import_branch(branch_code, governorate_value, branch_name):
                code_key = _excel_key(branch_code)
                gov_key = _excel_key(governorate_value)
                name_key = _excel_key(branch_name)
                # A unique active branch code is authoritative: differences in
                # spelling, hamza, spacing, or an outdated branch/governorate
                # label in Excel cannot redirect or reject the employee.
                if code_key:
                    code_matches = branches_by_code.get(code_key, [])
                    if len(code_matches) == 1:
                        return code_matches[0], 'code'
                    if len(code_matches) > 1:
                        scoped = [b for b in code_matches if _excel_key(b.governorate.name) == gov_key]
                        if len(scoped) == 1:
                            return scoped[0], 'code+governorate'
                        named = [b for b in code_matches if _excel_key(b.name) == name_key]
                        if len(named) == 1:
                            return named[0], 'code+name'
                        return None, 'ambiguous_code'
                # Backward compatibility for files without a recognized code,
                # or codes not found in the active authorized branch catalog.
                g = govs.get(gov_key)
                if not g:
                    # If the sheet's governorate label is missing/outdated, permit
                    # a name-only fallback only when that branch name is unique
                    # across all active branches the administrator may import into.
                    # Never guess when two governorates share a branch name.
                    name_matches = branches_by_name.get(name_key, []) if name_key else []
                    if len(name_matches) == 1:
                        return name_matches[0], 'unique_name_without_governorate'
                    if len(name_matches) > 1:
                        return None, 'ambiguous_name'
                    return None, 'governorate_not_found'
                # A known governorate is part of the user's intended target. If the
                # branch is not inside it, reject rather than silently cross-linking.
                named = branch_cache.get((_excel_key(g.name), name_key))
                if named:
                    return named, 'name'
                return None, 'branch_not_found'
            emails = {
                _excel_key(e.email): e
                for e in Employee.query.filter(Employee.email.isnot(None)).all()
            }
            job_codes = {
                _excel_key(e.job_code): e
                for e in Employee.query.filter(Employee.job_code.isnot(None)).all()
            }
            seen_job_codes = set()
            seen_emails = set()
            for (rno, row) in enumerate(ws.iter_rows(min_row=2, values_only=False), 2):
                vals = {k: _mapped_value(row, mapping, k) for k in spec}
                if not any(vals.values()):
                    continue
                b, branch_match_method = _resolve_employee_import_branch(
                    vals.get('branch_code', ''), vals.get('governorate', ''), vals.get('branch', '')
                )
                if not b:
                    if branch_match_method == 'ambiguous_code':
                        errors.append(
                            f"صف {rno}: كود الفرع {vals.get('branch_code', '')} غير فريد؛ أضف اسم المحافظة الصحيح أو صحح كود الفرع."
                        )
                    elif branch_match_method == 'ambiguous_name':
                        errors.append(
                            f"صف {rno}: اسم الفرع «{vals.get('branch', '')}» موجود في أكثر من محافظة؛ أدخل المحافظة الصحيحة أو كود الفرع."
                        )
                    elif branch_match_method == 'governorate_not_found':
                        errors.append(
                            f"صف {rno}: لم يُعثر على المحافظة أو كود فرع نشط مطابق: {vals.get('governorate', '')}."
                        )
                    else:
                        errors.append(
                            f"صف {rno}: لم يُعثر على فرع مطابق. راجع كود الفرع {vals.get('branch_code', '')} أو اسم الفرع {vals.get('branch', '')} والمحافظة {vals.get('governorate', '')}."
                        )
                    continue
                # Branch code determines the canonical branch and governorate.
                # Do not trust mismatched labels in Excel over a unique code.
                g = b.governorate
                required = ['name', 'job_title', 'job_code', 'hire_date']
                missing_values = [field for field in required if not vals.get(field)]
                if missing_values:
                    labels = {'name': 'اسم الموظف', 'job_title': 'الوظيفة', 'job_code': 'الكود الوظيفي', 'hire_date': 'تاريخ التعيين'}
                    errors.append(f"صف {rno}: البيانات الأساسية المطلوبة ناقصة: {'، '.join(labels[x] for x in missing_values)}.")
                    continue
                # Empty contact data is valid. Validate email only when supplied.
                vals['email'] = (vals.get('email') or '').strip()
                vals['company_phone'] = (vals.get('company_phone') or '').strip()
                vals['personal_phone'] = (vals.get('personal_phone') or '').strip()
                if vals['email'] and not valid_email(vals['email']):
                    errors.append(f'صف {rno}: البريد الإلكتروني غير صحيح.')
                    continue
                hd = _excel_date(_cell_by_index(row, mapping.get('hire_date')))
                if not hd:
                    errors.append(f'صف {rno}: تاريخ التعيين غير صحيح.')
                    continue
                ck = _excel_key(vals['job_code'])
                ek = _excel_key(vals['email']) if vals['email'] else ''
                if ck in seen_job_codes:
                    errors.append(f"صف {rno}: الكود الوظيفي مكرر داخل ملف Excel: {vals.get('job_code', '')}.")
                    continue
                if ek and ek in seen_emails:
                    errors.append(f"صف {rno}: البريد الإلكتروني مكرر داخل ملف Excel: {vals.get('email', '')}.")
                    continue
                seen_job_codes.add(ck)
                if ek:
                    seen_emails.add(ek)
                e = job_codes.get(ck) or (emails.get(ek) if ek else None)
                if e:
                    # If email points to another employee while the job code points to this one, flag it.
                    if (
                        ck
                        and ck in job_codes
                        and ek
                        and ek in emails
                        and job_codes[ck].id != emails[ek].id
                    ):
                        errors.append(
                            f'صف {rno}: الكود الوظيفي والبريد الإلكتروني يعودان لموظفين مختلفين.',
                        )
                        continue
                    changes = {}
                    candidate = {
                        'branch_id': b.id,
                        'branch': b.name,
                        'full_name': vals['name'],
                        'email': vals['email'],
                        'job_title': vals['job_title'],
                        'job_code': vals['job_code'],
                        'hire_date': hd.isoformat(),
                        'company_phone': vals['company_phone'],
                        'personal_phone': vals['personal_phone'],
                    }
                    current = {
                        'branch_id': e.branch_id,
                        'branch': e.branch.name if e.branch else '—',
                        'full_name': e.full_name,
                        'email': e.email or '',
                        'job_title': e.job_title or '',
                        'job_code': e.job_code or '',
                        'hire_date': e.hire_date.isoformat() if e.hire_date else '',
                        'company_phone': e.company_phone or '',
                        'personal_phone': e.personal_phone or '',
                    }
                    for (f, label) in [
                        ('branch_id', 'الفرع'),
                        ('full_name', 'اسم الموظف'),
                        ('email', 'البريد الإلكتروني'),
                        ('job_title', 'الوظيفة'),
                        ('job_code', 'الكود الوظيفي'),
                        ('hire_date', 'تاريخ التعيين'),
                        ('company_phone', 'هاتف الشركة'),
                        ('personal_phone', 'الهاتف الشخصي'),
                    ]:
                        if str(current.get(f, '')) != str(candidate.get(f, '')):
                            changes[f] = {
                                'label': label,
                                'old': current.get(f, '—'),
                                'new': candidate.get(f, '—'),
                            }
                    if changes:
                        actions.append(
                            {
                                'type': 'employee',
                                'id': e.id,
                                'row': rno,
                                'name': e.full_name,
                                'changes': changes,
                            },
                        )
                else:
                    if ck in job_codes or (ek and ek in emails):
                        errors.append(
                            f'صف {rno}: يوجد موظف مسجل مسبقًا بالكود الوظيفي أو البريد الإلكتروني.',
                        )
                        continue
                    actions.append(
                        {
                            'type': 'new_employee',
                            'row': rno,
                            'values': vals,
                            'hire_date': hd.isoformat(),
                            'branch_id': b.id,
                            'branch': b.name,
                            'governorate': g.name,
                        },
                    )
                    job_codes[ck] = None
                    emails[ek] = None
        wb.close()
        review_path = _pending_excel_review_path(token)
        with open(review_path, 'w', encoding='utf-8') as fh:
            json.dump(
                {'kind': kind, 'mapping': mapping, 'actions': actions, 'errors': errors},
                fh,
                ensure_ascii=False,
            )
        session['excel_review_token'] = token
        return render_template(
            'excel_import.html',
            kind=kind,
            review_step=True,
            actions=actions,
            errors=errors,
            fields=fields,
        )
    except Exception as exc:
        logger.error('Excel import confirmation failed (kind=%s, error=%s)', kind, type(exc).__name__)
        try:
            wb.close()
        except Exception:
            pass
        _remove_pending_excel(token)
        session.pop('excel_import_token', None)
        session.pop('excel_review_token', None)
        flash('تعذر تحليل ملف Excel. لم يتم حفظ أي تغييرات؛ راجع الملف وحاول مرة أخرى.')
        return redirect(url_for('excel_import.excel_import_page', kind=kind))


@bp.post('/excel-import/<kind>/apply')
@req
def excel_import_apply(kind):
    _excel_import_permissions(kind)
    token = session.get('excel_review_token')
    path = _pending_excel_path(token) if token else None
    review_path = _pending_excel_review_path(token) if token else None
    if (
        not token
        or session.get('excel_import_token') != token
        or not path
        or not os.path.isfile(path)
        or not review_path
        or not os.path.isfile(review_path)
    ):
        _remove_pending_excel(token)
        session.pop('excel_import_token', None)
        session.pop('excel_review_token', None)
        flash('انتهت جلسة مراجعة ملف Excel أو لم تعد متطابقة. ارفع الملف وراجعه مرة أخرى.')
        return redirect(url_for('excel_import.excel_import_page', kind=kind))
    try:
        with open(review_path, 'r', encoding='utf-8') as fh:
            review = json.load(fh)
        if not isinstance(review, dict) or review.get('kind') != kind:
            _remove_pending_excel(token)
            session.pop('excel_import_token', None)
            session.pop('excel_review_token', None)
            flash('نوع ملف المراجعة لا يطابق العملية المطلوبة. ارفع الملف وراجعه مرة أخرى.')
            return redirect(url_for('excel_import.excel_import_page', kind=kind))
        actions = review.get('actions', [])
        if not isinstance(actions, list):
            raise ValueError('Invalid review actions structure')
        selected = set(request.form.getlist('change'))
        added = updated = skipped = 0
        errors = list(review.get('errors', []))

        # Revalidate every database reference at apply time. The preview may be
        # several minutes old, and a branch/employee can be disabled or removed
        # between preview and confirmation. Never trust preview-time IDs alone.
        for action in actions:
            if not isinstance(action, dict) or not isinstance(action.get('type'), str):
                raise ValueError('Invalid Excel review action')
            action_type = action['type']
            if kind == 'branches' and action_type == 'new_branch':
                governorate_id = action.get('governorate_id')
                governorate = db.session.get(Governorate, governorate_id) if isinstance(governorate_id, int) else None
                if not governorate or not governorate.is_active:
                    raise ValueError('Excel branch import references a missing or inactive governorate')
            elif kind == 'branches' and action_type == 'branch':
                branch = db.session.get(Branch, action.get('id'))
                if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
                    raise ValueError('Excel branch update references a missing or inactive branch')
            elif kind == 'employees' and action_type == 'new_employee':
                branch_id = action.get('branch_id')
                branch = db.session.get(Branch, branch_id) if isinstance(branch_id, int) else None
                if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
                    raise ValueError('Excel employee import references a missing or inactive branch')
                values = action.get('values') or {}
                job_code = str(values.get('job_code') or '').strip().casefold()
                email = str(values.get('email') or '').strip().casefold()
                if not job_code:
                    raise ValueError('Excel employee import is missing a personnel code')
                if Employee.query.filter(func.lower(func.trim(Employee.job_code)) == job_code).first():
                    raise ValueError('Excel employee import conflicts with an existing personnel code')
                if email and Employee.query.filter(func.lower(Employee.email) == email).first():
                    raise ValueError('Excel employee import conflicts with an existing email')
            elif kind == 'employees' and action_type == 'employee':
                employee = db.session.get(Employee, action.get('id'))
                if not employee or employee.deleted_at is not None:
                    raise ValueError('Excel employee update references a missing or deleted employee')
                branch_key = f"employee:{action.get('id')}:branch_id"
                if branch_key in selected and 'branch_id' in (action.get('changes') or {}):
                    try:
                        branch_id = int(action['changes']['branch_id']['new'])
                    except (TypeError, ValueError, KeyError):
                        raise ValueError('Excel employee update contains an invalid branch reference')
                    branch = db.session.get(Branch, branch_id)
                    if not branch or not branch.is_active or not branch.governorate or not branch.governorate.is_active:
                        raise ValueError('Excel employee update references a missing or inactive branch')
        if kind == 'governorates':
            for a in actions:
                if a['type'] != 'new_governorate':
                    continue
                name = a['values']['name'].strip()
                if not name:
                    continue
                if Governorate.query.filter_by(name=name).first() or any(_excel_key(g.name) == _excel_key(name) for g in Governorate.query.filter_by(is_active=True).all()):
                    skipped += 1
                    continue
                db.session.add(Governorate(name=name, is_active=True))
                added += 1
        elif kind == 'branches':
            for a in actions:
                if a['type'] == 'new_branch':
                    v = a['values']
                    b = Branch(governorate_id=a['governorate_id'], name=v['name'], code=v['code'])
                    db.session.add(b)
                    db.session.flush()
                    added += 1
                elif a['type'] == 'branch':
                    b = db.session.get(Branch, a['id'])
                    if not b:
                        continue
                    changed = False
                    for f in ('name', 'code'):
                        key = f'{a['type']}:{a['id']}:{f}'
                        if key in selected:
                            setattr(b, f, a['changes'][f]['new'])
                            changed = True
                    if changed:
                        updated += 1
        else:
            for a in actions:
                if a['type'] == 'new_employee':
                    v = a['values']
                    e = Employee(
                        employee_code=None,
                        email=(v.get('email') or '').strip() or None,
                        full_name=v['name'],
                        branch_id=a['branch_id'],
                        job_title=v['job_title'],
                        job_code=v['job_code'],
                        hire_date=datetime.fromisoformat(a['hire_date']).date(),
                        company_phone=v['company_phone'],
                        personal_phone=v['personal_phone'],
                    )
                    db.session.add(e)
                    db.session.flush()
                    added += 1
                elif a['type'] == 'employee':
                    e = db.session.get(Employee, a['id'])
                    if not e:
                        continue
                    changed = False
                    for f in a['changes']:
                        key = f'employee:{a['id']}:{f}'
                        if key not in selected:
                            continue
                        new = a['changes'][f]['new']
                        if f == 'branch_id':
                            setattr(e, f, int(new))
                        elif f == 'hire_date':
                            setattr(e, f, datetime.fromisoformat(new).date())
                        else:
                            setattr(e, f, new)
                        changed = True
                    if changed:
                        updated += 1
        # Keep imported records and their audit entry in one transaction.
        log(
            'IMPORT',
            'Governorate' if kind == 'governorates' else ('Branch' if kind == 'branches' else 'Employee'),
            0,
            f'Excel: إضافة {added}، تحديث {updated}، تخطي دون تغييرات {skipped}',
        )
        db.session.commit()
        _remove_pending_excel(token)
        session.pop('excel_import_token', None)
        session.pop('excel_review_token', None)
        return render_template(
            'excel_import.html',
            kind=kind,
            import_done=True,
            added=added,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )
    except Exception as exc:
        db.session.rollback()
        logger.error('Excel import apply failed (kind=%s, error=%s)', kind, type(exc).__name__)
        _remove_pending_excel(token)
        session.pop('excel_import_token', None)
        session.pop('excel_review_token', None)
        flash('تعذر تطبيق تغييرات Excel. تم التراجع عن العملية؛ راجع سجل التشغيل للتفاصيل.')
        return redirect(url_for('excel_import.excel_import_page', kind=kind))
