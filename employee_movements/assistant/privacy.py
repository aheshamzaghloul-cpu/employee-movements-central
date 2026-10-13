"""Privacy boundary for text sent to external language models.

Known local employee/account identifiers are replaced with reversible per-turn
aliases before model requests. The aliases are resolved only in this process,
never by the external provider. Credential-like strings are removed rather than
reversibly aliased and are never sent to a model.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

MAX_ENTITY_SEARCH_TERMS = 80
MAX_ENTITY_CANDIDATES = 500

# Keep this conservative: a word is considered a name component only when it
# appears in a local employee/account name and is not an ordinary instruction.
_COMMON_ARABIC_WORDS = {
    "اعمل", "اعمال", "عايز", "عاوزه", "عاوز", "عايزه", "اريد", "أريد",
    "من", "الى", "إلى", "في", "عن", "على", "له", "لها", "هو", "هي",
    "نفس", "الموظف", "موظف", "الموظفين", "حركه", "حركة", "حركات", "اجازه",
    "إجازة", "اجازة", "انتداب", "اذن", "إذن", "تقرير", "تقارير", "حساب",
    "حسابات", "فرع", "الفرع", "محافظه", "محافظة", "كود", "كودا", "رقم",
    "بيانات", "بياناته", "بياناتها", "حدث", "تعديل", "عدل", "عدّل", "احذف",
    "حذف", "اضف", "أضف", "اضافة", "إضافة", "انشئ", "أنشئ", "افتح", "وريني",
    "اعرض", "اعرضلي", "ابحث", "بحث", "عايز", "عايزين", "محتاج", "محتاجه",
    "please", "show", "find", "search", "employee", "employees", "branch",
    "report", "update", "delete", "create", "add", "edit", "user", "password",
}

_UNDDELIMITED_SECRET_RE = re.compile(
    r"(?i)(?:password|passwd|passcode|كلمة\s+(?:ال)?مرور(?:\s+(?:(?:ال)?مؤقت[ةه]|(?:ال)?جديد[ةه]|(?:ال)?قديم[ةه]))?|كلمة\s+السر|باسورد)"
    r"\s+(?:(?:هو|هي|is|will\s+be|تكون|سيكون)\s+)*"
    r"([A-Za-z0-9][A-Za-z0-9!@#$%^&*._+-]{7,}[^\r\n]*)"
)
_RESET_PASSWORD_TAIL_RE = re.compile(
    r"(?i)((?:"
    r"(?:غيّر|غير|تغيير|أعد(?:\s+(?:تعيين|ضبط))?|اعد(?:\s+(?:تعيين|ضبط))?|"
    r"إعادة(?:\s+(?:تعيين|ضبط))?|اعادة(?:\s+(?:تعيين|ضبط))?)\s+"
    r"(?:كلمة\s+)?(?:المرور|مرور)\b.*?\s+(?:إلى|الى)\s*"
    r"|(?:change|set|reset)(?:\s+the)?\s+password\b.*?\s+(?:to|as)\s*)"
    r")([^\r\n]+)"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)(\b(?:password|passwd|passcode|api[_ -]?key|secret[_ -]?key|access[_ -]?token|token)\b"
    r"|كلمة\s+(?:ال)?مرور(?:\s+(?:(?:ال)?مؤقت[ةه]|(?:ال)?جديد[ةه]|(?:ال)?قديم[ةه]))?|كلمة\s+السر|باسورد)"
    r"\s*(?:(?:هو|هي|is)\s+|[:=]\s*)([^\r\n]+)"
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_GOOGLE_API_KEY_RE = re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}={0,2}")
_LONG_SECRET_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9_-]{32,}(?![A-Za-z0-9])")
_IDENTIFIER_RE = re.compile(r"(?<![\w])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9][A-Za-z0-9_-]{3,}(?![\w])", re.UNICODE)
_DATE_VALUE_RE = re.compile(r"^(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?$")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s()\-]{7,}\d)(?!\w)", re.UNICODE)
_TOKEN_RE = re.compile(r"\[\[LOCAL_PRIVATE_\d{3,5}\]\]")
_WORD_RE = re.compile(r"[\u0600-\u06FF]{3,}|[A-Za-z]{3,}")
_PERSON_LABEL_RE = re.compile(
    r"(?i)(?:اسم\s+(?:الموظف(?:ة)?|المستخدم|الدخول)|الاسم\s+الكامل|اسمه|اسمها|باسم|username|login)\s*(?:(?:هو|هي)\s+|[:=]\s*)?"
    r"([\u0600-\u06FFA-Za-z0-9_][\u0600-\u06FFA-Za-z0-9_'.-]*(?:\s+[\u0600-\u06FFA-Za-z0-9_][\u0600-\u06FFA-Za-z0-9_'.-]*){0,3})"
    r"(?=\s+(?:باسم|من|الى|إلى|في|بفرع|بمحافظة|برقم|كود|تاريخ|وظيفة|هاتف|البريد|رقم|على|دور|المحافظة|الفرع|وعنوان|والبريد|بريد|ورقم|وهاتف|والهاتف|والوظيفة|ودور|اسم الدخول)|[،,؛;\n]|$)"
)


def redact_secrets_for_storage(value: Any) -> str:
    """Remove explicit credentials from chat history before database persistence."""
    text = str(value or "")
    text = _RESET_PASSWORD_TAIL_RE.sub(lambda m: m.group(1) + "[تم إخفاء السر]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}: [تم إخفاء السر]", text)
    text = _UNDDELIMITED_SECRET_RE.sub(lambda m: "[تم إخفاء السر]", text)
    text = _GOOGLE_API_KEY_RE.sub("[تم إخفاء مفتاح API]", text)
    text = _BEARER_RE.sub("Bearer [تم إخفاء الرمز]", text)
    text = _LONG_SECRET_RE.sub("[تم إخفاء قيمة سرية محتملة]", text)
    return text


def restore_local_tokens(value: Any, token_map: dict[str, str]) -> Any:
    """Resolve private aliases after the model reply returns to local code."""
    if isinstance(value, str) and token_map:
        return _TOKEN_RE.sub(lambda match: token_map.get(match.group(0), match.group(0)), value)
    if isinstance(value, list):
        return [restore_local_tokens(item, token_map) for item in value]
    if isinstance(value, tuple):
        return tuple(restore_local_tokens(item, token_map) for item in value)
    if isinstance(value, dict):
        return {key: restore_local_tokens(item, token_map) for key, item in value.items()}
    return value


def sanitize_conversation_for_model(chat: list[dict] | None, current_text: str) -> tuple[list[dict], str, dict[str, str]]:
    """Sanitize prior conversation turns and current text using local records and return reversible aliases.

    Both user and assistant history text are sanitized defensively, even though the
    outbound prompt packers currently forward only user-authored turns. The function
    fails closed if local identity lookup fails while a Flask
    application context is active. That prevents a database error from silently
    forwarding unfiltered text to the external model.
    """
    history_turns = []
    for item in (chat or []):
        if item.get("role") in {"user", "assistant"}:
            history_turns.append(str(item.get("text") or ""))
    raw_texts = history_turns + [str(current_text or "")]
    secret_cleaned = [_remove_credentials(text) for text in raw_texts]
    sensitive_values = set()

    # Structured personal identifiers are always filtered, whether or not they
    # happen to be present in the local database.
    for text in secret_cleaned:
        sensitive_values.update(match.group(0) for match in _EMAIL_RE.finditer(text))
        sensitive_values.update(match.group(0) for match in _GOOGLE_API_KEY_RE.finditer(text))
        sensitive_values.update(match.group(0) for match in _BEARER_RE.finditer(text))
        for match in _PHONE_RE.finditer(text):
            digits = re.sub(r"\D", "", match.group(0))
            # Do not redact short date fragments or small numeric values as phones.
            if len(digits) >= 9 and not _looks_like_date(match.group(0).strip()):
                sensitive_values.add(match.group(0).strip())
        for match in _IDENTIFIER_RE.finditer(text):
            value = match.group(0)
            digits = re.sub(r"\D", "", value)
            # Four-digit years are common context, not employee identifiers.
            if not _looks_like_date(value) and (len(digits) >= 5 or (len(digits) >= 4 and not digits.startswith(("19", "20")))):
                sensitive_values.add(value)

    sensitive_values.update(_explicit_person_values(secret_cleaned))
    sensitive_values.update(_local_sensitive_values(secret_cleaned))

    # Replace longest strings first so a full name/code takes precedence over a
    # single component of that name. Aliases are stable across this whole turn.
    ordered_values = sorted((v for v in sensitive_values if len(v.strip()) >= 2), key=len, reverse=True)
    token_map: dict[str, str] = {}
    value_tokens: dict[str, str] = {}
    for value in ordered_values:
        value = str(value).strip()
        if not value or value in value_tokens:
            continue
        token = f"[[LOCAL_PRIVATE_{len(value_tokens) + 1:03d}]]"
        value_tokens[value] = token
        token_map[token] = value

    def replace_values(text: str) -> str:
        # Longest-first replacement, with word boundaries for identifier-like
        # values and flexible whitespace for full names.
        for value, token in value_tokens.items():
            if not value or token in text:
                continue
            if re.fullmatch(r"[\w@.+-]+", value, flags=re.UNICODE):
                pattern = re.compile(r"(?<![\w])" + re.escape(value) + r"(?![\w])", re.IGNORECASE)
            else:
                pattern = re.compile(re.escape(value).replace(r"\ ", r"\s+"), re.IGNORECASE)
            text = pattern.sub(token, text)
        return text

    sanitized = [replace_values(text) for text in secret_cleaned]
    sanitized_chat = []
    cursor = 0
    for item in (chat or []):
        clone = dict(item)
        if clone.get("role") in {"user", "assistant"}:
            clone["text"] = sanitized[cursor]
            cursor += 1
        sanitized_chat.append(clone)
    sanitized_current = sanitized[-1] if sanitized else ""
    return sanitized_chat, sanitized_current, token_map


def _remove_credentials(text: str) -> str:
    text = _RESET_PASSWORD_TAIL_RE.sub(lambda m: m.group(1) + "[تم حجب بيانات الاعتماد]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}: [تم حجب بيانات الاعتماد]", text)
    text = _UNDDELIMITED_SECRET_RE.sub(lambda m: "[تم حجب بيانات الاعتماد]", text)
    text = _GOOGLE_API_KEY_RE.sub("[تم حجب بيانات الاعتماد]", text)
    text = _BEARER_RE.sub("Bearer [تم حجب بيانات الاعتماد]", text)
    text = _LONG_SECRET_RE.sub("[تم حجب قيمة سرية محتملة]", text)
    return text


def _explicit_person_values(texts: list[str]) -> set[str]:
    """Mask names explicitly labeled in a prompt, including not-yet-created people."""
    values = set()
    for text in texts:
        for match in _PERSON_LABEL_RE.finditer(text):
            candidate = re.sub(r"\s+", " ", match.group(1)).strip(" ,،;؛.")
            words = candidate.split()
            if not candidate or _normalize_arabic(candidate) in _COMMON_ARABIC_WORDS:
                continue
            # Reject captures that are only ordinary labels accidentally following
            # a person marker; proper names can still contain common particles.
            if words and all(_normalize_arabic(word) in _COMMON_ARABIC_WORDS for word in words):
                continue
            values.add(candidate)
    return values


def _local_sensitive_values(texts: list[str]) -> set[str]:
    """Return names and record identifiers which occur in user text, queried locally."""
    try:
        from flask import has_app_context
        if not has_app_context():
            return set()
        from sqlalchemy import func, or_
        from ..extensions import db
        from ..models import Employee, User

        corpus = "\n".join(texts)
        words_by_text = [_WORD_RE.findall(text) for text in texts]
        observed_words = [word for words in words_by_text for word in words]
        search_terms = {
            _normalize_arabic(word)
            for word in observed_words
            if _normalize_arabic(word) not in _COMMON_ARABIC_WORDS
        }
        # Arabic prefixes are frequently attached to names (e.g. «لأحمد»).
        for word in observed_words:
            normalized = _normalize_arabic(word)
            if len(normalized) >= 5 and normalized[0] in "ولفبك" and normalized[1:] not in _COMMON_ARABIC_WORDS:
                search_terms.add(normalized[1:])
            if len(normalized) >= 6 and normalized.startswith("لل"):
                search_terms.add(normalized[2:])

        # Prioritize multi-word name fragments before broad single-word matches.
        # This makes a full name findable even when a common first name matches
        # many rows in a large employee directory.
        name_phrases = set()
        for words in words_by_text:
            informative = []
            for word in words:
                normalized = _normalize_arabic(word)
                if len(normalized) >= 3 and normalized not in _COMMON_ARABIC_WORDS:
                    if len(normalized) >= 5 and normalized[0] in "ولفبك":
                        normalized = normalized[1:]
                    if normalized.startswith("لل") and len(normalized) >= 6:
                        normalized = normalized[2:]
                    informative.append(normalized)
            for size in (4, 3, 2):
                for index in range(max(0, len(informative) - size + 1)):
                    phrase = " ".join(informative[index:index + size])
                    if phrase and len(phrase) >= 7:
                        name_phrases.add(phrase)
        name_phrases = sorted(name_phrases, key=len, reverse=True)[:24]
        search_terms = sorted(search_terms, key=len, reverse=True)[:MAX_ENTITY_SEARCH_TERMS]
        identifier_values = {value for value in _IDENTIFIER_RE.findall(corpus) if not _looks_like_date(value)}

        def folded(column):
            expression = func.lower(column)
            replacements = {
                "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
                "ى": "ي", "ؤ": "و", "ئ": "ي", "ـ": "",
                "َ": "", "ً": "", "ُ": "", "ٌ": "", "ِ": "", "ٍ": "", "ّ": "", "ْ": "", "ٰ": "",
            }
            for source, target in replacements.items():
                expression = func.replace(expression, source, target)
            return expression

        employee_fields = (
            Employee.full_name, Employee.employee_code, Employee.job_code, Employee.email,
            Employee.company_phone, Employee.personal_phone,
        )
        user_fields = (User.full_name, User.username, User.email, User.job_code)
        employee_names = folded(Employee.full_name)
        user_names = folded(User.full_name)
        employee_exact = [employee_names.ilike(f"%{phrase}%", escape="\\") for phrase in name_phrases]
        user_exact = [user_names.ilike(f"%{phrase}%", escape="\\") for phrase in name_phrases]
        identifier_predicates = []
        if identifier_values:
            identifiers = list(identifier_values)[:100]
            identifier_predicates.extend([
                Employee.employee_code.in_(identifiers), Employee.job_code.in_(identifiers),
                User.username.in_(identifiers), User.job_code.in_(identifiers),
            ])
        employee_broad = [employee_names.ilike(f"%{term}%", escape="\\") for term in search_terms]
        employee_broad.extend(identifier_predicates[:2])
        user_broad = [user_names.ilike(f"%{term}%", escape="\\") for term in search_terms]
        user_broad.extend(identifier_predicates[2:])

        def query_rows(fields, predicates, limit):
            if not predicates:
                return []
            return db.session.query(*fields).filter(or_(*predicates)).limit(limit).all()

        # Exact/multi-word matches come first; broad matches supplement first-name
        # references and short account/employee identifiers.
        employee_rows = query_rows(employee_fields, employee_exact, MAX_ENTITY_CANDIDATES)
        employee_rows += query_rows(employee_fields, employee_broad, MAX_ENTITY_CANDIDATES)
        user_rows = query_rows(user_fields, user_exact, 200)
        user_rows += query_rows(user_fields, user_broad, 200)
    except Exception as exc:
        # Never log raw prompts or candidate values in this path.
        raise RuntimeError("Local privacy screening could not complete; external processing blocked.") from exc

    values: set[str] = set()
    observed_norm = {}
    for word in observed_words:
        observed_norm.setdefault(_normalize_arabic(word), set()).add(word)

    def collect_rows(rows):
        for row in rows:
            name = str(row[0] or "").strip()
            if name:
                if _contains_value(corpus, name):
                    values.add(name)
                for part in name.split():
                    normalized_part = _normalize_arabic(part)
                    if normalized_part not in _COMMON_ARABIC_WORDS and len(normalized_part) >= 3:
                        # Preserve the user's original spelling in the per-turn map,
                        # while ensuring common Arabic orthographic variants are masked.
                        values.update(observed_norm.get(normalized_part, set()))
            for value in row[1:]:
                candidate = str(value or "").strip()
                if candidate and _contains_value(corpus, candidate):
                    values.add(candidate)

    collect_rows(employee_rows)
    collect_rows(user_rows)
    return values


def _looks_like_date(value: str) -> bool:
    """Avoid hiding explicit dates; the language model needs to map them to date fields."""
    return _DATE_VALUE_RE.fullmatch(str(value or "").strip()) is not None


def _normalize_arabic(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).replace("ـ", "")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"})).lower()


def _contains_value(text: str, value: str) -> bool:
    if not value:
        return False
    if re.fullmatch(r"[\w@.+-]+", value, flags=re.UNICODE):
        return re.search(r"(?<![\w])" + re.escape(value) + r"(?![\w])", text, re.IGNORECASE) is not None
    return re.search(re.escape(value), text, re.IGNORECASE) is not None
