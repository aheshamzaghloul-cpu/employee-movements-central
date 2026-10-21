"""Prepare assistant write actions without executing database mutations.

The application-local planner is authoritative; this module only creates a
confirmation-ready preview and never commits a transaction.
"""

from .tool_helpers import _safe_int
from .session_state import get_context_employee_id


def prepare_action(args, ctx):
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
        normalized["employee_id"] = selected.get("employee_id") or _safe_int(get_context_employee_id())
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
