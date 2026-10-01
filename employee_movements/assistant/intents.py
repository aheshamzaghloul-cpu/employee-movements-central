"""Rule-based intent and entity extraction from Arabic prompts."""

import re

from ..access import can
from ..models import Governorate
from ..validation import active_leave_types
from .directory import find_branch, find_employee
from .text import extract_date, normalize_digits, normalize_for_search


def is_greeting(text):
    n = normalize_for_search(text)
    greetings = (
        'السلام عليكم',
        'السلام عليكم ورحمة الله وبركاته',
        'وعليكم السلام',
        'صباح الخير',
        'مساء الخير',
        'اهلا',
        'اهلاً',
        'مرحبا',
        'مرحباً',
        'هاي',
        'هلا',
        'السلام عليكم ورحمة الله وبركاته',
    )
    return any(
        n == normalize_for_search(g) or n.startswith(normalize_for_search(g) + ' ')
        for g in greetings
    )


def greeting_reply(text):
    n = normalize_for_search(text)
    if 'صباح الخير' in n:
        return 'صباح النور ☀️ أهلاً بك. أنا معك، ويمكنك سؤالي عن أي موظف أو فرع أو حركة أو تنفيذ أي إجراء متاح لك.'
    if 'مساء الخير' in n:
        return 'مساء النور 🌙 أهلاً بك. أنا معك، ويمكنك سؤالي عن أي موظف أو فرع أو حركة أو تنفيذ أي إجراء متاح لك.'
    if 'السلام عليكم' in n:
        return 'وعليكم السلام ورحمة الله وبركاته 🌷 أهلاً بك. كيف أساعدك؟'
    return 'أهلاً بك 🌷 كيف أساعدك؟'


def detect_employee_field(text):
    n = normalize_for_search(text)
    if any(
        x in n
        for x in ('الحاله', 'حالته', 'حالته الان', 'حاله الموظف', 'متواجد', 'موجود', 'في اجازه', 'منتدب')
    ):
        return 'status'
    if any((x in n for x in ('الوظيفه', 'وظيفته', 'المسمى الوظيفي', 'المسمى الوظيفى'))):
        return 'job_title'
    if any(
        x in n
        for x in ('الكود الوظيفي', 'الكود الوظيفى', 'كود الموظف', 'كود شئون العاملين', 'كود شؤون العاملين', 'كود شئون')
    ):
        return 'job_code'
    if any(
        x in n
        for x in ('فرع التعيين', 'فرعه', 'فرع الموظف', 'الفرع الحالي', 'فين فرعه', 'اين فرعه', 'اين يعمل', 'بيشتغل فين')
    ):
        return 'branch'
    if any((x in n for x in ('المحافظه', 'محافظته', 'تابع لاي محافظه', 'تابع لاى محافظه'))):
        return 'governorate'
    if any((x in n for x in ('تاريخ التعيين', 'اتعين امتى', 'تاريخ تعيينه'))):
        return 'hire_date'
    if any((x in n for x in ('هاتف الشركه', 'تليفون الشركه', 'هاتف العمل', 'رقم العمل'))):
        return 'company_phone'
    if any((x in n for x in ('رقم الهاتف', 'رقم التليفون', 'رقم الموبايل', 'التليفون', 'الهاتف'))):
        return 'phone'
    if any((x in n for x in ('الهاتف الشخصي', 'تليفونه الشخصي', 'رقم موبايله', 'رقم هاتفه'))):
        return 'personal_phone'
    if any(
        x in n
        for x in ('اخر اجازه', 'اخر اجازة', 'آخر اجازه', 'آخر إجازة', 'اجازته الاخيره', 'اجازته')
    ):
        return 'last_leave'
    if any(
        x in n
        for x in ('اخر انتداب', 'آخر انتداب', 'انتدابه الاخير', 'اخر ماموريه', 'آخر مأمورية')
    ):
        return 'last_assignment'
    if any((x in n for x in ('اخر اذن', 'آخر إذن', 'اذنه الاخير'))):
        return 'last_permission'
    if any((x in n for x in ('حركاته', 'سجل حركاته', 'سجل حركات', 'تاريخ حركاته', 'كل حركاته'))):
        return 'movements'
    if any(
        x in n
        for x in ('بياناته', 'بيانات الموظف', 'بطاقته', 'بطاقة الموظف', 'معلوماته', 'بيانات')
    ):
        return 'basic'
    return None


