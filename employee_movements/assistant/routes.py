"""Assistant chat endpoints."""

from flask import abort, Blueprint, current_app, flash, redirect, render_template, request, session

from ..access import branch_ok, can, log, me, req
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement
from ..validation import (
    movement_overlaps,
    parse_date,
    record_movement_history,
    validate_movement_fields,
)
from .directory import find_branch, find_employee
from .intents import detect_employee_field, greeting_reply, parse_intent
from .llm import llm_parse
from ..ratelimit import RateLimiter
from .menu import capability_groups
from .manager import plan as manager_plan, execute as manager_execute
from .render import render_branch_entry, render_read, topic_options

bp = Blueprint('assistant', __name__)


MAX_PROMPT_CHARS = 1000
MAX_HISTORY = 16
MAX_HISTORY_TEXT_CHARS = 600
_assistant_limiter = None


def assistant_limiter():
    """One shared limiter per process, sized from ``ASSISTANT_RATE_LIMIT`` requests/minute."""
    global _assistant_limiter
    if _assistant_limiter is None:
        _assistant_limiter = RateLimiter(current_app.config['ASSISTANT_RATE_LIMIT'], 60)
    return _assistant_limiter


def history_text(result):
    """Plain-text summary stored in the session.

    The session lives in a size-limited cookie, so rich HTML cards are never stored;
    only a short text is kept for conversational context.
    """
    text = (
        result.get('answer')
        or result.get('error')
        or result.get('preview')
        or result.get('title')
        or 'تمت معالجة طلبك.'
    )
    return str(text)[:MAX_HISTORY_TEXT_CHARS]


