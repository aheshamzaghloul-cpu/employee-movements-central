"""Local dispatch for assistant tools.

Read tools are delegated to their read-only service; navigation checks stay
local; write tools are delegated to a preview-only preparation service.
"""

from ..access import can, roles
from .action_preparation import prepare_action
from .tool_read_handlers import execute_read_tool


def dispatch_tool(name, args, ctx):
    args = args or {}
    if name == "get_workspace_context":
        return {"ok": True, "context": ctx}
    read_result = execute_read_tool(name, args)
    if read_result is not None:
        return read_result
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
        return prepare_action(args, ctx)
    return {"ok": False, "error": f"أداة غير معروفة: {name}"}
