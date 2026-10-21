"""Directory and branch read handlers for the assistant."""

from datetime import date

from markupsafe import Markup, escape
from sqlalchemy.orm import joinedload

from ..access import can, readable_branch_ids
from ..assignments import current_assignment_for_employee, employees_effectively_in_branches
from ..extensions import db
from ..models import Branch, Employee, EntryAssignment, EntryAssignmentBranch, Governorate, Movement
from .read_helpers import (
    _latest_current_movements,
    _load_candidate_records,
    _movement_status_text,
    _visible_branch,
    employee_status_text,
)
from .visibility import visible_employee, visible_movement


def handle_governorate_employees(a):
    gid = a.get('governorate_id')
    gov = db.session.get(Governorate, gid) if gid else None
    allowed_gids = {row.id for row in Governorate.query.filter_by(is_active=True).all()}
    if not gov or not gov.is_active or gov.id not in allowed_gids:
        return {
            'title': 'موظفو المحافظة',
            'error': 'لا توجد محافظة مطابقة أو ليست ضمن نطاق صلاحياتك.',
        }
    visible_branch_ids = set(readable_branch_ids())
    branches = (
        Branch.query
        .filter(Branch.governorate_id == gov.id, Branch.is_active == True, Branch.id.in_(visible_branch_ids))
        .order_by(Branch.name)
        .all()
    ) if visible_branch_ids else []
    employees = (
        (
            Employee.query.filter(
                Employee.is_active == True,
                Employee.branch_id.in_([b.id for b in branches]),
            )
            .order_by(Employee.full_name)
            .all()
        )
        if branches
        else []
    )
    if not employees:
        return {
            'title': f'أسماء الموظفين في {gov.name}',
            'answer': f'لا يوجد موظفون نشطون مسجلون حاليًا في محافظة {gov.name}.',
        }
    lines = [
        f'{i}. {e.full_name} — {(e.branch.name if e.branch else 'غير محدد')}'
        for (i, e) in enumerate(employees, 1)
    ]
    return {
        'title': f'أسماء الموظفين في {gov.name}',
        'answer': f'عدد الموظفين النشطين: {len(employees)}\n\n' + '\n'.join(lines),
    }


def handle_branch_status(a, intent):
    b = db.session.get(Branch, a.get('branch_id')) if a.get('branch_id') else None
    if not _visible_branch(b):
        return {
            'title': 'نتيجة البحث',
            'error': 'لم أجد فرعًا واحدًا مطابقًا.',
            'choices': _load_candidate_records(Branch, a.get('candidate_ids', [])),
        }
    employees = employees_effectively_in_branches([b.id])
    entry_links = (
        EntryAssignmentBranch.query
        .options(
            joinedload(EntryAssignmentBranch.assignment).joinedload(EntryAssignment.employee),
            joinedload(EntryAssignmentBranch.assignment).joinedload(EntryAssignment.supervisor),
        )
        .join(EntryAssignment)
        .filter(EntryAssignmentBranch.branch_id == b.id, EntryAssignment.is_active == True)
        .all()
    )
    entry_names = []
    supervisors = []
    for link in entry_links:
        if link.assignment and link.assignment.employee and link.assignment.employee.is_active:
            entry_names.append(link.assignment.employee.full_name)
        if (
            link.assignment
            and link.assignment.supervisor
            and link.assignment.supervisor.is_active
        ):
            supervisors.append(link.assignment.supervisor.full_name)

    # الموظفون المنتدبون فعليًا إلى هذا الفرع: فرع التعيين مختلف،
    # والانتداب الحالي يجعل الفرع الحالي هو هذا الفرع.
    employee_ids = [e.id for e in employees]
    current_moves = {}
    if employee_ids:
        current_moves = _latest_current_movements(employee_ids, date.today())

    inbound = [
        (e, m) for e in employees
        for m in [current_moves.get(e.id)]
        if m and m.movement_type == 'انتداب' and m.destination_branch_id == b.id and e.branch_id != b.id
    ]
    leave_count = sum(1 for m in current_moves.values() if m.movement_type == 'إجازة')
    assignment_count = sum(1 for m in current_moves.values() if m.movement_type == 'انتداب')
    permission_count = sum(1 for m in current_moves.values() if m.movement_type == 'إذن')

    def esc(v):
        return str(escape(v if v is not None else ''))

    cards = [
        f'<div class="branch-data-card"><b>اسم الفرع</b><strong>{esc(b.name)}</strong></div>',
        f'<div class="branch-data-card"><b>كود الفرع</b><strong>{esc(b.code or 'غير محدد')}</strong></div>',
        f'<div class="branch-data-card"><b>المحافظة</b><strong>{esc(b.governorate.name)}</strong></div>',
        f'<div class="branch-data-card"><b>الموظفون حاليًا</b><strong>{len(employees)}</strong></div>',
        f'<div class="branch-data-card"><b>إجازة</b><strong>{leave_count}</strong></div>',
        f'<div class="branch-data-card"><b>انتداب</b><strong>{assignment_count}</strong></div>',
        f'<div class="branch-data-card"><b>إذن اليوم</b><strong>{permission_count}</strong></div>',
    ]
    management = f'<div class="branch-management-row"><div class="branch-management-item"><span>مسؤول إدخال الفروع</span><b>{esc(', '.join(dict.fromkeys(entry_names)) if entry_names else 'غير محدد')}</b></div><div class="branch-management-item"><span>المشرف</span><b>{esc(', '.join(dict.fromkeys(supervisors)) if supervisors else 'غير محدد')}</b></div></div>'

    current_cards = []
    for e in employees:
        status = _movement_status_text(current_moves.get(e.id))
        current_cards.append(
            f'<div class="branch-employee-card"><div class="branch-employee-name">{esc(e.full_name)}</div><div class="branch-employee-meta"><span>{esc(status)}</span><span>فرع التعيين: {esc(e.branch.name if e.branch else 'غير محدد')}</span></div></div>',
        )
    employees_html = (
        ''.join(current_cards)
        if current_cards
        else '<div class="branch-empty">لا يوجد موظفون حاليًا في هذا الفرع.</div>'
    )

    inbound_cards = []
    for (e, m) in inbound:
        period = 'مفتوح' if m.to_date is None else f'حتى {m.to_date}'
        inbound_cards.append(
            f'<div class="branch-inbound-card"><div class="branch-employee-name">{esc(e.full_name)}</div><div class="branch-inbound-meta"><span>انتداب إلى {esc(b.name)}</span><span>من {esc(m.from_date or 'غير محدد')}</span><span>{esc(period)}</span></div><div class="branch-inbound-origin">فرع التعيين: {esc(e.branch.name if e.branch else 'غير محدد')}</div></div>',
        )
    inbound_html = (
        ''.join(inbound_cards)
        if inbound_cards
        else '<div class="branch-empty">لا يوجد موظفون منتدبون حاليًا إلى هذا الفرع.</div>'
    )

    answer = (
        '<div class="branch-data-layout"><div class="branch-data-section"><div class="branch-section-title">بيانات الفرع</div><div class="branch-data-grid">'
        + ''.join(cards)
        + '</div></div><div class="branch-data-section">'
        + management
        + '</div><div class="branch-data-section"><div class="branch-section-title">الموظفون الموجودون في الفرع الآن</div><div class="branch-employee-grid">'
        + employees_html
        + '</div></div><div class="branch-data-section branch-inbound-section"><div class="branch-section-title">المنتدبون إلى الفرع الآن</div><div class="branch-employee-grid">'
        + inbound_html
        + '</div></div></div>'
    )
    return {'title': f'بيانات فرع {b.name}', 'html': Markup(answer)}