def answer_prompt(prompt, prior_chat):
    """Understand ``prompt`` (local rules first, LLM only when needed) and build the reply."""
    result = None
    # ابدأ ببيانات التطبيق الحية أولاً. هذا يجعل الاستفسارات الشائعة فورية ولا تنتظر نموذجًا خارجيًا.
    local_a = parse_intent(prompt)
    # استخدم Gemini خصوصًا في الطلبات التنفيذية؛ هذا يسمح بفهم الصياغات الحرة
    # مثل «اعمل لأحمد إجازة...» حتى عندما لا تطابق قواعد الاستخراج المحلية حرفيًا.
    # الاستعلامات المباشرة تظل محلية أولًا لتقليل التأخير وعدم إرسال بيانات حية إلى النموذج.
    semantic_intents = {'help', 'topic_options', 'employee_topic', 'register_movement', 'employee_add', 'employee_create', 'user_create', 'user_edit', 'user_toggle', 'user_delete', 'user_password_reset', 'user_set_governorates', 'user_set_branches', 'entry_assign', 'entry_remove', 'entry_replace', 'delegation_create', 'delegation_revoke', 'governorate_create', 'governorate_edit', 'governorate_toggle', 'branch_create', 'branch_edit', 'branch_toggle', 'employee_edit', 'employee_delete', 'employee_restore', 'role_grant', 'role_revoke', 'lookup_create', 'lookup_edit', 'lookup_toggle', 'lookup_delete', 'movement_edit', 'movement_delete', 'movement_close'}
    read_only_local = {'greeting', 'employee_status', 'employee_info', 'employee_movements', 'branch_status', 'branch_info', 'branch_entry', 'governorate_employees', 'governorate_assignments_today', 'movement_people_today'}
    manager_markers = ('امنح دور','منح دور','اسحب دور','إزالة دور','ازالة دور','عدّل حساب','عدل حساب','أضف حساب','اضف حساب','احذف حساب','أوقف حساب','أنشئ تفويض','انشئ تفويض','أضف محافظة','اضف محافظة','عدّل محافظة','عدل محافظة','أضف فرع','اضف فرع','عدّل فرع','عدل فرع','احذف موظف','احذف الموظف','استرجع موظف','استرجع الموظف','عيّن مدخل','عين مدخل','أزل دور المدخل','أزل المدخل','أضف نوع','اضف نوع','عطّل','عطل','فعّل','فعل','غيّر محافظات','غير محافظات','غيّر فروع','غير فروع','احذف حركة','حذف حركة','عدّل حركة','عدل حركة','تعديل حركة','أنهى الانتداب','انهاء الانتداب','أغلق الانتداب','اغلاق الانتداب')
    has_manager_marker = any(x in prompt for x in manager_markers)
    # مدير التطبيق يحتاج فهمًا دلاليًا حتى للطلبات الإدارية التي لا توجد لها
    # قاعدة كلمات محلية. الاستعلامات التي حلّها المسار المحلي بشكل يقيني تبقى محلية
    # ما لم تحمل صياغة صريحة لعملية إدارية.
    needs_semantic = local_a.get('intent') not in read_only_local or has_manager_marker
    llm_a = llm_parse(prompt, prior_chat) if needs_semantic else None
    if llm_a:
        a = local_a if local_a.get('intent') in read_only_local and not has_manager_marker else llm_a
        # إذا فهم Gemini طلبًا تنفيذيًا بشكل أوضح، نستخدمه ثم نحل الكيانات محليًا.
        # أما في الاستعلامات العامة، يبقى التعرف المحلي هو مصدر الحقيقة.
        if (
            local_a.get('intent') not in ('register_movement', 'employee_add')
            and a.get('intent') in ('help', 'topic_options', 'employee_topic')
        ):
            a = local_a
        # إذا أعاد النموذج تصنيفاً عاماً جداً (help) بينما يستطيع التطبيق
        # التعرف على النص مباشرة من بياناته، نستخدم التعرف المحلي الدقيق بدلاً
        # من مطالبة المستخدم بإعادة صياغة كلامه. هذا ليس قاموس كلمات؛ بل بحث فعلي
        # في كيانات قاعدة البيانات.
        if (
            a.get('intent') in ('help', 'topic_options', 'employee_topic')
            and local_a.get('intent') in ('employee_info', 'employee_status', 'employee_movements')
        ):
            a = local_a
        elif a.get('intent') == 'help' and local_a.get('intent') not in ('help',):
            a = local_a
        # حل أسماء/كيانات المستخدم على الخادم بعد الفهم الدلالي، دون فرض كلمات محددة.
        if not a.get('employee_id') and a.get('employee_name'):
            (ee, mm) = find_employee(a.get('employee_name'))
            if ee:
                a['employee_id'] = ee.id
            elif mm:
                a['candidate_ids'] = [e.id for e in mm[:10]]
        if not a.get('branch_id') and a.get('branch_name'):
            (bb, mm) = find_branch(a.get('branch_name'))
            if bb:
                a['branch_id'] = bb.id
            elif mm:
                a['candidate_ids'] = [b.id for b in mm[:10]]
        if not a.get('governorate_id') and a.get('governorate_name'):
            gg = [
                g
                for g in Governorate.query.filter_by(is_active=True).all()
                if a.get('governorate_name', '').strip().lower() in (g.name or '').lower()
            ]
            if len(gg) == 1:
                a['governorate_id'] = gg[0].id
    else:
        a = local_a
    field = detect_employee_field(prompt)
    if field:
        a['employee_field'] = field
    if not a.get('employee_id') and session.get('assistant_context_employee_id') and field:
        ce = db.session.get(Employee, session.get('assistant_context_employee_id'))
        if ce and ce.is_active and branch_ok(ce.branch_id):
            a['employee_id'] = ce.id
            if a.get('intent') in ('help', 'topic_options', 'employee_topic'):
                a['intent'] = (
                    'employee_status'
                    if field == 'status'
                    else 'employee_movements' if field == 'movements' else 'employee_info'
                )
    # سياق الموظف الأخير: إذا ذكر المستخدم إجراءً جديدًا مباشرة بعد عرض موظف،
    # نستخدم الموظف الأخير تلقائيًا ما لم يحدد موظفًا آخر.
    if not a.get('employee_id') and session.get('assistant_context_employee_id'):
        if (
            a.get('intent') == 'register_movement'
            or a.get('topic') in ('leave', 'assignment', 'permission')
        ):
            ce = db.session.get(Employee, session.get('assistant_context_employee_id'))
            if ce and ce.is_active and branch_ok(ce.branch_id):
                a['employee_id'] = ce.id
    manager_intents = {
        'governorate_create', 'governorate_edit', 'governorate_toggle',
        'branch_create', 'branch_edit', 'branch_toggle',
        'employee_create', 'employee_edit', 'employee_delete', 'employee_restore',
        'user_create', 'user_edit', 'user_toggle', 'user_delete', 'user_password_reset',
        'user_set_governorates', 'user_set_branches',
        'role_grant', 'role_revoke', 'entry_assign', 'entry_remove', 'entry_replace',
        'delegation_create', 'delegation_revoke',
        'lookup_create', 'lookup_edit', 'lookup_toggle', 'lookup_delete', 'movement_edit', 'movement_delete', 'movement_close',
    }
    if a.get('intent') in manager_intents:
        result = manager_plan(a)
        if result and result.get('plan'):
            session['assistant_manager_pending'] = result['plan']
        if result is None:
            result = {'title': 'مدير التطبيق', 'error': 'لم أستطع تحديد العملية الإدارية.'}
    elif a.get('intent') == 'greeting':
        result = {
            'title': 'المساعد الذكي',
            'answer': a.get('reply') or greeting_reply(prompt),
        }
    elif a.get('intent') == 'topic_options':
        result = topic_options(a.get('topic'))
        # لا تستخدم رسالة خيارات عامة إذا أعاد النموذج ردًا طبيعيًا أكثر تحديدًا.
        if a.get('reply') and (not result.get('answer')):
            result['answer'] = a.get('reply')
    elif a.get('intent') == 'employee_topic':
        # موضوع عام مثل اسم موظف/الموظفين: اعرض ما فهمه النظام فقط، دون أمثلة ثابتة.
        result = topic_options('employee')
    elif a.get('intent') == 'employee_add':
        if not can('manage_employees'):
            result = {
                'title': 'إضافة موظف جديد',
                'error': 'لا تملك صلاحية إضافة موظف جديد.',
            }
        else:
            result = {
                'title': 'إضافة موظف جديد',
                'answer': 'بالتأكيد. يمكنك إضافة موظف جديد. سأفتح لك شاشة الإضافة مباشرة لتسجيل البيانات المطلوبة: المحافظة، الفرع، الاسم، البريد الإلكتروني، الوظيفة، الكود الوظيفي، تاريخ التعيين، هاتف الشركة والهاتف الشخصي.',
                'actions': [{'label': 'بدء إضافة موظف جديد', 'url': '/employees'}],
            }
    elif a.get('intent') == 'navigate':
        nav = a.get('navigate_url') or ''
        topic_map = {
            'reports': '/reports/leaves',
            'admin': '/structure',
            'users': '/users',
            'delegation': '/delegations',
            'replacement': '/replacement',
            'audit': '/audit',
        }
        if not nav:
            nav = topic_map.get(a.get('topic'), '')
        allowed = {
            '/employees': 'manage_employees',
            '/employees/edit-data': 'manage_employees',
            '/employees/resigned': 'manage_employees',
            '/structure': 'manage_structure',
            '/governorates': 'manage_structure',
            '/branches': 'manage_structure',
            '/replacement': 'manage_structure',
            '/users': 'manage_users',
            '/delegations': 'manage_users',
            '/movements': 'manage_movements',
            '/audit': 'view_audit',
            '/lookups': 'view_audit',
            '/reports/leaves': 'view_reports',
            '/reports/assignments': 'view_reports',
            '/reports/permissions': 'view_reports',
            '/reports/assignments/print-missions': 'view_reports',
        }
        if nav not in allowed:
            result = {
                'title': 'المساعد الذكي',
                'answer': a.get('reply') or 'وضح لي الوظيفة أو التقرير الذي تريده.',
            }
        elif not can(allowed[nav]):
            result = {
                'title': 'الصلاحيات',
                'error': 'هذا الإجراء غير متاح ضمن صلاحيات دورك الحالي.',
            }
        else:
            result = {
                'title': 'المساعد الذكي',
                'answer': a.get('reply') or 'سأفتح لك الوظيفة المطلوبة.',
                'actions': [{'label': 'فتح', 'url': nav}],
            }
    elif a.get('intent') == 'help':
        # help هنا يعني أن النموذج لم يجد عملية آمنة محددة؛ استخدم رده الطبيعي إن وُجد،
        # ولا تعُد إلى قائمة أمثلة محفوظة.
        result = {
            'title': 'المساعد الذكي',
            'answer': (
                a.get('reply')
                or 'ما الذي تريد معرفته أو تنفيذه بخصوص البيانات الظاهرة أمامنا؟'
            ),
        }
    elif a.get('intent') == 'register_movement':
        if not can('manage_movements'):
            result = {'title': 'تسجيل حركة', 'error': 'لا تملك صلاحية تسجيل الحركات.'}
        elif not a.get('employee_id'):
            result = {
                'title': 'تحديد الموظف',
                'error': 'لم أستطع تحديد موظف واحد. اكتب الاسم بشكل أوضح.',
                'choices': [
                    db.session.get(Employee, i)
                    for i in a.get('candidate_ids', [])
                    if db.session.get(Employee, i)
                ],
            }
        else:
            e = db.session.get(Employee, a['employee_id'])
            dest = (
                db.session.get(Branch, a.get('destination_branch_id'))
                if a.get('destination_branch_id')
                else None
            )
            mt = a.get('movement_type')
            if mt == 'إجازة' and (not a.get('leave_type')):
                result = {
                    'title': 'نوع الإجازة',
                    'answer': 'ما نوع الإجازة التي تريد تسجيلها؟',
                }
            elif mt in ('إجازة', 'انتداب') and (not a.get('from_date')):
                result = {'title': 'تاريخ البداية', 'answer': 'ما تاريخ بداية الحركة؟'}
            elif (
                mt == 'انتداب'
                and not a.get('open_assignment')
                and not a.get('to_date')
            ):
                result = {
                    'title': 'تاريخ نهاية الانتداب',
                    'answer': 'هل الانتداب مفتوح بدون تاريخ نهاية، أم له تاريخ نهاية؟',
                }
            elif mt == 'إجازة' and (not a.get('to_date')):
                result = {'title': 'تاريخ النهاية', 'answer': 'ما تاريخ نهاية الإجازة؟'}
            elif mt == 'إذن' and (not a.get('permission_date')):
                result = {'title': 'تاريخ الإذن', 'answer': 'ما تاريخ الإذن؟'}
            elif (
                mt == 'انتداب'
                and not a.get('destination_name')
                and not a.get('destination_branch_id')
            ):
                result = {'title': 'فرع الانتداب', 'answer': 'إلى أي فرع سيكون الانتداب؟'}
            elif (
                mt == 'انتداب'
                and a.get('destination_name')
                and not a.get('destination_branch_id')
            ):
                (dest, matches_dest) = find_branch(a.get('destination_name'))
                if not dest:
                    result = {
                        'title': 'تحديد فرع الانتداب',
                        'error': 'لم أجد فرعًا مطابقًا.',
                        'choices': matches_dest[:10],
                    }
                else:
                    a['destination_branch_id'] = dest.id
            if result is None:
                dest = (
                    db.session.get(Branch, a.get('destination_branch_id'))
                    if a.get('destination_branch_id')
                    else dest
                )
                err = validate_movement_fields(
                    a.get('movement_type'),
                    a.get('leave_type'),
                    dest.id if dest else None,
                    a.get('from_date'),
                    None if a.get('open_assignment') else a.get('to_date'),
                    a.get('permission_date'),
                )
                if err:
                    result = {'title': 'مراجعة الحركة', 'error': err}
                elif not e or not branch_ok(e.branch_id):
                    result = {'title': 'تسجيل حركة', 'error': 'الموظف خارج نطاق صلاحياتك.'}
                elif (
                    a.get('movement_type') == 'انتداب'
                    and (not dest or not branch_ok(dest.id))
                ):
                    result = {
                        'title': 'تسجيل انتداب',
                        'error': 'فرع الانتداب غير موجود أو خارج نطاق صلاحياتك.',
                    }
                elif movement_overlaps(
                    e.id,
                    a['movement_type'],
                    a.get('from_date'),
                    None if a.get('open_assignment') else a.get('to_date'),
                    a.get('permission_date'),
                ):
                    result = {
                        'title': 'تعارض في الحركة',
                        'error': movement_overlaps(
                            e.id,
                            a['movement_type'],
                            a.get('from_date'),
                            None if a.get('open_assignment') else a.get('to_date'),
                            a.get('permission_date'),
                        ),
                    }
                else:
                    session['assistant_pending'] = a
                    dest_text = (
                        f' إلى {dest.governorate.name} — {dest.name}'
                        if dest
                        else ''
                    )
                    period = (
                        f' من {a.get('from_date')} — انتداب مفتوح'
                        if (
                            a.get('movement_type') == 'انتداب'
                            and not a.get('to_date')
                            and a.get('from_date')
                        )
                        else (
                            f' من {a.get('from_date')} إلى {a.get('to_date')}'
                            if a.get('from_date')
                            else (
                                f' بتاريخ {a.get('permission_date')}'
                                if a.get('permission_date')
                                else ''
                            )
                        )
                    )
                    result = {
                        'title': 'تأكيد تسجيل الحركة',
                        'preview': f'{a['movement_type']} للموظف {e.full_name}{dest_text}{period}',
                    }
    else:
        if a.get('intent') == 'branch_entry':
            result = render_branch_entry(a)
        else:
            result = render_read(a)
        if a.get('employee_id') and db.session.get(Employee, a.get('employee_id')):
            session['assistant_context_employee_id'] = a.get('employee_id')
    return result