def employee_from_mixed_phrase(text):
    cleaned = normalize_digits(text)
    # أزل عبارات السؤال والبيان مع الإبقاء على اسم الموظف، مثل:
    # "ما وظيفة كيرلس" / "رقم الهاتف كيرلس" / "بيانات كيرلس".
    patterns = (
        '\\b(?:ما|ماذا|هل|عايز|اريد|أريد|اعرض|عرض|بيانات|بياناته|بطاقة|بطاقته|حالة|حالته|الموظف|موظفة|موظف)\\b',
        '\\b(?:الوظيفة|وظيفته|المسمى الوظيفي|المسمى الوظيفى|رقم الهاتف|رقم التليفون|رقم الموبايل|الهاتف|التليفون|هاتف العمل|هاتف الشركة|الهاتف الشخصي|الكود الوظيفي|كود شئون العاملين|فرع التعيين|الفرع الحالي|المحافظة|تاريخ التعيين|آخر إجازة|اخر اجازه|آخر انتداب|اخر انتداب|آخر إذن|اخر اذن|حركاته|سجل حركاته|سجل الحركات|بيانات الموظف|معلوماته)\\b',
        '\\b(?:إجازة|اجازة|الإجازة|الاجازه|انتداب|الانتداب|مأمورية|مأموريه|إذن|اذن|الأذن|الاذن)\\b',
        '\\b(?:آخر|اخر|الاخير|الأخير|تفاصيل|تفصيل|سجل|حركات|حركه|حركة)\\b',
        '\\b(?:في|فى|عن|من|لـ|ل|به|له)\\b',
    )
    for pat in patterns:
        cleaned = re.sub(pat, ' ', cleaned, flags=re.I)
    cleaned = re.sub('[؟?،,؛;:]+', ' ', cleaned)
    cleaned = re.sub('\\s+', ' ', cleaned).strip()
    return find_employee(cleaned) if cleaned else (None, [])


