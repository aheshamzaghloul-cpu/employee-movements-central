"""Application-agent layer for the in-app assistant.

Gemini is used as the conversational planner/tool selector.  The application remains
source of truth for records, scopes, permissions, validation and all mutations.
"""
from __future__ import annotations

import json
import logging
import urllib.error

from flask import current_app, request, session

from ..access import roles
from .pending import store_pending_plan
from .llm import DEFAULT_MODEL
from .conversation_context import (
    MAX_CONVERSATION_CHARS as _MAX_CONVERSATION_CHARS,
    MAX_CONVERSATION_TURNS as _MAX_CONVERSATION_TURNS,
    build_agent_contents,
)
from .gemini_client import GEMINI_URL as _GEMINI_URL, generate_content as _generate_content
from .privacy import restore_local_tokens, sanitize_conversation_for_model
from .tool_schemas import ACTION_NAMES as ACTION_NAMES, tool_schemas
from .tool_responses import render_tool_result_response
from .tool_helpers import _employee_summary as _employee_summary, _safe_int as _safe_int
from .action_preparation import prepare_action as _prepare_action_impl
from .tool_dispatch import dispatch_tool as _dispatch_tool

# Legacy module-level constants remain available to existing imports.
MAX_CONVERSATION_CHARS = _MAX_CONVERSATION_CHARS
MAX_CONVERSATION_TURNS = _MAX_CONVERSATION_TURNS
GEMINI_INTERACTION_URL = _GEMINI_URL

logger = logging.getLogger(__name__)

MAX_AGENT_ROUNDS = 2

PAGE_NAMES = {
    "/": "الرئيسية",
    "/employees": "الموظفون",
    "/movements": "حركات الموظفين",
    "/reports": "التقارير",
    "/reports-missions": "تقارير ومأموريات",
    "/delegations": "التفويض",
    "/structure": "الإدارة",
    "/users": "المستخدمون والحسابات",
    "/branches": "الفروع",
    "/governorates": "المحافظات",
    "/lookups": "القوائم الأساسية",
    "/audit": "سجل التدقيق",
}


SYSTEM = """
أنت «بسيوني»، المساعد الذكي والشخصية الرسمية داخل «نظام إدارة حركات الموظفين». تعامل مع المستخدم كمحادثة مستمرة،
وافهم العامية المصرية والفصحى والضمائر والعبارات المختصرة مثل «هو»، «نفسه»، «عدّلها»،
«خلّيها»، «تمام»، «نفّذ»، «اللي قدامك»، و«من هنا».

أنت لست مقيدًا بصفحة معينة: يمكنك الانتقال والتعامل مع أي جزء من النظام من نفس المحادثة. لا تضع قيودًا اصطناعية على أنواع الأسئلة أو الصفحات؛ استخدم كل الأدوات المتاحة لك عندما تكون مفيدة. صلاحياتك التنفيذية هي نفس صلاحيات المستخدم الحالي، والتطبيق هو صاحب القرار النهائي في الصلاحيات والنطاق والتحقق. إذا كان المستخدم مسؤول التطبيق، تعامل معه كمستخدم إداري كامل ولا تطلب منه العودة إلى صفحة الإدارة لمجرد تنفيذ إجراء متاح له.
افهم المحادثة كوحدة واحدة: اربط الطلب الحالي بما سبق، واحتفظ بالأسماء والحقول التي ذكرها المستخدم بالفعل، واستنتج مرجع الضمير من آخر سجل أو طلب واضح. إذا كانت هناك معلومة واحدة ناقصة فقط فاسأل عنها مباشرة بدل إعادة الطلب من البداية. لا تعتبر «تمام» موافقة على عملية جديدة إلا إذا كان هناك إجراء معلّق واضح.
استخدم أدوات التطبيق بدل التخمين. لا تخترع اسم موظف أو فرع أو محافظة أو نتيجة.
إذا احتجت بيانات حقيقية فاستدع الأداة المناسبة أولًا.
قد تظهر رموز مثل [[LOCAL_PRIVATE_001]] بدل أسماء أو أكواد أو بيانات شخصية. احتفظ بكل رمز كما هو عند تمريره إلى أدوات التطبيق، ولا تحاول كشف قيمته أو تخمينها.

هناك نوعان من الأدوات:
1) أدوات قراءة: ابحث عن موظف/فرع/محافظة، اعرض ملف الموظف، الحركات، وحالة الحركة.
2) أداة prepare_action: تجهز عملية كتابة أو تعديل ولا تنفذها. التطبيق يعيد معاينة ويخزن عملية معلقة.
لا تطلب من المستخدم العودة إلى صفحة أخرى لمجرد تنفيذ عملية يمكن للتطبيق تجهيزها هنا.

عند نقص معلومة ضرورية، اسأل عنها فقط. لا تسأل عن معلومة موجودة في سياق الصفحة أو المحادثة.
إذا كان هناك موظف أو حركة أو سجل محدد في الصفحة الحالية، اعتبره المقصود افتراضيًا عند قول المستخدم «هو/هي/ها/عدله/عدّلها» ما لم يحدد غيره.

بعد إتمام أدوات القراءة، أجب باختصار واضح وعملي. في الأسئلة اليومية استخدم المصرية الخفيفة، وفي البيانات الرسمية استخدم العربية الفصحى.
""".strip()


