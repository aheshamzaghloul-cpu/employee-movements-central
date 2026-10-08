"""Document generation services for assignment missions (مأموريات)."""

import io
import os
from datetime import datetime

import fitz
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font


def mission_state_label(mission):
    return getattr(mission, 'mission_state', None) or 'تحت التحرير'


def mission_template_pdf(
    mission,
    employee,
    branch,
    destination,
    root_path,
    creator=None,
    print_to_date=None,
):
    """Render the supplied mission PDF template without changing its geometry."""
    template = os.path.join(root_path, 'static', 'mission', 'mission_template.pdf')
    font = os.path.join(root_path, 'static', 'mission', 'mission-original.ttf')
    doc = fitz.open(template)
    page = doc[0]

    variable_regions = [
        fitz.Rect(497.5, 74.0, 553.8, 88.8),
        fitz.Rect(458.0, 89.5, 553.8, 106.2),
        fitz.Rect(31.0, 80.0, 115.0, 94.0),
        fitz.Rect(62.0, 94.0, 84.5, 109.5),
        fitz.Rect(346.6, 158.7, 482.9, 177.2),
        fitz.Rect(156.8, 158.7, 274.4, 177.2),
        fitz.Rect(57.1, 158.7, 88.5, 177.2),
        fitz.Rect(346.5, 188.8, 482.9, 207.2),
        fitz.Rect(299.9, 253.9, 360.2, 272.6),
        fitz.Rect(428.8, 253.9, 483.1, 272.6),
        fitz.Rect(100.0, 281.5, 180.0, 298.5),
        fitz.Rect(100.0, 300.0, 180.0, 317.0),
    ]
    for rect in variable_regions:
        page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    if os.path.exists(font):
        page.insert_font(fontfile=font, fontname='missionorig')
    else:
        fallback = os.path.join(root_path, 'static', 'mission', 'NotoNaskhArabic-Regular.ttf')
        if os.path.exists(fallback):
            page.insert_font(fontfile=fallback, fontname='missionorig')

    now = datetime.now()

    def put(rect, text, size=9.9603748, align='right', direction='rtl'):
        text = '' if text is None else str(text)
        safe = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        html = (
            f'<div style="font-family:missionorig;font-size:{size:.6f}pt;'
            f'line-height:1;white-space:nowrap;text-align:{align};direction:{direction};">{safe}</div>'
        )
        page.insert_htmlbox(rect, html)

    status = 'مغلقة' if mission_state_label(mission) == 'مغلقة' else 'تحت التحرير'
    put(fitz.Rect(498.0, 74.2, 552.8, 87.9), f'{mission.id} {status}', 8.0403004, 'right', 'ltr')

    creator_name = creator.full_name if creator else ''
    creator_job = creator.job_title if creator and creator.job_title else ''
    if creator_name:
        put(fitz.Rect(462.5, 90.2, 552.8, 98.2), f'- {creator_name}', 6.0002327, 'right', 'rtl')
    if creator_job:
        put(fitz.Rect(462.5, 97.3, 552.8, 106.0), creator_job, 6.0002327, 'right', 'rtl')

    put(fitz.Rect(32.0, 82.0, 77.8, 93.0), now.strftime('%Y/%m/%d'), 8.0403004, 'left', 'ltr')
    put(fitz.Rect(80.5, 82.0, 115.0, 93.0), now.strftime('%H:%M:%S'), 8.0403004, 'left', 'ltr')
    put(fitz.Rect(62.0, 96.5, 84.5, 107.5), '1 \\ 1', 8.0403004, 'center', 'ltr')

    employee_name = employee.full_name if employee else ''
    gov_name = branch.governorate.name if branch and branch.governorate else ''
    branch_name = branch.name if branch else ''
    destination_gov = destination.governorate.name if destination and destination.governorate else ''
    destination_name = destination.name if destination else ''

    put(fitz.Rect(347.0, 159.1, 482.7, 176.9), employee_name, 9.9603748, 'right', 'rtl')
    basic_branch = f'{gov_name} - {branch_name}' if gov_name and branch_name else gov_name or branch_name
    put(fitz.Rect(157.0, 159.1, 274.2, 176.9), basic_branch, 9.9603748, 'right', 'rtl')
    put(
        fitz.Rect(57.2, 159.1, 88.4, 176.9),
        employee.job_code if employee and employee.job_code else '',
        9.9603748,
        'center',
        'ltr',
    )

    mission_dest = (
        f'{destination_gov} - {destination_name}'
        if destination_gov and destination_name
        else destination_gov or destination_name
    )
    put(fitz.Rect(346.8, 189.2, 482.7, 206.9), mission_dest, 9.9603748, 'right', 'rtl')

    effective_to_date = print_to_date or mission.to_date
    put(
        fitz.Rect(300.1, 254.6, 359.9, 271.9),
        effective_to_date.strftime('%Y/%m/%d') if effective_to_date else '',
        9.9603748,
        'center',
        'ltr',
    )
    put(
        fitz.Rect(429.1, 254.6, 482.8, 271.9),
        mission.from_date.strftime('%Y/%m/%d') if mission.from_date else '',
        9.9603748,
        'center',
        'ltr',
    )

    put(fitz.Rect(116.8, 284.6, 172.2, 296.0), 'اعتماد مدير فرع', 9.9603748, 'center', 'rtl')
    put(fitz.Rect(107.9, 303.0, 170.1, 314.5), mission_dest, 9.9603748, 'center', 'rtl')

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    out.seek(0)
    return out.getvalue()


def mission_export_xlsx(rows):
    """Build the detailed raw mission export used for external incentive calculation."""
    wb = Workbook()
    ws = wb.active
    ws.title = 'المأموريات'
    headers = [
        'رقم المأمورية', 'كود شئون العاملين', 'اسم الموظف', 'المحافظة الأصلية',
        'الفرع الأصلي', 'من محافظة', 'من فرع', 'إلى محافظة', 'إلى فرع',
        'من تاريخ', 'إلى تاريخ', 'عدد الأيام', 'حالة المأمورية', 'تاريخ الإنشاء',
        'تاريخ الإغلاق', 'منشئ المأمورية', 'سبب الإغلاق', 'ملاحظات',
    ]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    for mission in rows:
        employee = mission.employee
        origin = employee.branch if employee else None
        destination = mission.destination
        start = mission.from_date
        end = mission.to_date
        days = (end - start).days + 1 if start and end else None
        ws.append([
            mission.id,
            employee.job_code if employee else '',
            employee.full_name if employee else '',
            origin.governorate.name if origin and origin.governorate else '',
            origin.name if origin else '',
            origin.governorate.name if origin and origin.governorate else '',
            origin.name if origin else '',
            destination.governorate.name if destination and destination.governorate else '',
            destination.name if destination else '',
            start,
            end,
            days,
            mission.mission_state or 'تحت التحرير',
            mission.created_at,
            mission.closed_at,
            employee.full_name if employee else '',
            mission.closure_reason or '',
            mission.notes or '',
        ])

    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    for column in ws.columns:
        letter = column[0].column_letter
        max_length = max(len(str(cell.value or '')) for cell in column[:200])
        ws.column_dimensions[letter].width = min(max(max_length + 2, 12), 32)

    out = io.BytesIO()
    wb.save(out)
    out.seek(0)
    return out
