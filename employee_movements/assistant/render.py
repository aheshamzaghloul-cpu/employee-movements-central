"""Read-only answers rendered for the chat."""

from datetime import date

from markupsafe import Markup, escape

from ..access import branch_ok, can, gids
from ..assignments import current_assignment_for_employee, employees_effectively_in_branches
from ..extensions import db
from ..models import Branch, Employee, EntryAssignment, EntryAssignmentBranch, Governorate, Movement


def topic_options(topic):
    """Return contextual next-step choices for a keyword/topic, filtered by role permissions."""
    if topic == 'leave':
        items = [
            {'label': 'تسجيل إجازة', 'prompt': 'تسجيل إجازة', 'icon': '🌿', 'kind': 'action'},
            {
                'label': 'تقرير الإجازات',
                'prompt': 'أريد تقرير الإجازات',
                'icon': '📊',
                'kind': 'report',
            },
            {
                'label': 'حالة إجازة موظف',
                'prompt': 'ما حالة إجازة الموظف ',
                'icon': 'person',
                'kind': 'query',
            },
            {
                'label': 'سجل إجازات موظف',
                'prompt': 'اعرض سجل حركات الموظف ',
                'icon': '📋',
                'kind': 'query',
            },
        ]
        if not can('manage_movements'):
            items = [x for x in items if x['kind'] != 'action']
        if not can('view_reports'):
            items = [x for x in items if x['label'] not in ('تقرير الإجازات',)]
        return {
            'title': 'خيارات الإجازات',
            'answer': 'اختر ما تريد بخصوص الإجازات، أو اكتب طلبك مباشرة.',
            'topic_items': items,
        }
    if topic == 'assignment':
        items = [
            {
                'label': 'تسجيل انتداب',
                'prompt': 'تسجيل انتداب',
                'icon': 'assignment',
                'kind': 'action',
            },
            {
                'label': 'تقرير الانتدابات',
                'prompt': 'أريد تقرير الانتدابات',
                'icon': '📊',
                'kind': 'report',
            },
            {
                'label': 'حالة انتداب موظف',
                'prompt': 'اعرض حالة انتداب الموظف ',
                'icon': 'person',
                'kind': 'query',
            },
            {
                'label': 'سجل انتدابات موظف',
                'prompt': 'اعرض سجل حركات الموظف ',
                'icon': '📋',
                'kind': 'query',
            },
            {
                'label': 'طباعة المأموريات',
                'prompt': 'أريد طباعة المأموريات',
                'icon': '🖨️',
                'kind': 'report',
            },
        ]
        if not can('manage_movements'):
            items = [x for x in items if x['kind'] != 'action']
        if not can('view_reports'):
            items = [x for x in items if x['kind'] != 'report']
        return {
            'title': 'خيارات الانتداب',
            'answer': 'اختر الإجراء أو الاستعلام المطلوب بخصوص الانتدابات.',
            'topic_items': items,
        }
    if topic == 'permission':
        items = [
            {'label': 'تسجيل إذن', 'prompt': 'تسجيل إذن', 'icon': 'permission', 'kind': 'action'},
            {
                'label': 'تقرير الأذونات',
                'prompt': 'أريد تقرير الأذونات',
                'icon': '📊',
                'kind': 'report',
            },
            {
                'label': 'سجل أذونات موظف',
                'prompt': 'اعرض سجل حركات الموظف ',
                'icon': '📋',
                'kind': 'query',
            },
        ]
        if not can('manage_movements'):
            items = [x for x in items if x['kind'] != 'action']
        if not can('view_reports'):
            items = [x for x in items if x['kind'] != 'report']
        return {
            'title': 'خيارات الأذونات',
            'answer': 'اختر ما تريد بخصوص الأذونات، أو اكتب طلبك مباشرة.',
            'topic_items': items,
        }
    if topic == 'employee':
        items = [
            {
                'label': 'إضافة موظف جديد',
                'prompt': 'إضافة موظف جديد',
                'icon': 'add',
                'kind': 'action',
                'url': '/employees',
            },
            {
                'label': 'تعديل بيانات موظف',
                'prompt': 'تعديل بيانات موظف',
                'icon': 'edit',
                'kind': 'action',
                'url': '/employees/edit-data',
            },
            {
                'label': 'البحث عن موظف',
                'prompt': 'ابحث عن موظف',
                'icon': '🔎',
                'kind': 'query',
                'url': '/employees',
            },
            {
                'label': 'الموظفون المستقيلون',
                'prompt': 'اعرض الموظفين المستقيلين',
                'icon': 'restore',
                'kind': 'query',
                'url': '/employees/resigned',
            },
        ]
        if not can('manage_employees'):
            items = [x for x in items if x['kind'] == 'query']
        return {
            'title': 'خيارات الموظفين',
            'answer': 'ما الذي تريد فعله بخصوص الموظفين؟',
            'topic_items': items,
        }
    if topic == 'entry':
        items = []
        if can('manage_structure'):
            items += [
                {
                    'label': 'تعيين مدخل أول',
                    'prompt': 'أريد تعيين مدخل أول',
                    'icon': '👥',
                    'kind': 'action',
                },
                {
                    'label': 'إزالة دور مدخل أول',
                    'prompt': 'أريد إزالة دور مدخل أول',
                    'icon': 'remove-role',
                    'kind': 'action',
                },
                {
                    'label': 'إدارة المدخلين الأوائل',
                    'prompt': 'أريد إدارة المدخلين الأوائل',
                    'icon': 'settings',
                    'kind': 'action',
                },
                {
                    'label': 'فروع مسؤولية مدخل أول',
                    'prompt': 'اعرض فروع مسؤولية مدخل أول',
                    'icon': '🏬',
                    'kind': 'query',
                },
                {
                    'label': 'موظفو مدخل أول',
                    'prompt': 'اعرض موظفي مدخل أول',
                    'icon': 'person',
                    'kind': 'query',
                },
            ]
        if not items:
            items = [
                {
                    'label': 'عرض المدخل الأول',
                    'prompt': 'اعرض بيانات المدخل الأول',
                    'icon': '👥',
                    'kind': 'query',
                },
            ]
        return {
            'title': 'خيارات المدخل الأول',
            'answer': 'هذه الإجراءات والاستعلامات المتاحة لك بخصوص المدخل الأول.',
            'topic_items': items,
        }
    return {'title': 'المساعد الذكي', 'answer': 'اكتب الموضوع الذي تريد المساعدة فيه.'}