def _workspace_context(raw: str | None = None) -> dict:
    """Validate and normalize client-supplied workspace metadata."""
    data = {}
    if raw:
        try:
            candidate = json.loads(raw)
            if isinstance(candidate, dict):
                data = candidate
        except (TypeError, ValueError, json.JSONDecodeError):
            data = {}
    path = str(data.get("path") or request.path or "/")[:180]
    heading = str(data.get("heading") or "")[:160]
    title = str(data.get("title") or PAGE_NAMES.get(path, "التطبيق"))[:160]
    selected = {}
    for key in ("employee_id", "movement_id", "branch_id", "governorate_id", "delegation_id", "user_id"):
        val = data.get(key)
        try:
            if val not in (None, ""):
                selected[key] = int(val)
        except (TypeError, ValueError):
            pass
    # Never derive the external model's page label from client-authored title text.
    page = PAGE_NAMES.get(path, "التطبيق")
    for base, label in PAGE_NAMES.items():
        if base != "/" and path.startswith(base + "/"):
            page = label
            break
    return {
        "path": path,
        "page": page,
        "title": title,
        "heading": heading,
        "hash": str(data.get("hash") or "")[:120],
        "selected": selected,
        "scope_governorate_id": _safe_int(data.get("scope_governorate_id")),
    }






def _tool_context_text(ctx):
    """Return a safe context summary; never include dynamic paths, titles or record IDs."""
    page = ctx.get("page") if ctx.get("page") in PAGE_NAMES.values() else "التطبيق"
    return json.dumps({
        "current_page": page,
        "selected": {
            key: True for key, value in (ctx.get("selected", {}) or {}).items() if value is not None
        },
        "has_selected_governorate": bool(ctx.get("scope_governorate_id")),
        "active_role": session.get("active_role"),
        "roles": roles(),
    }, ensure_ascii=False)




def tool_execute(name, args, ctx):
    """Backward-compatible alias for the separated local tool dispatcher."""
    return _dispatch_tool(name, args, ctx)


def _prepare_action(args, ctx):
    """Backward-compatible alias for confirmation-only action preparation."""
    return _prepare_action_impl(args, ctx)


def _extract_function_calls(response):
    calls = []
    for cand in response.get("candidates", []) or []:
        content = cand.get("content") or {}
        for part in content.get("parts", []) or []:
            fc = part.get("functionCall") or part.get("function_call")
            if fc:
                calls.append({"id": fc.get("id") or "", "name": fc.get("name"), "args": fc.get("args") or {}})
    return calls


