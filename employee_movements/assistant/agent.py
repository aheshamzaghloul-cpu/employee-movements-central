"""Application-agent layer for the in-app assistant.

Gemini is used as the conversational planner/tool selector.  The application remains
source of truth for records, scopes, permissions, validation and all mutations.
"""
from __future__ import annotations

import json
import logging
from datetime import date
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app, request, session

from ..access import actual_roles, bids, branch_ok, can, effective_user_gov_ids, me, roles, user_gov_ids
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement
from .directory import find_branch, find_employee
from .pending import store_pending_plan
from .visibility import visible_employee, visible_movement
from .llm import DEFAULT_MODEL
from .privacy import restore_local_tokens, sanitize_conversation_for_model

logger = logging.getLogger(__name__)

GEMINI_INTERACTION_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_AGENT_ROUNDS = 2
MAX_CONVERSATION_TURNS = 20
MAX_CONVERSATION_CHARS = 16000

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
            "description": "ابحث محليًا عن موظفين بالاسم أو كود شؤون العاملين؛ البحث برقم الهاتف متاح فقط عند امتلاك صلاحية إدارة بيانات الموظفين.",
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


def _employee_summary(e, *, include_contacts=False):
    """Build the minimum local employee summary permitted for this user."""
    branch = getattr(e, "branch", None)
    gov = getattr(branch, "governorate", None) if branch else None
    summary = {
        "id": e.id,
        "name": e.full_name,
        "employee_code": e.employee_code or e.job_code,
        "job_title": e.job_title,
        "job_code": e.job_code,
        "branch": branch.name if branch else None,
        "branch_id": branch.id if branch else None,
        "governorate": gov.name if gov else None,
        "governorate_id": gov.id if gov else None,
    }
    # Contact details are employee-management data, not a default consequence
    # of merely having report-reading permission.
    if include_contacts:
        summary.update({
            "company_phone": e.company_phone,
            "personal_phone": e.personal_phone,
        })
    return summary


