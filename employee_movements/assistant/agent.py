"""Application-agent layer for the in-app assistant.

Gemini is used as the conversational planner/tool selector.  The application remains
source of truth for records, scopes, permissions, validation and all mutations.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app, request, session

from ..access import actual_roles, branch_ok, can, effective_user_gov_ids, me, roles, user_gov_ids
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement
from .directory import find_branch, find_employee
from .llm import DEFAULT_MODEL

logger = logging.getLogger(__name__)

GEMINI_INTERACTION_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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

ACTION_NAMES = [
    "register_movement",
    "employee_create", "employee_edit", "employee_delete", "employee_restore",
    "governorate_create", "governorate_edit", "governorate_toggle",
    "branch_create", "branch_edit", "branch_toggle",
    "user_create", "user_edit", "user_toggle", "user_delete", "user_password_reset",
    "user_set_governorates", "user_set_branches", "role_grant", "role_revoke",
    "entry_assign", "entry_remove", "entry_replace",
    "delegation_create", "delegation_revoke",
    "lookup_create", "lookup_edit", "lookup_toggle", "lookup_delete",
    "movement_edit", "movement_delete", "movement_close", "movement_reopen",
]

SYSTEM = """
أنت «بسيوني»، المساعد الذكي والشخصية الرسمية داخل «نظام إدارة حركات الموظفين». تعامل مع المستخدم كمحادثة مستمرة،
وافهم العامية المصرية والفصحى والضمائر والعبارات المختصرة مثل «هو»، «نفسه»، «عدّلها»،
«خلّيها»، «تمام»، «نفّذ»، «اللي قدامك»، و«من هنا».

أنت لست مقيدًا بصفحة معينة: يمكنك الانتقال والتعامل مع أي جزء من النظام من نفس المحادثة. صلاحياتك التنفيذية هي نفس صلاحيات المستخدم الحالي، والتطبيق هو صاحب القرار النهائي في الصلاحيات والنطاق والتحقق. إذا كان المستخدم مسؤول التطبيق، تعامل معه كمستخدم إداري كامل ولا تطلب منه العودة إلى صفحة الإدارة لمجرد تنفيذ إجراء متاح له.
استخدم أدوات التطبيق بدل التخمين. لا تخترع اسم موظف أو فرع أو محافظة أو نتيجة.
إذا احتجت بيانات حقيقية فاستدع الأداة المناسبة أولًا.

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
    page = PAGE_NAMES.get(path, title)
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


def _safe_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def tool_schemas():
    """Function declarations exposed to Gemini."""
    common_limit = {
        "type": "integer", "minimum": 1, "maximum": 10,
    }
    return [
        {
            "name": "get_workspace_context",
            "description": "يقرأ سياق مساحة العمل الحالية: الصفحة والسجل المحدد ونطاق المحافظة.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "search_employees",
            "description": "ابحث محليًا عن موظفين بالاسم أو كود شؤون العاملين أو الهاتف.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "limit": common_limit,
            }, "required": ["query"]},
        },
        {
            "name": "get_employee_profile",
            "description": "يعرض بيانات موظف محدد وحالته وآخر حركاته.",
            "parameters": {"type": "object", "properties": {
                "employee_id": {"type": "integer"},
            }, "required": ["employee_id"]},
        },
        {
            "name": "search_branches",
            "description": "ابحث محليًا عن الفروع.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "governorate_id": {"type": "integer"},
                "limit": common_limit,
            }, "required": ["query"]},
        },
        {
            "name": "search_governorates",
            "description": "ابحث محليًا عن المحافظات.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"},
                "limit": common_limit,
            }, "required": ["query"]},
        },
        {
            "name": "search_movements",
            "description": "يعرض الحركات المطابقة لموظف أو نوع حركة أو محافظة أو فرع أو تاريخ.",
            "parameters": {"type": "object", "properties": {
                "employee_id": {"type": "integer"},
                "movement_type": {"type": "string", "enum": ["إجازة", "انتداب", "إذن"]},
                "governorate_id": {"type": "integer"},
                "branch_id": {"type": "integer"},
                "date": {"type": "string"},
                "limit": common_limit,
            }},
        },
        {
            "name": "prepare_action",
            "description": "يجهز عملية كتابة/تعديل داخل النظام. لا ينفذها؛ يعيد معاينة أو يطلب معلومة ناقصة.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ACTION_NAMES},
                    "employee_id": {"type": "integer"},
                    "employee_name": {"type": "string"},
                    "full_name": {"type": "string"},
                    "employee_code": {"type": "string"},
                    "branch_id": {"type": "integer"},
                    "branch_name": {"type": "string"},
                    "branch_code": {"type": "string"},
                    "governorate_id": {"type": "integer"},
                    "governorate_name": {"type": "string"},
                    "new_name": {"type": "string"},
                    "movement_id": {"type": "integer"},
                    "movement_type": {"type": "string", "enum": ["إجازة", "انتداب", "إذن"]},
                    "leave_type": {"type": "string"},
                    "destination_name": {"type": "string"},
                    "from_date": {"type": "string"},
                    "to_date": {"type": "string"},
                    "permission_date": {"type": "string"},
                    "open_assignment": {"type": "boolean"},
                    "username": {"type": "string"},
                    "email": {"type": "string"},
                    "job_title": {"type": "string"},
                    "job_code": {"type": "string"},
                    "roles": {"type": "array", "items": {"type": "string"}},
                    "role": {"type": "string"},
                    "password": {"type": "string"},
                    "supervisor_name": {"type": "string"},
                    "delegate_name": {"type": "string"},
                    "starts_at": {"type": "string"},
                    "ends_at": {"type": "string"},
                    "new_employee_id": {"type": "integer"},
                    "new_employee_name": {"type": "string"},
                    "lookup_name": {"type": "string"},
                    "lookup_kind": {"type": "string", "enum": ["movement", "leave"]},
                    "reason": {"type": "string"},
                    "user_id": {"type": "integer"},
                    "delegation_id": {"type": "integer"},
                },
                "required": ["action"],
            },
        },
        {
            "name": "navigate_to",
            "description": "يفتح صفحة أو مركز عمل داخل التطبيق عندما يطلب المستخدم ذلك صراحة.",
            "parameters": {"type": "object", "properties": {
                "target": {"type": "string", "enum": [
                    "home", "employees", "employee", "movements", "reports", "missions",
                    "delegations", "administration", "users", "branches", "governorates", "lookups", "audit"
                ]},
            }, "required": ["target"]},
        },
    ]