def render_branch_entry(a):
    br = db.session.get(Branch, a.get('branch_id')) if a.get('branch_id') else None
    if not br:
        matches = [
            db.session.get(Branch, i)
            for i in a.get('candidate_ids', [])
            if db.session.get(Branch, i)
        ]
        if len(matches) == 1:
            br = matches[0]
        elif matches:
            return {
                'title': 'تحديد الفرع',
                'error': 'وجدت أكثر من فرع مطابق. اختر الفرع المقصود.',
                'choices': matches,
            }
        else:
            return {
                'title': 'تحديد الفرع',
                'error': 'لم أجد فرعًا مطابقًا. اكتب اسم الفرع بصورة أوضح.',
            }
    link = (
        EntryAssignmentBranch.query.join(EntryAssignment)
        .filter(EntryAssignmentBranch.branch_id == br.id, EntryAssignment.is_active == True)
        .first()
    )
    if not link or not link.assignment or (not link.assignment.employee):
        return {
            'title': 'مدخل أول الفرع',
            'answer': f'الفرع: {br.name} — لا يوجد مدخل أول معين حاليًا لهذا الفرع.',
        }
    e = link.assignment.employee
    return {
        'title': 'مدخل أول الفرع',
        'answer': f'الفرع: {br.name}\nالمدخل الأول: {e.full_name}\nالمشرف: {(link.assignment.supervisor.full_name if link.assignment.supervisor else 'غير محدد')}',
    }


