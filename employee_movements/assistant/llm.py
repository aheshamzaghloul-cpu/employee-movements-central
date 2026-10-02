"""Optional Gemini semantic intent extraction.

Gemini is used only as a language/intent parser.  The application database remains
 the source of truth: employee/branch/governorate names and IDs are resolved locally,
 permissions are checked locally, and Gemini never receives a catalog of live records.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app

from ..access import me, roles

logger = logging.getLogger(__name__)

GEMINI_URL = 'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
DEFAULT_MODEL = 'gemini-3.6-flash'
REQUEST_TIMEOUT_SECONDS = 20
MAX_HISTORY_MESSAGES = 8
MAX_HISTORY_TEXT_CHARS = 800


INTENT_SCHEMA = {
    'type': 'object',
    'additionalProperties': False,
    'properties': {
        'intent': {
            'type': 'string',
            'enum': [
                'employee_add', 'employee_create', 'employee_status', 'employee_info', 'employee_movements',
                'governorate_create', 'governorate_edit', 'governorate_toggle',
                'branch_create', 'branch_edit', 'branch_toggle',
                'employee_edit', 'employee_delete', 'employee_restore', 'user_create', 'user_edit', 'user_toggle', 'user_delete', 'user_password_reset', 'user_set_governorates', 'user_set_branches', 'role_grant', 'role_revoke', 'entry_assign', 'entry_remove', 'entry_replace', 'delegation_create', 'delegation_revoke', 'lookup_create', 'lookup_edit', 'lookup_toggle', 'lookup_delete', 'movement_edit', 'movement_delete', 'movement_close',
                'branch_status', 'branch_info', 'branch_entry', 'governorate_employees',
                'governorate_assignments_today', 'movement_people_today', 'employee_topic',
                'register_movement', 'topic_options', 'navigate', 'help',
            ],
        },
        'topic': {
            'type': ['string', 'null'],
            'enum': [
                'leave', 'assignment', 'permission', 'entry', 'employee', 'branch',
                'reports', 'admin', 'users', 'delegation', 'replacement', 'audit', None,
            ],
        },
        'employee_name': {'type': ['string', 'null']},
        'full_name': {'type': ['string', 'null']},
        'employee_code': {'type': ['string', 'null']},
        'hire_date': {'type': ['string', 'null']},
        'company_phone': {'type': ['string', 'null']},
        'personal_phone': {'type': ['string', 'null']},
        'username': {'type': ['string', 'null']},
        'email': {'type': ['string', 'null']},
        'job_title': {'type': ['string', 'null']},
        'job_code': {'type': ['string', 'null']},
        'password': {'type': ['string', 'null']},
        'roles': {'type': 'array', 'items': {'type': 'string'}},
        'governorate_ids': {'type': 'array', 'items': {'type': 'integer'}},
        'governorate_names': {'type': 'array', 'items': {'type': 'string'}},
        'branch_names': {'type': 'array', 'items': {'type': 'string'}},
        'supervisor_name': {'type': ['string', 'null']},
        'delegate_name': {'type': ['string', 'null']},
        'starts_at': {'type': ['string', 'null']},
        'ends_at': {'type': ['string', 'null']},
        'new_name': {'type': ['string', 'null']},
        'branch_code': {'type': ['string', 'null']},
        'role': {'type': ['string', 'null']},
        'employee_id': {'type': ['integer', 'null']},
        'branch_name': {'type': ['string', 'null']},
        'branch_id': {'type': ['integer', 'null']},
        'governorate_id': {'type': ['integer', 'null']},
        'user_id': {'type': ['integer', 'null']},
        'supervisor_id': {'type': ['integer', 'null']},
        'delegate_id': {'type': ['integer', 'null']},
        'delegation_id': {'type': ['integer', 'null']},
        'reason': {'type': ['string', 'null']},
        'new_employee_id': {'type': ['integer', 'null']},
        'new_employee_name': {'type': ['string', 'null']},
        'governorate_name': {'type': ['string', 'null']},
        'lookup_id': {'type': ['integer', 'null']},
        'lookup_name': {'type': ['string', 'null']},
        'lookup_kind': {'type': ['string', 'null'], 'enum': ['movement', 'leave', None]},
        'movement_id': {'type': ['integer', 'null']},
        'close_date': {'type': ['string', 'null']},
        'candidate_ids': {'type': 'array', 'items': {'type': 'integer'}},
        'movement_type': {'type': ['string', 'null'], 'enum': ['إجازة', 'انتداب', 'إذن', None]},
        'leave_type': {'type': ['string', 'null']},
        'destination_name': {'type': ['string', 'null']},
        'from_date': {'type': ['string', 'null']},
        'to_date': {'type': ['string', 'null']},
        'permission_date': {'type': ['string', 'null']},
        'open_assignment': {'type': 'boolean'},
        'navigate_url': {'type': ['string', 'null']},
        'reply': {'type': ['string', 'null']},
        'employee_field': {
            'type': ['string', 'null'],
            'enum': [
                'status', 'job_title', 'job_code', 'employee_code', 'branch', 'governorate',
                'hire_date', 'company_phone', 'personal_phone', 'phone', 'last_leave',
                'last_assignment', 'last_permission', 'movements', 'basic', None,
            ],
        },
    },
    'required': [
        'intent', 'topic', 'employee_name', 'employee_id', 'branch_name', 'branch_id',
        'governorate_id', 'governorate_name', 'candidate_ids', 'movement_type', 'leave_type',
        'destination_name', 'from_date', 'to_date', 'permission_date', 'open_assignment',
        'navigate_url', 'reply', 'employee_field', 'new_name', 'full_name', 'employee_code', 'hire_date', 'company_phone', 'personal_phone', 'user_id', 'supervisor_id', 'delegate_id', 'delegation_id', 'reason', 'new_employee_id', 'new_employee_name', 'branch_code', 'role', 'username', 'email', 'job_title', 'job_code', 'password', 'roles', 'supervisor_name', 'delegate_name', 'starts_at', 'ends_at', 'new_employee_name', 'lookup_id', 'lookup_name', 'lookup_kind', 'movement_id', 'close_date',
    ],
}


SYSTEM_INSTRUCTION = """
أنت محلل لغوي فقط لمساعد إداري عربي داخل نظام إدارة حركات الموظفين.
مهمتك استخراج نية المستخدم والحقول التي ذكرها في كلامه، ولا تنفذ أي إجراء ولا
تخمن بيانات قاعدة البيانات.