@bp.route('/assistant', methods=['GET', 'POST'])
@req
def assistant():
    result = None
    prompt = ''
    chat = session.get('assistant_chat', [])
    if request.method == 'POST':
        prompt = (request.form.get('prompt') or '').strip()[:MAX_PROMPT_CHARS]
        if not prompt:
            result = {'title': 'المساعد الذكي', 'error': 'اكتب طلبك أولًا.'}
        elif not assistant_limiter().allow(f'{me().id}'):
            result = {
                'title': 'المساعد الذكي',
                'error': 'عدد الطلبات كبير. انتظر دقيقة ثم حاول مرة أخرى.',
            }
        else:
            prior_chat = list(chat)
            chat.append({'role': 'user', 'text': prompt})
            result = answer_prompt(prompt, prior_chat)
        if prompt and result:
            chat.append(
                {
                    'role': 'assistant',
                    'text': history_text(result),
                    'title': result.get('title', 'المساعد الذكي'),
                },
            )
            session['assistant_chat'] = chat[-MAX_HISTORY:]
    groups = capability_groups()
    embed = request.args.get('embed') == '1'
    return render_template(
        'assistant_embed.html' if embed else 'assistant.html',
        result=result,
        prompt=prompt,
        assistant_options=[item for group in groups for item in group['items']],
        assistant_option_groups=groups,
        embed=embed,
        chat=session.get('assistant_chat', []),
    )