def parse_intent(text):
    t = normalize_digits(text)
    if is_greeting(t):
        return {'intent': 'greeting', 'reply': greeting_reply(t)}
    # فهم لغوي مرن: نطبع الصيغ الشائعة ونفسر المقصود حتى لو لم يستخدم المستخدم
    # نفس تسمية الزر داخل التطبيق.
    low = t.lower()
    # تطبيع إضافي خاص بفهم النوايا: يسمح بتطابق الهمزات، ى/ي، ة/ه،
    # والتشكيل دون تغيير النص الأصلي المستخدم في استخراج الأسماء والتواريخ.
    intent_norm = normalize_for_search(t)

    def has_any(*words):
        # المطابقة على النص الأصلي + النص الموحّد حتى تعمل مثلاً: إجازة/اجازة/اجازه
        # وكذلك منى/مني وهكذا.
        return any(
            w in t or w in low or normalize_for_search(w) in intent_norm
            for w in words
        )

    # عبارات موضوعية مباشرة: أي صياغة تدل على الإجازة/الانتداب/الإذن/المدخل الأول.
    leave_words = ('إجازة', 'اجازة', 'اجازات', 'الإجازات', 'الاجازات', 'عطلة', 'عطلات')
    assign_words = ('انتداب', 'انتدابات', 'مأمورية', 'مأموريات')
    perm_words = ('إذن', 'اذن', 'أذونات', 'اذونات')
    entry_words = (
        'مدخل أول',
        'مدخل الاول',
        'مدخل الأول',
        'المدخل الأول',
        'المدخل الاول',
        'مدخلين أوائل',
        'المدخلين الأوائل',
    )
    action_words = (
        'سجل',
        'تسجيل',
        'سجّل',
        'ادخل',
        'إدخال',
        'أدخل',
        'اضف',
        'أضف',
        'إضافة',
        'اعمل',
        'عمل',
        'نفذ',
        'تنفيذ',
        'عين',
        'تعيين',
    )
    employee_words = ('موظف', 'الموظف', 'الموظفين', 'الموظفون', 'موظفة', 'موظفات')
    employee_add_words = (
        'جديد',
        'جديدة',
        'إضافة',
        'اضافة',
        'أضف',
        'اضف',
        'إدخال',
        'ادخال',
        'تعيين',
    )
    # v35.46 — استعلامات الانتداب الحالية حسب المحافظة/التاريخ.
    # مثال: «مين منتدب النهارده فى محافظة سوهاج» يجب أن يفهم كاستعلام
    # عن الانتدابات السارية اليوم داخل المحافظة، وليس كموضوع «انتداب» عام.
    today_words = (
        'النهارده',
        'اليوم',
        'دلوقتي',
        'حاليا',
        'حاليًا',
        'حاليه',
        'الحاليه',
        'الان',
        'الآن',
    )
    if (
        has_any('منتدب', 'منتدبين', 'منتدبة', 'منتدبات', 'انتداب')
        and has_any('مين', 'من', 'اسماء', 'أسماء', 'موظفين', 'الموظفين')
        and has_any(*today_words)
        and has_any('محافظة', 'المحافظه', 'المحافظة', 'في', 'فى', 'داخل')
    ):
        gm = re.search('(?:محافظة|المحافظه|المحافظة)\\s+([^؟?،,؛\\n]+)', t, re.I)
        if gm:
            place = gm.group(1).strip()
        else:
            gm = re.search('(?:في|فى|داخل)\\s+(?:محافظة\\s+)?([^؟?،,؛\\n]+)', t, re.I)
            place = gm.group(1).strip() if gm else ''
        govs = [
            g
            for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
            if place and normalize_for_search(place) in normalize_for_search(g.name)
        ]
        if len(govs) == 1:
            return {
                'intent': 'governorate_assignments_today',
                'governorate_id': govs[0].id,
                'governorate_name': govs[0].name,
            }
        if not govs and place:
            # بعض الصياغات تكون «فى سوهاج» بدون كلمة محافظة.
            govs = [
                g
                for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                if normalize_for_search(place) == normalize_for_search(g.name)
            ]
            if len(govs) == 1:
                return {
                    'intent': 'governorate_assignments_today',
                    'governorate_id': govs[0].id,
                    'governorate_name': govs[0].name,
                }

    # v35.48 — استعلامات الحركة حسب المكان واليوم بصياغة طبيعية.
    # أمثلة: «مين إجازة في الإسكندرية»، «مين انتداب في سوهاج»،
    # «مين إجازة اليوم في طما»، «مين عنده إذن اليوم في طما».
    # وجود «مين» + نوع حركة + مكان يعني بحثًا في البيانات، وليس فتح خيارات الموضوع.
    movement_query_words = has_any('مين', 'من', 'اسماء', 'أسماء', 'موظفين', 'الموظفين', 'الموظفون')
    movement_kind = None
    if has_any(*leave_words):
        movement_kind = 'إجازة'
    elif has_any(*assign_words) or has_any('منتدب', 'منتدبين', 'منتدبة', 'منتدبات'):
        movement_kind = 'انتداب'
    elif has_any(*perm_words):
        movement_kind = 'إذن'
    if (
        movement_query_words
        and movement_kind
        and has_any('في', 'فى', 'داخل', 'بمحافظة', 'بفرع', 'محافظة', 'فرع')
    ):
        pm = re.search(
            '(?:في|فى|داخل|بمحافظة|بفرع|محافظة|فرع)\\s+(?:محافظة\\s+|فرع\\s+)?(.+?)(?:\\s+(?:اليوم|النهارده|دلوقتي|حاليًا|حاليا|الان|الآن))?\\s*$',
            t,
            re.I,
        )
        place = pm.group(1).strip() if pm else ''
        place = (
            re.sub(
                '\\s+(?:اليوم|النهارده|دلوقتي|حاليًا|حاليا|الان|الآن)\\s*$',
                '',
                place,
                flags=re.I,
            )
            .strip(' ؟?,،؛;:')
        )
        # «في محافظة سوهاج» يجب أن تذهب للمحافظة، بينما «في طما» يمكن أن تكون فرعًا.
        explicit_gov = bool(re.search('(?:بمحافظة|محافظة)\\s+', t, re.I))
        explicit_branch = bool(re.search('(?:بفرع|فرع)\\s+', t, re.I))
        # الأولوية للمحافظة عند التطابق التام: إذا كان هناك محافظة باسم «سوهاج»
        # وفرع باسم «سوهاج»، فعبارة «في سوهاج» تعني المحافظة ما لم يقل المستخدم صراحة «فرع سوهاج».
        govs = []
        if not explicit_branch:
            govs = [
                g
                for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                if normalize_for_search(place) == normalize_for_search(g.name)
            ]
            if not govs:
                govs = [
                    g
                    for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                    if normalize_for_search(place) in normalize_for_search(g.name)
                ]
        if len(govs) == 1 and (not explicit_branch):
            return {
                'intent': 'movement_people_today',
                'movement_type': movement_kind,
                'governorate_id': govs[0].id,
                'governorate_name': govs[0].name,
                'place_type': 'governorate',
                'place_name': govs[0].name,
            }
        (br, bmatches) = find_branch(place) if not explicit_gov else (None, [])
        if br and (not explicit_gov):
            return {
                'intent': 'movement_people_today',
                'movement_type': movement_kind,
                'branch_id': br.id,
                'branch_name': br.name,
                'place_type': 'branch',
                'place_name': br.name,
            }

    # استعلام الحركة بدون تحديد مكان: «مين انتداب؟»، «مين إجازة؟»، «مين عنده إذن؟»
    # يُنفذ كبحث عام داخل نطاق صلاحيات المستخدم بدل فتح قائمة الخيارات أو إرجاع «لم أجد».
    if (
        movement_query_words
        and movement_kind
        and not has_any('في', 'فى', 'داخل', 'بمحافظة', 'بفرع', 'محافظة', 'فرع')
    ):
        return {
            'intent': 'movement_people_today',
            'movement_type': movement_kind,
            'place_type': 'all',
            'place_name': 'كل النطاق',
        }

    # استعلامات عامة بصياغة طبيعية: "اسماء موظفين"، "الموظفين في جهينه".
    if has_any(
        'موظفين',
        'الموظفين',
        'الموظفون',
        'اسماء موظفين',
        'أسماء موظفين',
        'اسماء الموظفين',
        'أسماء الموظفين',
    ):
        pm = re.search('(?:في|فى|بـ|ب|داخل)\\s+(?:فرع\\s+)?([^؟?،,؛\\n]+)', t, re.I)
        if pm:
            place = pm.group(1).strip()
            (br, bmatches) = find_branch(place)
            if br:
                return {
                    'intent': 'branch_status',
                    'branch_id': br.id,
                    'branch_name': br.name,
                    'candidate_ids': [b.id for b in bmatches[:10]],
                }
            govs = [
                g
                for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                if normalize_for_search(place) in normalize_for_search(g.name)
            ]
            if len(govs) == 1:
                return {
                    'intent': 'governorate_employees',
                    'governorate_id': govs[0].id,
                    'governorate_name': govs[0].name,
                }
        return {'intent': 'employee_topic'}

    # طلبات مثل: موظف جديد / إضافة موظف / أريد إدخال موظف جديد
    # تُفهم كطلب إدارة موظف، وليس كاستعلام عن موظف موجود.
    if has_any(*employee_words) and has_any(*employee_add_words) and can('manage_employees'):
        return {'intent': 'employee_add'}
    if (
        has_any(*employee_words)
        and has_any('جديد', 'جديدة')
        and not has_any('حالة', 'سجل', 'بيانات', 'فرع')
    ):
        if can('manage_employees'):
            return {'intent': 'employee_add'}
        return {'intent': 'employee_topic'}
    # استعلام ذكي عن المدخل الأول المسؤول عن فرع محدد.
    if (
        has_any(*entry_words)
        and has_any('فرع', 'الفرع')
        and has_any('اسم', 'من هو', 'مين', 'مسؤول', 'مسئول', 'يتبع')
    ):
        bm = re.search('(?:فرع|الفرع)\\s+([^؟?،,؛\\n]+)', t)
        name = bm.group(1).strip() if bm else ''
        (br, matches) = find_branch(name)
        return {
            'intent': 'branch_entry',
            'branch_id': br.id if br else None,
            'branch_name': name,
            'candidate_ids': [b.id for b in matches[:10]],
        }
    # إذا ذكر المستخدم موظفي فرع/العاملين بفرع، فهو استعلام عن موظفي الفرع حتى لو لم يقل
    # حرفيًا "حالة الفرع".
    if (
        has_any('موظفي', 'الموظفين', 'الموظفون', 'العاملين', 'العاملون', 'موظفين')
        and has_any('فرع', 'الفرع')
    ):
        bm = re.search('(?:فرع|الفرع)\\s+([^؟?،,؛\\n]+)', t)
        name = bm.group(1).strip() if bm else ''
        (br, matches) = find_branch(name)
        return {
            'intent': 'branch_status',
            'branch_id': br.id if br else None,
            'branch_name': name,
            'candidate_ids': [b.id for b in matches[:10]],
        }
    # صياغات مثل "إدخال إجازة" و"إضافة إجازة" و"اعمل إجازة" تعني تسجيل إجازة.
    if has_any(*leave_words) and has_any(*action_words):
        mt = 'إجازة'
    elif has_any(*assign_words) and has_any(*action_words):
        mt = 'انتداب'
    elif has_any(*perm_words) and has_any(*action_words):
        mt = 'إذن'
    else:
        mt = None
    if mt:
        em = re.search(
            '(?:للموظف|لـ|ل |الموظف|موظف)\\s*([^،,؛\\n]+?)(?=\\s+(?:من|بتاريخ|في|إجازة|اجازة|انتداب|إذن|اذن)|$)',
            t,
            re.I,
        )
        name = em.group(1).strip() if em else ''
        (emp, matches) = find_employee(name)
        dates = re.findall('20\\d{2}[-/]\\d{1,2}[-/]\\d{1,2}', t)
        fd = extract_date(dates[0]) if dates else None
        td = extract_date(dates[1]) if len(dates) > 1 else fd
        pd = extract_date(dates[0]) if dates else None
        leave_type = None
        if mt == 'إجازة':
            for x in active_leave_types():
                if x in t:
                    leave_type = x
                    break
            if not leave_type and has_any('سنوي', 'سنوية'):
                leave_type = 'سنوية'
        dest = None
        if mt == 'انتداب':
            dm = re.search(
                '(?:إلى|الى|لـ|لفرع|إلى فرع|الى فرع)\\s+(?:فرع\\s+)?([^،,؛\\n]+?)(?=\\s+(?:من|بتاريخ)|$)',
                t,
                re.I,
            )
            if dm:
                (dest, _) = find_branch(dm.group(1).strip())
        return {
            'intent': 'register_movement',
            'movement_type': mt,
            'employee_id': emp.id if emp else None,
            'employee_name': name,
            'candidate_ids': [e.id for e in matches[:10]],
            'leave_type': leave_type,
            'destination_branch_id': dest.id if dest else None,
            'destination_name': dest.name if dest else '',
            'from_date': fd,
            'to_date': td,
            'permission_date': pd if mt == 'إذن' else None,
        }
    (mixed_emp, mixed_matches) = employee_from_mixed_phrase(t)
    if mixed_emp or mixed_matches:
        field = detect_employee_field(t)
        if field == 'status':
            return {
                'intent': 'employee_status',
                'employee_id': mixed_emp.id if mixed_emp else None,
                'employee_name': t,
                'candidate_ids': [e.id for e in mixed_matches[:10]],
                'employee_field': field,
            }
        return {
            'intent': 'employee_info',
            'employee_id': mixed_emp.id if mixed_emp else None,
            'employee_name': t,
            'candidate_ids': [e.id for e in mixed_matches[:10]],
            'employee_field': field or 'basic',
        }

    # كلمة الموضوع وحدها أو مع صياغة غير مكتملة تعرض خيارات الموضوع.
    if has_any(*entry_words) and (not has_any('فرع', 'الفرع')):
        return {'intent': 'topic_options', 'topic': 'entry'}
    if has_any(*leave_words) and (not mt):
        return {'intent': 'topic_options', 'topic': 'leave'}
    if has_any(*assign_words) and (not mt):
        return {'intent': 'topic_options', 'topic': 'assignment'}
    if has_any(*perm_words) and (not mt):
        return {'intent': 'topic_options', 'topic': 'permission'}
    # v34.89 — الكلمات المفتاحية تفتح مسار الموضوع بدل اعتبارها طلبًا نهائيًا.
    # مثال: "إجازة" يعرض كل ما يمكن فعله/الاستعلام عنه بخصوص الإجازات،
    # و"مدخل أول" يعرض الإجراءات والاستعلامات الخاصة بالمدخل الأول، وفق الصلاحيات.
    # المطابقة النهائية للموضوع تعتمد على النص الموحّد، لذلك لا تفشل
    # صيغ مثل: اجازه / اجازه / إجازة، أو إذن / اذن.
    topic_norm = normalize_for_search(t).strip()
    if topic_norm in ('اجازه', 'الاجازه', 'اجازات', 'الاجازات', 'عطله', 'عطلات'):
        return {'intent': 'topic_options', 'topic': 'leave'}
    if topic_norm in ('انتداب', 'الانتداب', 'مأموريه', 'المأموريه', 'ماموريه', 'الماموريه'):
        return {'intent': 'topic_options', 'topic': 'assignment'}
    if topic_norm in ('اذن', 'الاذن', 'اذونات', 'الاذونات'):
        return {'intent': 'topic_options', 'topic': 'permission'}
    if low.strip() in ('مدخل اول', 'مدخل أول', 'المدخل الاول', 'المدخل الأول', 'مدخل أولاً', 'المدخل الاول'):
        return {'intent': 'topic_options', 'topic': 'entry'}
    if low.strip() in ('موظف', 'الموظف', 'موظفين', 'الموظفين', 'الموظفون', 'موظفة', 'موظفات'):
        return {'intent': 'topic_options', 'topic': 'employee'}
    if any(
        x in t
        for x in ['سجل حركة', 'سجل له', 'سجل للموظف', 'تسجيل إجازة', 'تسجيل انتداب', 'تسجيل اذن', 'تسجيل إذن', 'اضف إجازة', 'أضف إجازة', 'اضف انتداب', 'أضف انتداب', 'اضف اذن', 'أضف إذن']
    ):
        mt = (
            'إجازة'
            if 'إجازة' in t or 'اجازة' in t
            else 'انتداب' if 'انتداب' in t or 'مأمورية' in t else 'إذن'
        )
        if mt == 'إجازة':
            mt = 'إجازة'
        if mt == 'إذن':
            mt = 'إذن'
        em = re.search(
            '(?:للموظف|لـ|ل )\\s*([^،,؛\\n]+?)(?=\\s+(?:من|بتاريخ|في|إجازة|اجازة|انتداب|إذن|اذن)|$)',
            t,
            re.I,
        )
        name = em.group(1).strip() if em else ''
        (emp, matches) = find_employee(name)
        dates = re.findall('20\\d{2}[-/]\\d{1,2}[-/]\\d{1,2}', t)
        if mt in ('إجازة', 'انتداب'):
            fd = extract_date(dates[0]) if dates else None
            td = extract_date(dates[1]) if len(dates) > 1 else fd
        else:
            pd = extract_date(dates[0]) if dates else None
            fd = td = None
        leave_type = None
        if mt == 'إجازة':
            for x in active_leave_types():
                if x in t:
                    leave_type = x
                    break
            if not leave_type:
                leave_type = 'سنوية' if 'سنوي' in t else None
        dest = None
        if mt == 'انتداب':
            dm = re.search(
                '(?:إلى|الى)\\s+(?:فرع\\s+)?([^،,؛\\n]+?)(?=\\s+(?:من|بتاريخ)|$)',
                t,
                re.I,
            )
            if dm:
                (dest, _) = find_branch(dm.group(1).strip())
        return {
            'intent': 'register_movement',
            'movement_type': mt,
            'employee_id': emp.id if emp else None,
            'employee_name': name,
            'candidate_ids': [e.id for e in matches[:10]],
            'leave_type': leave_type,
            'destination_branch_id': dest.id if dest else None,
            'destination_name': dest.name if dest else '',
            'from_date': fd,
            'to_date': td,
            'permission_date': pd if mt == 'إذن' else None,
        }
    if any((x in t for x in ['سجل حركات', 'تاريخ حركات', 'حركات الموظف', 'حركات موظف'])):
        em = re.search('(?:الموظف|موظف)\\s+([^؟?،,؛\\n]+)', t)
        name = em.group(1).strip() if em else t
        (emp, matches) = find_employee(name)
        return {
            'intent': 'employee_movements',
            'employee_id': emp.id if emp else None,
            'employee_name': name,
            'candidate_ids': [e.id for e in matches[:10]],
        }
    if any((x in t for x in ['حالة موظفي', 'موظفي فرع', 'حالة الفرع', 'حالة موظفين'])):
        bm = re.search('(?:فرع)\\s+([^؟?،,؛\\n]+)', t)
        name = bm.group(1).strip() if bm else ''
        (br, matches) = find_branch(name)
        return {
            'intent': 'branch_status',
            'branch_id': br.id if br else None,
            'branch_name': name,
            'candidate_ids': [b.id for b in matches[:10]],
        }
    if any((x in t for x in ['حالة الموظف', 'ما حالة', 'حاله الموظف', 'حالة'])):
        em = re.search('(?:الموظف|موظف)\\s+([^؟?،,؛\\n]+)', t)
        name = (
            em.group(1).strip()
            if em
            else t.replace('ما حالة', '').replace('حالة الموظف', '').strip(' ؟?')
        )
        (emp, matches) = find_employee(name)
        return {
            'intent': 'employee_status',
            'employee_id': emp.id if emp else None,
            'employee_name': name,
            'candidate_ids': [e.id for e in matches[:10]],
        }

    # الإدخال الحر: لا نفترض أن المستخدم كتب "سؤالاً". أي نص قد يكون اسم موظف،
    # اسم فرع، اسم محافظة، أو موضوعاً مختصراً. نبحث في بيانات النظام أولاً.
    (emp, ematches) = find_employee(t)
    if emp or ematches:
        return {
            'intent': 'employee_info',
            'employee_id': emp.id if emp else None,
            'employee_name': t,
            'candidate_ids': [e.id for e in ematches[:10]],
            'employee_field': detect_employee_field(t) or 'basic',
        }
    (br, bmatches) = find_branch(t)
    if br or bmatches:
        return {
            'intent': 'branch_status',
            'branch_id': br.id if br else None,
            'branch_name': t,
            'candidate_ids': [b.id for b in bmatches[:10]],
        }
    gov_matches = [
        g
        for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if normalize_for_search(t) in normalize_for_search(g.name)
    ]
    if gov_matches:
        if len(gov_matches) == 1:
            return {
                'intent': 'governorate_employees',
                'governorate_id': gov_matches[0].id,
                'governorate_name': gov_matches[0].name,
            }
        return {'intent': 'employee_topic', 'candidate_ids': [g.id for g in gov_matches[:10]]}

    # موضوع مختصر بدون فعل: نعرض ما يمكن عمله في هذا الموضوع، لا رسالة مساعدة عامة.
    if has_any(*leave_words):
        return {'intent': 'topic_options', 'topic': 'leave'}
    if has_any(*assign_words):
        return {'intent': 'topic_options', 'topic': 'assignment'}
    if has_any(*perm_words):
        return {'intent': 'topic_options', 'topic': 'permission'}
    if has_any(*entry_words):
        return {'intent': 'topic_options', 'topic': 'entry'}
    if has_any('موظف', 'موظفين', 'موظفون', 'اسماء', 'أسماء'):
        return {'intent': 'employee_topic'}
    return {'intent': 'help'}