def handle_employee_info(a):
    e = db.session.get(Employee, a.get('employee_id')) if a.get('employee_id') else None
    if not visible_employee(e):
        return {
            'title': 'نتيجة البحث',
            'error': 'لم أجد موظفًا واحدًا مطابقًا.',
            'choices': _load_candidate_records(Employee, a.get('candidate_ids', [])),
        }
    can_read_movement_details = can('view_reports')
    cur = current_assignment_for_employee(e.id) if can_read_movement_details else None
    cb = cur.destination if cur and cur.destination else e.branch
    if can_read_movement_details:
        candidate_movements = (
            Movement.query.filter_by(employee_id=e.id, is_active=True)
            .order_by(Movement.id.desc()).limit(80).all()
        )
        ms = [m for m in candidate_movements if visible_movement(m)][:20]
    else:
        ms = []
    latest_by_kind = {}
    for kind in ('إجازة', 'انتداب', 'إذن'):
        latest_by_kind[kind] = next((m for m in ms if m.movement_type == kind), None)

    leave = latest_by_kind['إجازة']
    assignment = latest_by_kind['انتداب']
    permission = latest_by_kind['إذن']
    field = a.get('employee_field') or 'basic'

    def movement_text(m):
        if not m:
            return 'لا توجد بيانات'
        if m.movement_type == 'إذن':
            return str(m.permission_date or 'لا توجد بيانات')
        detail = m.leave_type or (m.destination.name if m.destination else '') or ''
        if m.movement_type == 'إجازة':
            return f'{detail} — من {m.from_date or '—'} إلى {m.to_date or '—'}'
        return f'{detail} — من {m.from_date or '—'} إلى {m.to_date or 'مفتوح'}'

    if field in ('status', 'last_leave', 'last_assignment', 'last_permission', 'movements') and not can_read_movement_details:
        return {'title': 'الصلاحيات', 'error': 'تفاصيل الحركات والحالة الحالية تتطلب صلاحية التقارير.'}
    if field in ('phone', 'company_phone', 'personal_phone') and not can('view_reports'):
        return {'title': 'الصلاحيات', 'error': 'بيانات التواصل متاحة للمستخدمين المسجلين في التطبيق.'}
    if field == 'job_title':
        return {
            'title': f'وظيفة {e.full_name}',
            'answer': f'{e.full_name} — الوظيفة: {e.job_title or 'لا توجد بيانات'}',
        }
    if field == 'job_code':
        return {
            'title': f'الكود الوظيفي — {e.full_name}',
            'answer': f'{e.full_name} — الكود الوظيفي: {e.job_code or 'لا توجد بيانات'}',
        }
    if field == 'employee_code':
        return {
            'title': f'كود الموظف — {e.full_name}',
            'answer': f'{e.full_name} — كود الموظف: {e.job_code or 'لا توجد بيانات'}',
        }
    if field == 'branch':
        return {
            'title': f'فرع {e.full_name}',
            'answer': f'{e.full_name} — فرع التعيين: {(e.branch.name if e.branch else 'لا توجد بيانات')} — الفرع الحالي: {(cb.name if cb else 'لا توجد بيانات')}',
        }
    if field == 'governorate':
        return {
            'title': f'محافظة {e.full_name}',
            'answer': f'{e.full_name} — المحافظة الحالية: {(cb.governorate.name if cb and cb.governorate else 'لا توجد بيانات')}',
        }
    if field == 'hire_date':
        return {
            'title': f'تاريخ تعيين {e.full_name}',
            'answer': f'{e.full_name} — تاريخ التعيين: {e.hire_date or 'لا توجد بيانات'}',
        }
    if field == 'phone':
        return {
            'title': f'رقم الهاتف — {e.full_name}',
            'answer': f'{e.full_name} — هاتف الشركة: {e.company_phone or 'لا توجد بيانات'} — الهاتف الشخصي: {e.personal_phone or 'لا توجد بيانات'}',
        }
    if field == 'company_phone':
        return {
            'title': f'هاتف العمل — {e.full_name}',
            'answer': f'{e.full_name} — هاتف الشركة: {e.company_phone or 'لا توجد بيانات'}',
        }
    if field == 'personal_phone':
        return {
            'title': f'الهاتف الشخصي — {e.full_name}',
            'answer': f'{e.full_name} — الهاتف الشخصي: {e.personal_phone or 'لا توجد بيانات'}',
        }
    if field == 'last_leave':
        return {
            'title': f'آخر إجازة — {e.full_name}',
            'answer': f'{e.full_name} — آخر إجازة: {movement_text(leave)}',
        }
    if field == 'last_assignment':
        return {
            'title': f'آخر انتداب — {e.full_name}',
            'answer': f'{e.full_name} — آخر انتداب: {movement_text(assignment)}',
        }
    if field == 'last_permission':
        return {
            'title': f'آخر إذن — {e.full_name}',
            'answer': f'{e.full_name} — آخر إذن: {movement_text(permission)}',
        }
    if field == 'movements':
        return {
            'title': f'حركات {e.full_name}',
            'answer': (
                '\n'.join(
                    [f'{m.movement_type} — {movement_text(m)} — {m.status}' for m in ms[:20]],
                )
                if ms
                else f'{e.full_name}: لا توجد حركات مسجلة.'
            ),
        }
    lines = [
        f'الموظف: {e.full_name}',
        f'كود الموظف: {e.job_code or 'لا توجد بيانات'}',
        f'الوظيفة: {e.job_title or 'لا توجد بيانات'}',
        f'المحافظة: {(e.branch.governorate.name if e.branch and e.branch.governorate else 'لا توجد بيانات')}',
        f'فرع التعيين: {(e.branch.name if e.branch else 'لا توجد بيانات')}',
        f'تاريخ التعيين: {e.hire_date or 'لا توجد بيانات'}',
    ]
    if can_read_movement_details:
        lines.extend([
            f'الحالة الآن: {employee_status_text(e)}',
            f'الفرع الحالي: {(cb.name if cb else 'لا توجد بيانات')}',
            f'آخر إجازة: {movement_text(leave)}',
            f'آخر انتداب: {movement_text(assignment)}',
            f'آخر إذن: {movement_text(permission)}',
        ])
    return {
        'title': f'بطاقة الموظف — {e.full_name}',
        'answer': '\n'.join(lines),
        'actions': (
            [
                {'label': 'الوظيفة', 'url': '#', 'prompt': f'ما وظيفة {e.full_name}؟'},
                {'label': 'آخر إجازة', 'url': '#', 'prompt': f'ما آخر إجازة لـ {e.full_name}؟'},
                {'label': 'آخر انتداب', 'url': '#', 'prompt': f'ما آخر انتداب لـ {e.full_name}؟'},
                {'label': 'آخر إذن', 'url': '#', 'prompt': f'ما آخر إذن لـ {e.full_name}؟'},
                {'label': 'سجل الحركات', 'url': '#', 'prompt': f'اعرض سجل حركات {e.full_name}'},
            ] if can_read_movement_details else [
                {'label': 'الوظيفة', 'url': '#', 'prompt': f'ما وظيفة {e.full_name}؟'},
                {'label': 'كود شئون العاملين', 'url': '#', 'prompt': f'ما كود شئون العاملين لـ {e.full_name}؟'},
            ]
        ),
    }