def _extract_text(response):
    chunks = []
    for cand in response.get("candidates", []) or []:
        for part in (cand.get("content") or {}).get("parts", []) or []:
            text = part.get("text")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def _call_gemini(contents, context):
    api_key = current_app.config.get("GEMINI_API_KEY", "")
    if not api_key:
        return None
    model = (current_app.config.get("GEMINI_MODEL") or DEFAULT_MODEL).removeprefix("models/")
    role_text = ", ".join(roles())
    # Only page-level metadata is sent to the external model. Selected record IDs
    # are replaced with presence flags; the actual IDs remain local for tool use.
    # External context is an allowlist: static page label and presence flags only.
    # Dynamic URL paths, headings, titles and hashes may contain employee names or IDs.
    safe_page = context.get("page") if context.get("page") in PAGE_NAMES.values() else "التطبيق"
    model_context = {
        "page": safe_page,
        "selected": {
            key: True for key, value in (context.get("selected", {}) or {}).items()
            if value is not None
        },
        "has_selected_governorate": bool(context.get("scope_governorate_id")),
    }
    system = SYSTEM + f"\n\nسياق مساحة العمل الحالي (بيانات وصفية فقط، دون معرّفات سجلات): {json.dumps(model_context, ensure_ascii=False)}\nالدور النشط: {session.get('active_role') or role_text}. اسم المساعد: بسيوني في الخدمة. الصفحة الحالية سياق مساعد وليست قيدًا على قدراتك."
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "tools": [{"functionDeclarations": tool_schemas()}],
        "generationConfig": {"maxOutputTokens": 700, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    try:
        return _generate_content(
            model=model,
            payload=payload,
            api_key=api_key,
            timeout=int(current_app.config.get("ASSISTANT_TIMEOUT_SECONDS", 25)),
            ensure_ascii=True,
        )
    except urllib.error.HTTPError as exc:
        # Provider error bodies can echo submitted prompt fragments; never log them.
        logger.warning("Gemini agent request failed with HTTP status %s", exc.code)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        # Avoid logging request/response payloads; only the exception class is needed.
        logger.warning("Gemini agent request failed (%s)", type(exc).__name__)
        return None


def _tool_result_response(name, result, args, context):
    """Backward-compatible alias for local tool-result formatting."""
    return render_tool_result_response(name, result, args, context)


def run_agent(prompt, prior_chat, workspace_context):
    """Run one conversational turn with local application tools and confirmation-ready mutations."""
    if not current_app.config.get("GEMINI_API_KEY", ""):
        return None
    context = _workspace_context(workspace_context)
    # Replace locally-known personal identifiers in prior context and the current prompt.
    # Only sanitized user-authored turns are actually packed for external transfer.
    prior_chat, prompt, local_token_map = sanitize_conversation_for_model(prior_chat, prompt)
    contents = build_agent_contents(prior_chat, prompt)

    response = _call_gemini(contents, context)
    if not response:
        return None
    calls = _extract_function_calls(response)
    if not calls:
        text = restore_local_tokens(_extract_text(response), local_token_map)
        return {"title": "المساعد الذكي", "answer": text or "لم أستطع استخراج رد واضح من النموذج."}

    # لا نسمح للنموذج بإعداد أكثر من عملية كتابة في الاستدعاء نفسه؛ وإلا قد
    # تتنافس خطتان على خانة التأكيد الواحدة في الجلسة.
    action_calls = [call for call in calls if call.get("name") == "prepare_action"]
    if len(action_calls) > 1:
        return {
            "title": "تأكيد العملية",
            "error": "قسّم الطلب إلى عملية واحدة في كل مرة حتى أراجع صلاحياتها ونتيجتها قبل الانتقال لغيرها.",
        }

    tool_results = []
    for call in calls:
        local_args = restore_local_tokens(call.get("args") or {}, local_token_map)
        try:
            result = tool_execute(call["name"], local_args, context)
        except Exception as exc:
            # Exception text from SQLAlchemy may contain row values or SQL params.
            # Keep diagnostics categorical and do not send exception contents downstream.
            logger.error("Assistant tool %s failed (%s)", call.get("name"), type(exc).__name__)
            result = {"ok": False, "error": "تعذر تنفيذ الأداة محليًا."}

        if result.get("needs_confirmation") and result.get("plan"):
            if result.get("plan_kind") == "manager":
                store_pending_plan("assistant_manager_pending", result["plan"])
            else:
                store_pending_plan("assistant_pending", result["plan"])
        if result.get("navigate"):
            context["navigate"] = result["navigate"]
        tool_results.append((call.get("name") or "", result, local_args))

    # Privacy boundary: do not append function responses to `contents` and do not
    # make a second Gemini request. Search/profile/movement results and action
    # previews can contain employee identifiers or operational records. They are
    # formatted into the user-visible reply locally after permissions are checked.
    local_responses = [
        _tool_result_response(name, result, args, context)
        for name, result, args in tool_results
    ]
    planned = next((item for item in local_responses if item.get("preview")), None)
    if planned:
        return planned
    navigation = next((item for item in local_responses if item.get("navigate_url")), None)
    if navigation:
        return navigation
    useful = [item for item in local_responses if item.get("answer") or item.get("error")]
    if len(useful) == 1:
        return useful[0]
    if useful:
        errors = [item.get("error") for item in useful if item.get("error")]
        answers = [item.get("answer") for item in useful if item.get("answer")]
        return {
            "title": "نتيجة المساعد",
            "error": "\n".join(errors) if errors else None,
            "answer": "\n\n".join(answers) if answers else None,
        }
    return {"title": "المساعد الذكي", "answer": "تمت مراجعة الطلب محليًا، دون إرسال نتائج السجلات إلى النموذج الخارجي."}
