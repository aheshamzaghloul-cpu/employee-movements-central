"""Arabic text normalization and date extraction (pure functions)."""

import re


def normalize_for_search(text):
    """تطبيع النص العربي للبحث والفهم فقط دون تغيير القيمة الأصلية المخزنة."""
    import unicodedata
    text = unicodedata.normalize('NFKC', str(text or ''))
    # إزالة التشكيل والتطويل وعلامات الوقف الزائدة.
    text = re.sub('[\\u064B-\\u065F\\u0670\\u0640]', '', text)
    # توحيد صور الهمزة والألف، والألف المقصورة/الياء، والتاء المربوطة/الهاء
    # حتى تنجح المطابقة المرنة مثل: إجازة/اجازه، منى/مني، هدى/هدي.
    text = text.translate(
        str.maketrans(
            {'أ': 'ا', 'إ': 'ا', 'آ': 'ا', 'ٱ': 'ا', 'ى': 'ي', 'ئ': 'ي', 'ؤ': 'و', 'ة': 'ه'},
        ),
    )
    text = re.sub('[\\s\\u200f\\u200e]+', ' ', text).strip().lower()
    return text


def normalize_digits(text):
    """تطبيع عام للنص، مع الاحتفاظ بالقيمة الأصلية لعرضها كما هي."""
    trans = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹', '01234567890123456789')
    return (text or '').translate(trans).strip()


def extract_date(text):
    m = re.search('(20\\d{2})[-/](\\d{1,2})[-/](\\d{1,2})', text or '')
    if not m:
        return None
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
