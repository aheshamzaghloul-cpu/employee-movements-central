"""Small, deterministic helpers for Arabic assistant prompt interpretation."""

import re

from .directory import find_employee
from .text import normalize_digits, normalize_for_search


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