def _tool_context_text(ctx):
    return json.dumps({
        "current_page": ctx.get("page"),
        "path": ctx.get("path"),
        "heading": ctx.get("heading"),
        "hash": ctx.get("hash"),
        "selected": ctx.get("selected", {}),
        "scope_governorate_id": ctx.get("scope_governorate_id"),
        "active_role": session.get("active_role"),
        "roles": roles(),
    }, ensure_ascii=False)


def _visible_employee(e):
    if not e or not getattr(e, "is_active", False):
        return False
    try:
        rs = roles()
        return True if ('مسؤول التطبيق' in rs or 'مشرف محافظة' in rs) else branch_ok(e.branch_id)
    except Exception:
        return False


def _employee_summary(e):
    branch = getattr(e, "branch", None)
    gov = getattr(branch, "governorate", None) if branch else None
    return {
        "id": e.id,
        "name": e.full_name,
        "employee_code": e.employee_code or e.job_code,
        "job_title": e.job_title,
        "job_code": e.job_code,
        "branch": branch.name if branch else None,
        "branch_id": branch.id if branch else None,
        "governorate": gov.name if gov else None,
        "governorate_id": gov.id if gov else None,
        "company_phone": e.company_phone,
        "personal_phone": e.personal_phone,
    }


def tool_execute(name, args, ctx):
    args = args or {}
    if name == "get_workspace_context":
        return {"ok": True, "context": ctx}
    if name == "search_employees":
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        if not q:
            return {"ok": False, "error": "أدخل اسم الموظف أو الكود."}
        rows = []
        for e in Employee.query.order_by(Employee.full_name).all():
            if not _visible_employee(e):
                continue
            hay = " ".join(filter(None, [e.full_name, e.employee_code, e.job_code, e.company_phone, e.personal_phone])).lower()
            if q in hay:
                rows.append(_employee_summary(e))
                if len(rows) >= limit:
                    break
        return {"ok": True, "count": len(rows), "employees": rows}
    if name == "get_employee_profile":
        eid = _safe_int(args.get("employee_id"))
        e = db.session.get(Employee, eid) if eid else None
        if not _visible_employee(e):
            return {"ok": False, "error": "الموظف غير موجود أو خارج نطاق الصلاحية."}
        session["assistant_context_employee_id"] = e.id
        movements = (Movement.query.filter_by(employee_id=e.id).order_by(Movement.id.desc()).limit(8).all())
        return {
            "ok": True,
            "employee": _employee_summary(e),
            "movements": [{
                "id": m.id, "type": m.movement_type, "leave_type": m.leave_type,
                "from_date": str(m.from_date) if m.from_date else None,
                "to_date": str(m.to_date) if m.to_date else None,
                "permission_date": str(m.permission_date) if m.permission_date else None,
                "destination_branch": m.destination_branch.name if getattr(m, "destination_branch", None) else None,
                "status": m.status,
                "assignment_state": m.assignment_state,
            } for m in movements],
        }
    if name == "search_branches":
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        gid = _safe_int(args.get("governorate_id"))
        rows = []
        for b in Branch.query.filter_by(is_active=True).order_by(Branch.name).all():
            if gid and b.governorate_id != gid:
                continue
            if not ('مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles()) and not branch_ok(b.id):
                continue
            if q and q not in (b.name or "").lower() and q not in str(b.code or "").lower():
                continue
            rows.append({"id": b.id, "name": b.name, "code": b.code, "governorate": b.governorate.name if b.governorate else None, "governorate_id": b.governorate_id})
            if len(rows) >= limit:
                break
        return {"ok": True, "count": len(rows), "branches": rows}
    if name == "search_governorates":
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        rows = []
        for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all():
            if q and q not in (g.name or "").lower():
                continue
            if not (set(effective_user_gov_ids(me())) & {g.id}) and 'مسؤول التطبيق' not in roles():
                continue
            rows.append({"id": g.id, "name": g.name})
            if len(rows) >= limit:
                break
        return {"ok": True, "count": len(rows), "governorates": rows}
    if name == "search_movements":
        query = Movement.query.join(Employee).filter(Employee.is_active == True)
        eid = _safe_int(args.get("employee_id"))
        gid = _safe_int(args.get("governorate_id"))
        bid = _safe_int(args.get("branch_id"))
        mt = args.get("movement_type")
        if eid: query = query.filter(Movement.employee_id == eid)
        if mt: query = query.filter(Movement.movement_type == mt)
        if gid: query = query.filter(Employee.branch.has(governorate_id=gid))
        if bid: query = query.filter(Employee.branch_id == bid)
        rows = []
        for m in query.order_by(Movement.id.desc()).limit(30).all():
            if not ('مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles()) and not branch_ok(m.employee.branch_id):
                continue
            date_filter = str(args.get("date") or "").strip()
            if date_filter:
                candidates = [m.from_date, m.to_date, m.permission_date]
                if not any(str(x) == date_filter for x in candidates if x):
                    continue
            rows.append({
                "id": m.id, "employee_id": m.employee_id, "employee": m.employee.full_name,
                "type": m.movement_type, "leave_type": m.leave_type,
                "from_date": str(m.from_date) if m.from_date else None,
                "to_date": str(m.to_date) if m.to_date else None,
                "permission_date": str(m.permission_date) if m.permission_date else None,
                "destination_branch": m.destination_branch.name if getattr(m, "destination_branch", None) else None,
                "status": m.status, "assignment_state": m.assignment_state,
            })
        return {"ok": True, "count": len(rows), "movements": rows}
    if name == "navigate_to":
        mapping = {
            "home": "/", "employees": "/employees", "employee": "/employees", "movements": "/movements",
            "reports": "/reports", "missions": "/reports-missions", "delegations": "/delegations",
            "administration": "/structure", "users": "/users", "branches": "/branches", "governorates": "/governorates", "lookups": "/lookups", "audit": "/audit",
        }
        target = args.get("target")
        if target not in mapping:
            return {"ok": False, "error": "صفحة غير معروفة."}
        # التنقل عبر بسيوني لا يتجاوز حدود الدور النشط.
        current_roles = roles()
        if target == "delegations" and "مشرف محافظة" not in current_roles and "مسؤول التطبيق" not in current_roles:
            return {"ok": False, "error": "صفحة التفويض متاحة لمشرف المحافظة ومسؤول التطبيق فقط."}
        if target in {"administration", "users", "branches", "governorates", "lookups"} and "مسؤول التطبيق" not in current_roles:
            return {"ok": False, "error": "هذه الصفحة إدارية ومخصصة لمسؤول التطبيق."}
        if target == "audit" and not can("view_audit"):
            return {"ok": False, "error": "لا تملك صلاحية سجل التدقيق."}
        if target in {"employees", "employee"} and not can("manage_employees") and not can("view_reports"):
            return {"ok": False, "error": "لا تملك صلاحية دليل الموظفين."}
        if target in {"movements", "reports", "missions"} and not (can("manage_movements") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية هذه المساحة التشغيلية."}
        return {"ok": True, "navigate": mapping[target]}
    if name == "prepare_action":
        return _prepare_action(args, ctx)
    return {"ok": False, "error": f"أداة غير معروفة: {name}"}


def _prepare_action(args, ctx):
    """Use the existing local safety/plan layer for mutations."""
    from .manager import plan as manager_plan
    from .routes import build_movement_plan

    action = str(args.get("action") or "").strip()
    normalized = dict(args)
    normalized["intent"] = action
    # Prefer explicit IDs, then current workspace selection, then names locally.
    selected = ctx.get("selected", {})
    if not normalized.get("employee_id"):
        normalized["employee_id"] = selected.get("employee_id")
    if not normalized.get("movement_id"):
        normalized["movement_id"] = selected.get("movement_id")
    if not normalized.get("branch_id"):
        normalized["branch_id"] = selected.get("branch_id")
    if action == "register_movement":
        result = build_movement_plan(normalized)
    else:
        result = manager_plan(normalized)
    if result is None:
        return {"ok": False, "error": "لم أستطع تجهيز هذه العملية من المعطيات الحالية."}
    if result.get("plan"):
        return {"ok": True, "needs_confirmation": True, "plan_kind": "movement" if action == "register_movement" else "manager", "plan": result["plan"], "title": result.get("title"), "preview": result.get("preview"), "error": result.get("error")}
    return {"ok": True, "needs_confirmation": False, "title": result.get("title"), "answer": result.get("answer"), "error": result.get("error"), "choices": result.get("choices", [])}


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
    endpoint = GEMINI_INTERACTION_URL.format(model=urllib.parse.quote(model, safe=""))
    role_text = ", ".join(roles())
    system = SYSTEM + f"\n\nسياق مساحة العمل الحالي (بيانات وصفية من التطبيق): {json.dumps(context, ensure_ascii=False)}\nالدور النشط: {session.get('active_role') or role_text}. اسم المساعد: بسيوني في الخدمة. الصفحة الحالية سياق مساعد وليست قيدًا على قدراتك."
    payload = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
        "tools": [{"functionDeclarations": tool_schemas()}],
        "generationConfig": {"maxOutputTokens": 700, "thinkingConfig": {"thinkingLevel": "low"}},
    }
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(current_app.config.get("ASSISTANT_TIMEOUT_SECONDS", 25))) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("Gemini agent request failed: %s", exc)
        return None


def run_agent(prompt, prior_chat, workspace_context):
    """Run one conversational turn with local application tools and confirmation-ready mutations."""
    context = _workspace_context(workspace_context)
    history = []
    for item in (prior_chat or [])[-30:]:
        role = "user" if item.get("role") == "user" else "model"
        text = str(item.get("text") or "").strip()
        if text:
            history.append({"role": role, "parts": [{"text": text[:1800]}]})
    history.append({"role": "user", "parts": [{"text": str(prompt)[:4000]}]})
    contents = history

    pending_result = None
    navigation = None
    for _ in range(MAX_AGENT_ROUNDS):
        response = _call_gemini(contents, context)
        if not response:
            return None
        calls = _extract_function_calls(response)
        if not calls:
            text = _extract_text(response)
            out = {"title": "المساعد الذكي", "answer": text or "لم أستطع استخراج رد واضح من النموذج."}
            if pending_result:
                out["preview"] = pending_result.get("preview")
                out["pending_title"] = pending_result.get("title")
            if navigation:
                out["navigate_url"] = navigation
            return out
        model_content = next(((c.get("content") or {}) for c in response.get("candidates", []) if c.get("content")), None)
        if model_content:
            contents.append(model_content)
        function_parts = []
        for call in calls:
            try:
                result = tool_execute(call["name"], call.get("args") or {}, context)
            except Exception as exc:
                logger.exception("Assistant tool %s failed", call.get("name"))
                result = {"ok": False, "error": "تعذر تنفيذ الأداة محليًا.", "debug": str(exc)[:200]}
            if result.get("needs_confirmation") and result.get("plan"):
                pending_result = result
                if result.get("plan_kind") == "manager":
                    session["assistant_manager_pending"] = result["plan"]
                else:
                    session["assistant_pending"] = result["plan"]
            if result.get("navigate"):
                navigation = result["navigate"]
                context["navigate"] = result["navigate"]
            function_parts.append({
                "functionResponse": {
                    "name": call["name"],
                    "id": call.get("id") or None,
                    "response": result,
                }
            })
        contents.append({"role": "user", "parts": function_parts})

    return {"title": "المساعد الذكي", "error": "احتاج المساعد إلى خطوات أكثر من الحد المسموح لهذه الرسالة."}