@bp.post('/assistant/clear')
@req
def assistant_clear():
    session.pop('assistant_chat', None)
    session.pop('assistant_pending', None)
    session.pop('assistant_manager_pending', None)
    return redirect('/assistant?embed=1' if request.form.get('embed') == '1' else '/assistant')


@bp.post('/assistant/confirm')
@req
def assistant_confirm():
    embed = request.form.get('embed') == '1'
    back = '/assistant?embed=1' if embed else '/assistant'
    if request.form.get('cancel'):
        session.pop('assistant_pending', None)
        session.pop('assistant_manager_pending', None)
        flash('تم إلغاء العملية ولم يُنفذ أي تغيير.')
        return redirect(back)
    manager_pending = session.pop('assistant_manager_pending', None)
    if manager_pending:
        ok, message = manager_execute(manager_pending)
        if ok:
            flash(message)
        else:
            flash(message)
        return redirect(back)
    a = session.pop('assistant_pending', None)
    if not a:
        flash('لا توجد عملية معلقة للتأكيد.')
        return redirect(back)
    if not can('manage_movements'):
        abort(403)
    e = db.session.get(Employee, a.get('employee_id'))
    dest = (
        db.session.get(Branch, a.get('destination_branch_id'))
        if a.get('destination_branch_id')
        else None
    )
    if not e or not e.is_active or (not branch_ok(e.branch_id)):
        flash('الموظف خارج نطاق صلاحياتك.')
        return redirect(back)
    err = validate_movement_fields(
        a.get('movement_type'),
        a.get('leave_type'),
        dest.id if dest else None,
        a.get('from_date'),
        None if a.get('open_assignment') else a.get('to_date'),
        a.get('permission_date'),
    )
    if err:
        flash(err)
        return redirect(back)
    if a.get('movement_type') == 'انتداب' and (not dest or not branch_ok(dest.id)):
        flash('فرع الانتداب غير مسموح.')
        return redirect(back)
    overlap = movement_overlaps(
        e.id,
        a['movement_type'],
        a.get('from_date'),
        None if a.get('open_assignment') else a.get('to_date'),
        a.get('permission_date'),
    )
    if overlap:
        flash(overlap)
        return redirect(back)
    m = Movement(
        employee_id=e.id,
        movement_type=a['movement_type'],
        leave_type=a.get('leave_type'),
        destination_branch_id=dest.id if dest else None,
        from_date=parse_date(a.get('from_date')),
        to_date=parse_date(a.get('to_date')),
        permission_date=parse_date(a.get('permission_date')),
        notes=None,
        created_by=me().id,
        status='مسجلة',
        assignment_state='ساري',
    )
    db.session.add(m)
    db.session.flush()
    record_movement_history(m, None, 'مسجلة', 'AI_ASSISTANT_ADD', 'تسجيل الحركة من المساعد الذكي')
    log('AI_ASSISTANT_ADD', 'Movement', m.id, f'{m.movement_type} — {e.full_name}')
    db.session.commit()
    flash('تم تسجيل الحركة بنجاح من خلال المساعد الذكي.')
    return redirect(back)