def employee_status_text(e):
    today = date.today()
    active = (
        Movement.query.filter_by(employee_id=e.id, is_active=True)
        .filter(
            (
                (
                    (Movement.movement_type == 'إجازة')
                    & (Movement.from_date <= today)
                    & (Movement.to_date >= today)
                )
                | (
                    (Movement.movement_type == 'انتداب')
                    & (Movement.assignment_state != 'مغلق')
                    & (Movement.from_date <= today)
                    & ((Movement.to_date == None) | (Movement.to_date >= today))
                )
                | (Movement.movement_type == 'إذن') & (Movement.permission_date == today)
            ),
        )
        .order_by(Movement.id.desc())
        .all()
    )
    if not active:
        return 'متواجد في الفرع'
    m = active[0]
    if m.movement_type == 'إجازة':
        return f'إجازة — {m.leave_type or ''} — حتى {m.to_date}'
    if m.movement_type == 'انتداب':
        return (
            f'انتداب مفتوح — {(m.destination.name if m.destination else 'غير محدد')}'
            if m.to_date is None
            else f'انتداب — {(m.destination.name if m.destination else 'غير محدد')} — حتى {m.to_date}'
        )
    return 'إذن اليوم'


def render_read(a):
    intent = a.get('intent')
    if intent == 'movement_people_today':
        mt = a.get('movement_type') or 'إجازة'
        gid = a.get('governorate_id')
        bid = a.get('branch_id')
        gov = db.session.get(Governorate, gid) if gid else None
        branch = db.session.get(Branch, bid) if bid else None
        allowed_gids = set(gids())
        if gov and (not gov.is_active or (allowed_gids and gov.id not in allowed_gids)):
            return {'title': 'نتيجة البحث', 'error': 'المحافظة غير متاحة ضمن نطاق صلاحياتك.'}
        if branch and (not branch.is_active or not branch_ok(branch.id)):
            return {'title': 'نتيجة البحث', 'error': 'الفرع غير متاح ضمن نطاق صلاحياتك.'}
        if not gov and (not branch):
            return {'title': 'نتيجة البحث', 'error': 'لم أجد محافظة أو فرعًا مطابقًا.'}

        today = date.today()
        if branch:
            target_branch_ids = {branch.id}
            location_label = f'فرع {branch.name}'
        elif gov:
            bs = (
                Branch.query.filter_by(governorate_id=gov.id, is_active=True)
                .order_by(Branch.name)
                .all()
            )
            bs = [b for b in bs if branch_ok(b.id)]
            target_branch_ids = {b.id for b in bs}
            location_label = f'محافظة {gov.name}'
        else:
            # بحث عام داخل كل الفروع المتاحة للمستخدم.
            target_branch_ids = {
                b.id
                for b in Branch.query.filter_by(is_active=True).all()
                if branch_ok(b.id)
            }
            location_label = 'النطاق المتاح لك'

        rows = []
        if mt == 'إجازة':
            if target_branch_ids:
                moves = (
                    Movement.query.join(Employee, Movement.employee_id == Employee.id)
                    .filter(
                        Employee.is_active == True,
                        Employee.branch_id.in_(target_branch_ids),
                        Movement.is_active == True,
                        Movement.movement_type == 'إجازة',
                        Movement.from_date <= today,
                        Movement.to_date >= today,
                    )
                    .order_by(Employee.full_name, Movement.id.desc())
                    .all()
                )
                seen = set()
                for m in moves:
                    if m.employee_id in seen:
                        continue
                    seen.add(m.employee_id)
                    rows.append((m.employee, m, None))
        elif mt == 'إذن':
            if target_branch_ids:
                moves = (
                    Movement.query.join(Employee, Movement.employee_id == Employee.id)
                    .filter(
                        Employee.is_active == True,
                        Employee.branch_id.in_(target_branch_ids),
                        Movement.is_active == True,
                        Movement.movement_type == 'إذن',
                        Movement.permission_date == today,
                    )
                    .order_by(Employee.full_name, Movement.id.desc())
                    .all()
                )
                seen = set()
                for m in moves:
                    if m.employee_id in seen:
                        continue
                    seen.add(m.employee_id)
                    rows.append((m.employee, None, None))
        else:
            # انتداب: «في المكان» تعني أن الوجهة الحالية داخل المكان.
            if target_branch_ids:
                moves = (
                    Movement.query.join(Employee, Movement.employee_id == Employee.id)
                    .filter(
                        Employee.is_active == True,
                        Movement.is_active == True,
                        Movement.movement_type == 'انتداب',
                        Movement.assignment_state != 'مغلق',
                        Movement.from_date <= today,
                        (Movement.to_date == None) | (Movement.to_date >= today),
                        Movement.destination_branch_id.in_(target_branch_ids),
                    )
                    .order_by(Employee.full_name, Movement.id.desc())
                    .all()
                )
                seen = set()
                for m in moves:
                    if m.employee_id in seen:
                        continue
                    seen.add(m.employee_id)
                    rows.append((m, m.employee.branch, m.destination))

        if not rows:
            labels = {'إجازة': 'في إجازة', 'انتداب': 'منتدبين', 'إذن': 'عندهم إذن'}
            return {
                'title': f'{labels[mt]} اليوم — {location_label}',
                'answer': f'لا يوجد موظفون {labels[mt]} اليوم في {location_label}.',
            }

        lines = []
        for (i, (m, origin, dest)) in enumerate(rows, 1):
            e = m.employee
            if mt == 'إجازة':
                detail = f'{m.leave_type or 'إجازة'} — حتى {m.to_date}'
            elif mt == 'إذن':
                detail = f'إذن اليوم — {m.permission_date}'
            else:
                direction = f'{(origin.name if origin else 'غير محدد')} → {(dest.name if dest else 'غير محدد')}'
                detail = f'{direction} — ' + ('مفتوح' if m.to_date is None else f'حتى {m.to_date}')
            branch_name = e.branch.name if e.branch else 'غير محدد'
            lines.append(f'{i}. {e.full_name} — {detail} — فرع التعيين: {branch_name}')
        labels = {
            'إجازة': 'الموظفون في إجازة',
            'انتداب': 'الموظفون المنتدبون',
            'إذن': 'الموظفون لديهم إذن',
        }
        return {
            'title': f'{labels[mt]} اليوم — {location_label}',
            'answer': f'{labels[mt]} اليوم في {location_label}: {len(rows)}\n\n' + '\n'.join(lines),
        }

    if intent == 'governorate_assignments_today':
        gid = a.get('governorate_id')
        gov = db.session.get(Governorate, gid) if gid else None
        allowed_gids = set(gids())
        if not gov or not gov.is_active or (allowed_gids and gov.id not in allowed_gids):
            return {
                'title': 'انتدابات اليوم',
                'error': 'لا توجد محافظة مطابقة أو ليست ضمن نطاق صلاحياتك.',
            }
        branches = (
            Branch.query.filter_by(governorate_id=gov.id, is_active=True)
            .order_by(Branch.name)
            .all()
        )
        branches = [b for b in branches if branch_ok(b.id)]
        branch_ids = {b.id for b in branches}
        rows = []
        # الانتداب الحالي إلى فرع داخل المحافظة.
        for e in (
            Employee.query.filter(Employee.is_active == True)
            .order_by(Employee.full_name)
            .all()
        ):
            m = current_assignment_for_employee(e.id, date.today())
            if not m or not m.destination_branch_id or m.destination_branch_id not in branch_ids:
                continue
            dest = db.session.get(Branch, m.destination_branch_id)
            origin = e.branch
            rows.append((e, m, origin, dest))
        if not rows:
            return {
                'title': f'منتدبو اليوم في محافظة {gov.name}',
                'answer': f'لا يوجد موظفون منتدبون حاليًا إلى فروع محافظة {gov.name} اليوم.',
            }
        lines = []
        for (i, (e, m, origin, dest)) in enumerate(rows, 1):
            period = 'مفتوح' if m.to_date is None else f'حتى {m.to_date}'
            direction = f'{(origin.name if origin else 'غير محدد')} → {(dest.name if dest else 'غير محدد')}'
            lines.append(
                f'{i}. {e.full_name} — {direction} — من {m.from_date or 'غير محدد'} — {period}',
            )
        return {
            'title': f'منتدبو اليوم في محافظة {gov.name}',
            'answer': f'عدد المنتدبين إلى فروع المحافظة اليوم: {len(rows)}\n\n' + '\n'.join(lines),
        }
    if intent == 'governorate_employees':
        gid = a.get('governorate_id')
        gov = db.session.get(Governorate, gid) if gid else None
        allowed_gids = set(gids())
        if not gov or not gov.is_active or (allowed_gids and gov.id not in allowed_gids):
            return {
                'title': 'موظفو المحافظة',
                'error': 'لا توجد محافظة مطابقة أو ليست ضمن نطاق صلاحياتك.',
            }
        branches = (
            Branch.query.filter_by(governorate_id=gov.id, is_active=True)
            .order_by(Branch.name)
            .all()
        )
        branches = [b for b in branches if branch_ok(b.id)]
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
    if intent == 'employee_status':
        e = db.session.get(Employee, a.get('employee_id')) if a.get('employee_id') else None
        if not e or not e.is_active or (not branch_ok(e.branch_id)):
            return {
                'title': 'نتيجة البحث',
                'error': 'لم أجد موظفًا واحدًا مطابقًا.',
                'choices': [
                    db.session.get(Employee, i)
                    for i in a.get('candidate_ids', [])
                    if db.session.get(Employee, i)
                ],
            }
        cur = current_assignment_for_employee(e.id)
        display_branch = cur.destination if cur and cur.destination else e.branch
        state = employee_status_text(e)
        return {
            'title': 'حالة الموظف',
            'answer': f'الموظف: {e.full_name}\nالفرع الحالي: {(display_branch.name if display_branch else '—')}\nفرع التعيين: {(e.branch.name if e.branch else '—')}\nالمحافظة: {(display_branch.governorate.name if display_branch and display_branch.governorate else '—')}\nالحالة الآن: {state}',
        }
    if intent in ('branch_status', 'branch_info'):
        b = db.session.get(Branch, a.get('branch_id')) if a.get('branch_id') else None
        if not b or not branch_ok(b.id):
            return {
                'title': 'نتيجة البحث',
                'error': 'لم أجد فرعًا واحدًا مطابقًا.',
                'choices': [
                    db.session.get(Branch, i)
                    for i in a.get('candidate_ids', [])
                    if db.session.get(Branch, i)
                ],
            }
        employees = employees_effectively_in_branches([b.id])
        entry_links = (
            EntryAssignmentBranch.query.join(EntryAssignment)
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
        inbound = []
        for e in employees:
            cur = current_assignment_for_employee(e.id)
            if cur and cur.destination_branch_id == b.id and (e.branch_id != b.id):
                inbound.append((e, cur))

        on_duty = sum((1 for e in employees if employee_status_text(e) == 'على رأس العمل'))
        leave_count = sum((1 for e in employees if 'إجازة' in employee_status_text(e)))
        assignment_count = sum(
            1
            for e in employees
            if 'انتداب' in employee_status_text(e)
        )
        permission_count = sum(
            1
            for e in employees
            if employee_status_text(e) == 'إذن اليوم'
        )

        def esc(v):
            return str(escape(v if v is not None else ''))

        cards = [
            f'<div class="branch-data-card"><b>اسم الفرع</b><strong>{esc(b.name)}</strong></div>',
            f'<div class="branch-data-card"><b>كود الفرع</b><strong>{esc(b.code or 'غير محدد')}</strong></div>',
            f'<div class="branch-data-card"><b>المحافظة</b><strong>{esc(b.governorate.name)}</strong></div>',
            f'<div class="branch-data-card"><b>الموظفون حاليًا</b><strong>{len(employees)}</strong></div>',
            f'<div class="branch-data-card"><b>على رأس العمل</b><strong>{on_duty}</strong></div>',
            f'<div class="branch-data-card"><b>إجازة</b><strong>{leave_count}</strong></div>',
            f'<div class="branch-data-card"><b>انتداب</b><strong>{assignment_count}</strong></div>',
            f'<div class="branch-data-card"><b>إذن اليوم</b><strong>{permission_count}</strong></div>',
        ]
        management = f'<div class="branch-management-row"><div class="branch-management-item"><span>المدخل الأول المسؤول</span><b>{esc(', '.join(dict.fromkeys(entry_names)) if entry_names else 'غير محدد')}</b></div><div class="branch-management-item"><span>المشرف</span><b>{esc(', '.join(dict.fromkeys(supervisors)) if supervisors else 'غير محدد')}</b></div></div>'

        current_cards = []
        for e in employees:
            cur = current_assignment_for_employee(e.id)
            status = employee_status_text(e)
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
    if intent == 'employee_info':
        e = db.session.get(Employee, a.get('employee_id')) if a.get('employee_id') else None
        if not e or not e.is_active or (not branch_ok(e.branch_id)):
            return {
                'title': 'نتيجة البحث',
                'error': 'لم أجد موظفًا واحدًا مطابقًا.',
                'choices': [
                    db.session.get(Employee, i)
                    for i in a.get('candidate_ids', [])
                    if db.session.get(Employee, i)
                ],
            }
        cur = current_assignment_for_employee(e.id)
        cb = cur.destination if cur and cur.destination else e.branch
        ms = (
            Movement.query.filter_by(employee_id=e.id, is_active=True)
            .order_by(Movement.id.desc())
            .all()
        )

        def latest(kind):
            return next((m for m in ms if m.movement_type == kind), None)

        leave = latest('إجازة')
        assignment = latest('انتداب')
        permission = latest('إذن')
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
            f'الحالة الآن: {employee_status_text(e)}',
            f'كود الموظف: {e.job_code or 'لا توجد بيانات'}',
            f'الوظيفة: {e.job_title or 'لا توجد بيانات'}',
            f'المحافظة: {(cb.governorate.name if cb and cb.governorate else 'لا توجد بيانات')}',
            f'فرع التعيين: {(e.branch.name if e.branch else 'لا توجد بيانات')}',
            f'الفرع الحالي: {(cb.name if cb else 'لا توجد بيانات')}',
            f'تاريخ التعيين: {e.hire_date or 'لا توجد بيانات'}',
            f'آخر إجازة: {movement_text(leave)}',
            f'آخر انتداب: {movement_text(assignment)}',
            f'آخر إذن: {movement_text(permission)}',
        ]
        return {
            'title': f'بطاقة الموظف — {e.full_name}',
            'answer': '\n'.join(lines),
            'actions': [
                {'label': 'الوظيفة', 'url': '#', 'prompt': f'ما وظيفة {e.full_name}؟'},
                {'label': 'آخر إجازة', 'url': '#', 'prompt': f'ما آخر إجازة لـ {e.full_name}؟'},
                {'label': 'آخر انتداب', 'url': '#', 'prompt': f'ما آخر انتداب لـ {e.full_name}؟'},
                {'label': 'آخر إذن', 'url': '#', 'prompt': f'ما آخر إذن لـ {e.full_name}؟'},
                {'label': 'سجل الحركات', 'url': '#', 'prompt': f'اعرض سجل حركات {e.full_name}'},
            ],
        }
    if intent == 'employee_movements':
        e = db.session.get(Employee, a.get('employee_id')) if a.get('employee_id') else None
        if not e or not branch_ok(e.branch_id):
            return {
                'title': 'نتيجة البحث',
                'error': 'لم أجد موظفًا واحدًا مطابقًا.',
                'choices': [
                    db.session.get(Employee, i)
                    for i in a.get('candidate_ids', [])
                    if db.session.get(Employee, i)
                ],
            }
        ms = (
            Movement.query.filter_by(employee_id=e.id, is_active=True)
            .order_by(Movement.id.desc())
            .limit(30)
            .all()
        )
        if not ms:
            ans = f'{e.full_name}: لا توجد حركات مسجلة.'
        else:
            lines = []
            for m in ms:
                detail = m.leave_type or (m.destination.name if m.destination else '') or ''
                period = (
                    m.permission_date
                    or (f'{m.from_date} إلى {m.to_date}' if m.from_date or m.to_date else '')
                )
                lines.append(f'{m.movement_type} — {detail} — {period} — {m.status}')
            ans = f'سجل حركات {e.full_name}:\n' + '\n'.join(lines)
        return {'title': 'سجل حركات الموظف', 'answer': ans}
    # لا تعرض أمثلة محفوظة عند تعذر التصنيف؛ اترك المساعد يطلب التوضيح بصورة طبيعية.
    return {'title': 'المساعد الذكي', 'answer': 'ما زلت أحتاج إلى تحديد المقصود من طلبك.'}