def tool_execute(name, args, ctx):
    args = args or {}
    if name == "get_workspace_context":
        return {"ok": True, "context": ctx}
    if name == "search_employees":
        if not (can("manage_employees") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية دليل الموظفين أو التقارير."}
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        if not q:
            return {"ok": False, "error": "أدخل اسم الموظف أو الكود."}
        pattern = f"%{q}%"
        search_fields = [
            Employee.full_name.ilike(pattern),
            Employee.employee_code.ilike(pattern),
            Employee.job_code.ilike(pattern),
            Employee.job_title.ilike(pattern),
        ]
        # Matching by phone is itself access to contact data, even if the
        # returned summary later omits the number. Keep it management-only.
        if can("manage_employees"):
            search_fields.extend([
                Employee.company_phone.ilike(pattern),
                Employee.personal_phone.ilike(pattern),
            ])
        candidate_query = Employee.query.filter(
            Employee.is_active == True,
            db.or_(*search_fields),
        ).order_by(Employee.full_name).limit(max(limit * 5, 20))
        rows = []
        for e in candidate_query.all():
            if not visible_employee(e):
                continue
            rows.append(_employee_summary(e, include_contacts=can("manage_employees")))
            if len(rows) >= limit:
                break
        return {"ok": True, "count": len(rows), "employees": rows}
    if name == "get_employee_profile":
        if not (can("manage_employees") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية دليل الموظفين أو التقارير."}
        eid = _safe_int(args.get("employee_id"))
        e = db.session.get(Employee, eid) if eid else None
        if not visible_employee(e):
            return {"ok": False, "error": "الموظف غير موجود أو خارج نطاق الصلاحية."}
        session["assistant_context_employee_id"] = e.id
        movements = []
        if can("view_reports"):
            candidates = (
                Movement.query.filter_by(employee_id=e.id, is_active=True)
                .order_by(Movement.id.desc()).limit(30).all()
            )
            movements = [m for m in candidates if visible_movement(m)][:8]
        return {
            "ok": True,
            "employee": _employee_summary(e, include_contacts=can("manage_employees")),
            "movements": [{
                "id": m.id, "type": m.movement_type, "leave_type": m.leave_type,
                "from_date": str(m.from_date) if m.from_date else None,
                "to_date": str(m.to_date) if m.to_date else None,
                "permission_date": str(m.permission_date) if m.permission_date else None,
                "destination_branch": m.destination.name if m.destination else None,
                "status": m.status,
                "assignment_state": m.assignment_state,
            } for m in movements],
        }
    if name == "search_branches":
        if not (can("manage_structure") or can("manage_movements") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية استعراض الفروع."}
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        gid = _safe_int(args.get("governorate_id"))
        pattern = f"%{q}%" if q else None
        query = Branch.query.filter(Branch.is_active == True)
        if gid:
            query = query.filter(Branch.governorate_id == gid)
        if pattern:
            query = query.filter(db.or_(Branch.name.ilike(pattern), Branch.code.ilike(pattern)))
        if not ('مسؤول التطبيق' in roles() or 'مشرف محافظة' in roles() or 'Manager Application Support' in roles()):
            allowed = set(bids())
            if not allowed:
                return {"ok": True, "count": 0, "branches": []}
            query = query.filter(Branch.id.in_(allowed))
        rows = query.order_by(Branch.name).limit(limit).all()
        return {"ok": True, "count": len(rows), "branches": [{
            "id": b.id, "name": b.name, "code": b.code,
            "governorate": b.governorate.name if b.governorate else None,
            "governorate_id": b.governorate_id,
        } for b in rows]}
    if name == "search_governorates":
        if not (can("manage_structure") or can("manage_movements") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية استعراض المحافظات."}
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        query = Governorate.query.filter(Governorate.is_active == True)
        if q:
            query = query.filter(Governorate.name.ilike(f"%{q}%"))
        if not (set(roles()) & {'مسؤول التطبيق', 'Manager Application Support'}):
            allowed = set(effective_user_gov_ids(me()))
            if not allowed:
                return {"ok": True, "count": 0, "governorates": []}
            query = query.filter(Governorate.id.in_(allowed))
        rows = query.order_by(Governorate.name).limit(limit).all()
        return {"ok": True, "count": len(rows), "governorates": [{"id": g.id, "name": g.name} for g in rows]}
    if name == "search_movements":
        if not can("view_reports"):
            return {"ok": False, "error": "لا تملك صلاحية عرض التقارير والحركات."}
        query = Movement.query.join(Employee).filter(
            Employee.is_active == True,
            Movement.is_active == True,
        )
        eid = _safe_int(args.get("employee_id"))
        gid = _safe_int(args.get("governorate_id"))
        bid = _safe_int(args.get("branch_id"))
        mt = args.get("movement_type")
        if eid: query = query.filter(Movement.employee_id == eid)
        if mt: query = query.filter(Movement.movement_type == mt)
        if gid: query = query.filter(Employee.branch.has(governorate_id=gid))
        if bid: query = query.filter(Employee.branch_id == bid)
        date_filter = str(args.get("date") or "").strip()
        if date_filter:
            try:
                target_date = date.fromisoformat(date_filter)
            except ValueError:
                return {"ok": False, "error": "اكتب التاريخ بصيغة سنة-شهر-يوم."}
            query = query.filter(db.or_(
                Movement.from_date == target_date,
                Movement.to_date == target_date,
                Movement.permission_date == target_date,
            ))
        current_roles = set(roles())
        if 'مسؤول التطبيق' not in current_roles:
            allowed_branches = bids()
            if current_roles & {'مشرف محافظة', 'Manager Application Support'}:
                # Assignments have intentional cross-governorate read scope;
                # leave/permission rows must remain inside the selected work scope.
                if allowed_branches:
                    query = query.filter(db.or_(
                        Movement.movement_type == 'انتداب',
                        Employee.branch_id.in_(allowed_branches),
                    ))
                else:
                    query = query.filter(Movement.movement_type == 'انتداب')
            else:
                if not allowed_branches:
                    return {"ok": True, "count": 0, "movements": []}
                query = query.filter(Employee.branch_id.in_(allowed_branches))
        result_limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        rows = []
        for m in query.order_by(Movement.id.desc()).limit(result_limit).all():
            if not visible_movement(m):
                continue
            rows.append({
                "id": m.id, "employee_id": m.employee_id, "employee": m.employee.full_name,
                "type": m.movement_type, "leave_type": m.leave_type,
                "from_date": str(m.from_date) if m.from_date else None,
                "to_date": str(m.to_date) if m.to_date else None,
                "permission_date": str(m.permission_date) if m.permission_date else None,
                "destination_branch": m.destination.name if m.destination else None,
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
    # Credentials must never be supplied by the language model. The manager
    # generates temporary passwords locally at execution time.
    normalized.pop("password", None)
    normalized["intent"] = action
    # Prefer explicit IDs, then current workspace selection, then names locally.
    selected = ctx.get("selected", {})
    if not normalized.get("employee_id"):
        normalized["employee_id"] = selected.get("employee_id") or _safe_int(session.get("assistant_context_employee_id"))
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
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=int(current_app.config.get("ASSISTANT_TIMEOUT_SECONDS", 25))) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Provider error bodies can echo submitted prompt fragments; never log them.
        logger.warning("Gemini agent request failed with HTTP status %s", exc.code)
        return None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        # Avoid logging request/response payloads; only the exception class is needed.
        logger.warning("Gemini agent request failed (%s)", type(exc).__name__)
        return None


def _tool_result_response(name, result, args, context):
    """Render tool results locally; live database rows must never be sent back to Gemini."""
    if not result.get("ok"):
        return {"title": "المساعد الذكي", "error": result.get("error") or "تعذر تنفيذ الطلب محليًا."}

    if name == "get_workspace_context":
        return {"title": "سياق الصفحة", "answer": f"أنت تعمل الآن في صفحة {context.get('page') or 'التطبيق'}."}

    if name == "search_employees":
        rows = result.get("employees") or []
        if not rows:
            return {"title": "بحث الموظفين", "answer": "لم أعثر على موظف مطابق ضمن نطاق الصلاحيات."}
        lines = []
        for e in rows:
            parts = [e.get("name") or "موظف"]
            code = e.get("employee_code") or e.get("job_code")
            if code:
                parts.append(f"كود شئون العاملين: {code}")
            if e.get("job_title"):
                parts.append(e["job_title"])
            location = " — ".join(x for x in (e.get("branch"), e.get("governorate")) if x)
            if location:
                parts.append(location)
            lines.append(" • " + " — ".join(parts))
        return {"title": "نتائج بحث الموظفين", "answer": f"وجدت {len(rows)} نتيجة:\n" + "\n".join(lines)}

    if name == "get_employee_profile":
        e = result.get("employee") or {}
        if not e:
            return {"title": "ملف الموظف", "error": "تعذر قراءة ملف الموظف."}
        lines = [f"الموظف: {e.get('name') or '—'}"]
        if e.get("employee_code") or e.get("job_code"):
            lines.append(f"كود شئون العاملين: {e.get('employee_code') or e.get('job_code')}")
        if e.get("job_title"):
            lines.append(f"الوظيفة: {e['job_title']}")
        if e.get("branch") or e.get("governorate"):
            lines.append("الموقع: " + " — ".join(x for x in (e.get("branch"), e.get("governorate")) if x))
        if e.get("company_phone"):
            lines.append(f"هاتف العمل: {e['company_phone']}")
        if e.get("personal_phone"):
            lines.append(f"الهاتف الشخصي: {e['personal_phone']}")
        movements = result.get("movements") or []
        if movements:
            lines.append("آخر الحركات المسموح بعرضها:")
            for m in movements:
                period = m.get("permission_date") or " — ".join(x for x in (m.get("from_date"), m.get("to_date") or ("مفتوح" if m.get("type") == "انتداب" else None)) if x)
                detail = m.get("leave_type") or m.get("destination_branch") or ""
                lines.append(" • " + " — ".join(x for x in (m.get("type"), detail, period, m.get("status")) if x))
        elif not can("view_reports"):
            lines.append("تفاصيل الحركات غير متاحة دون صلاحية التقارير.")
        return {"title": f"ملف الموظف — {e.get('name') or ''}", "answer": "\n".join(lines)}

    if name == "search_branches":
        rows = result.get("branches") or []
        lines = [" • " + " — ".join(x for x in (b.get("name"), b.get("code"), b.get("governorate")) if x) for b in rows]
        return {"title": "بحث الفروع", "answer": (f"وجدت {len(rows)} فرعًا:\n" + "\n".join(lines)) if rows else "لم أعثر على فرع مطابق ضمن الصلاحيات."}

    if name == "search_governorates":
        rows = result.get("governorates") or []
        lines = [" • " + str(g.get("name") or "") for g in rows]
        return {"title": "بحث المحافظات", "answer": (f"وجدت {len(rows)} محافظة:\n" + "\n".join(lines)) if rows else "لم أعثر على محافظة مطابقة ضمن الصلاحيات."}

    if name == "search_movements":
        rows = result.get("movements") or []
        if not rows:
            return {"title": "بحث الحركات", "answer": "لم أعثر على حركات مطابقة ضمن نطاق التقارير المسموح."}
        lines = []
        for m in rows:
            period = m.get("permission_date") or " — ".join(x for x in (m.get("from_date"), m.get("to_date") or ("مفتوح" if m.get("type") == "انتداب" else None)) if x)
            detail = m.get("leave_type") or m.get("destination_branch") or ""
            lines.append(" • " + " — ".join(x for x in (m.get("employee"), m.get("type"), detail, period, m.get("status")) if x))
        return {"title": "نتائج الحركات", "answer": f"وجدت {len(rows)} حركة مطابقة:\n" + "\n".join(lines)}

    if name == "navigate_to":
        if result.get("navigate"):
            return {"title": "الانتقال", "answer": "تم التحقق من الصلاحية. افتح الصفحة المطلوبة.", "navigate_url": result["navigate"]}
        return {"title": "الانتقال", "error": result.get("error") or "تعذر فتح الصفحة."}

    if name == "prepare_action":
        if result.get("needs_confirmation") and result.get("plan"):
            return {
                "title": result.get("title") or "تأكيد العملية",
                "answer": "راجع تفاصيل العملية التالية وأكّد التنفيذ من داخل المحادثة. لم يتم تنفيذ أي تغيير بعد.",
                "preview": result.get("preview") or "يرجى مراجعة تفاصيل العملية.",
            }
        return {
            "title": result.get("title") or "المساعد الذكي",
            "answer": result.get("answer") or result.get("error") or "لم يتم إجراء أي تغيير.",
            "error": result.get("error"),
            "choices": result.get("choices", []),
        }

    return {"title": "المساعد الذكي", "answer": result.get("answer") or "تمت معالجة الطلب محليًا."}


def run_agent(prompt, prior_chat, workspace_context):
    """Run one conversational turn with local application tools and confirmation-ready mutations."""
    if not current_app.config.get("GEMINI_API_KEY", ""):
        return None
    context = _workspace_context(workspace_context)
    # Replace locally-known personal identifiers in prior context and the current prompt.
    # Only sanitized user-authored turns are actually packed for external transfer.
    prior_chat, prompt, local_token_map = sanitize_conversation_for_model(prior_chat, prompt)
    # Keep conversational continuity without forwarding assistant replies that may
    # contain live employee/movement data. Pack recent user turns into one clear
    # context message so follow-ups are interpreted against the whole request.
    prior = []
    for item in (prior_chat or [])[-30:]:
        if item.get("role") != "user":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            prior.append(text[:1200])
    prior = prior[-MAX_CONVERSATION_TURNS:]
    current_section = "رسالة المستخدم الحالية:\n" + str(prompt or "").strip()[:4000]
    # Reserve space for the current request and fill remaining space from the
    # newest prior turns backwards. Never let older context cut off the prompt.
    budget = MAX_CONVERSATION_CHARS - len(current_section) - 2
    selected = []
    used = 0
    for value in reversed(prior):
        entry = f"{len(prior) - len(selected)}. {value}"
        cost = len(entry) + (1 if selected else 0)
        if cost > budget - used:
            remaining = budget - used
            if remaining > 8:
                selected.append(entry[:remaining])
            break
        selected.append(entry)
        used += cost
    selected.reverse()
    sections = []
    if selected:
        sections.append("رسائل المستخدم السابقة بالترتيب (الأحدث أقرب للرسالة الحالية):\n" + "\n".join(selected))
    sections.append(current_section)
    packed = "\n\n".join(sections)
    contents = [{"role": "user", "parts": [{"text": packed[-MAX_CONVERSATION_CHARS:]}]}]

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