قواعد مهمة:
- لا تملك قاعدة البيانات ولا كتالوج الموظفين أو الفروع أو المحافظات.
- لا تخترع أي اسم أو رقم أو معرف أو تاريخ غير موجود في رسالة المستخدم أو سياق المحادثة المرسل لك.
- employee_id و branch_id و governorate_id و candidate_ids يجب أن تبقى فارغة ما لم يذكر المستخدم الرقم صراحة؛ التطبيق هو الذي يحل الأسماء إلى سجلات حقيقية.
- إذا ذكر المستخدم اسم موظف أو فرع أو محافظة، أعد الاسم النصي في الحقل المناسب فقط. عند ذكر عدة فروع أو محافظات بالاسم، استخدم branch_names أو governorate_names.
- يمكن أن يطلب المستخدم عمليات إدارية: إضافة/تعديل/تعطيل محافظة أو فرع، تعديل/إخفاء/استعادة موظف، ومنح/إزالة دور. استخرج العملية والحقول المذكورة فقط.
- لا تستخرج كلمات مرور أو أسرار API؛ إذا طلب المستخدم إنشاء حساب بكلمة مرور فدع التطبيق يفتح شاشة الحساب.
- لا تضع URL من عندك. استخدم navigate_url فقط إذا أعطاك التطبيق رابطًا في السياق، وإلا اتركه فارغًا.
- افهم العربية الفصحى والعامية المصرية والأخطاء الإملائية والصياغات المختصرة.
- إذا كان المستخدم يطلب تسجيل حركة، استخرج نوع الحركة والتواريخ واسم الموظف والوجهة إن ذكرها.
- إذا كانت المعلومة ناقصة، لا تخترعها؛ اترك الحقل فارغًا ودع التطبيق يطلبها.
- reply اختياري ومختصر، وهو ليس مصدرًا للبيانات ولا لتنفيذ الصلاحيات.
- لا تتخذ قرار صلاحية أو وصول؛ التطبيق سيتحقق من ذلك محليًا.
""".strip()


def _history_for_language(chat):
    """Keep only recent user utterances; never send DB-generated assistant cards back to Gemini."""
    history = []
    for item in (chat or [])[-MAX_HISTORY_MESSAGES:]:
        if item.get('role') != 'user' or not item.get('text'):
            continue
        history.append({
            'role': 'user',
            'parts': [{'text': str(item['text'])[:MAX_HISTORY_TEXT_CHARS]}],
        })
    return history


def build_live_context(text, local_a=None):
    """Compatibility shim kept for callers from older versions.

    Deliberately returns no database snapshot.  Live entities must never be sent to the
    external language model; local code resolves them after intent extraction.
    """
    return ''


def llm_parse(text, chat=None, live_context=''):
    """Extract semantic intent with Gemini; never send live DB catalogs to the model."""
    api_key = current_app.config.get('GEMINI_API_KEY', '')
    if not api_key:
        return None

    model = current_app.config.get('GEMINI_MODEL') or DEFAULT_MODEL
    model = model.removeprefix('models/')
    role_text = '، '.join(sorted(roles(me()))) if me() else ''

    # Only role + the user's own language are sent.  ``live_context`` is intentionally ignored.
    language_context = (
        f'الدور النشط في التطبيق: {role_text}.\n'
        'هذا الدور معلومة سياقية لغوية فقط؛ لا تستخدمه لاتخاذ قرار صلاحية.\n'
        'لا توجد أي بيانات موظفين أو فروع أو محافظات متاحة للنموذج.\n'
    )
    contents = _history_for_language(chat)
    contents.append({'role': 'user', 'parts': [{'text': str(text)[:4000]}]})

    payload = {
        'system_instruction': {'parts': [{'text': SYSTEM_INSTRUCTION + '\n\n' + language_context}]},
        'contents': contents,
        'generationConfig': {
            'responseMimeType': 'application/json',
            'responseSchema': INTENT_SCHEMA,
            'temperature': 0.1,
            'maxOutputTokens': 700,
        },
    }
    endpoint = GEMINI_URL.format(model=urllib.parse.quote(model, safe=''))
    request_obj = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'x-goog-api-key': api_key,
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request_obj, timeout=int(current_app.config.get('GEMINI_TIMEOUT', REQUEST_TIMEOUT_SECONDS))) as response:
            data = json.loads(response.read().decode('utf-8'))
        candidates = data.get('candidates') or []
        if not candidates:
            return None
        parts = (candidates[0].get('content') or {}).get('parts') or []
        raw = ''.join(p.get('text', '') for p in parts if isinstance(p, dict)).strip()
        if not raw:
            return None
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        # IDs are authoritative only when the local app resolves them.  Ignore model-supplied IDs.
        parsed['employee_id'] = None
        parsed['branch_id'] = None
        parsed['governorate_id'] = None
        parsed['user_id'] = None
        parsed['supervisor_id'] = None
        parsed['delegate_id'] = None
        parsed['new_employee_id'] = None
        parsed['password'] = None
        parsed['candidate_ids'] = []
        return parsed
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        logger.warning('Gemini intent request failed: %s', exc)
        return None
