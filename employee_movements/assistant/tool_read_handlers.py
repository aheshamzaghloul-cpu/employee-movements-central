"""Read-only assistant tools for employees, branches, governorates and movements.

All records stay local and pass the application's current permission and visibility
checks. This module intentionally contains no write or confirmation operations.
"""
from datetime import date


from ..access import can, readable_branch_ids
from ..extensions import db
from ..models import Branch, Employee, Governorate, Movement
from ..services.entity_matching import (
    branch_search_filter, employee_search_filter, governorate_search_filter,
    rank_governorate_suggestions, rank_scoped_branch_suggestions, rank_scoped_employee_suggestions,
)
from .visibility import visible_employee, visible_movement
from .tool_helpers import _employee_summary, _safe_int
from .session_state import set_context_employee_id


def execute_read_tool(name, args):
    """Dispatch a read-only tool; return None when ``name`` is not a read tool."""
    args = args or {}
    if name == "search_employees":
        if not (can("manage_employees") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية دليل الموظفين أو التقارير."}
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        if not q:
            return {"ok": False, "error": "أدخل اسم الموظف أو الكود."}
        # Use the same local matching engine as directory, movements and imports.
        # Phone matching remains restricted to employee managers.
        allowed_branch_ids = set(readable_branch_ids())
        candidate_scope = (
            Employee.query.join(Branch, Employee.branch_id == Branch.id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(
                Employee.is_active == True,
                Branch.is_active == True,
                Governorate.is_active == True,
                Employee.branch_id.in_(allowed_branch_ids) if allowed_branch_ids else False,
            )
        )
        # Assistant reading is global across active governorates. The actual
        # prepare_action/write path separately checks the selected work governorate.
        scoped_candidates = candidate_scope.filter(
            employee_search_filter(
                q,
                include_job_title=True,
                include_contacts=can("view_reports"),
                include_branch=True,
            ),
        ).order_by(Employee.full_name).limit(max(limit * 5, 20))
        matched_rows = scoped_candidates.all()
        fuzzy_ids = set()
        fuzzy_reasons = {}
        if not matched_rows:
            pool = candidate_scope.order_by(Employee.full_name).limit(2500).all()
            ranked = rank_scoped_employee_suggestions(q, pool, limit=limit)
            matched_rows = [item["employee"] for item in ranked]
            fuzzy_ids = {item["employee"].id for item in ranked}
            fuzzy_reasons = {
                item["employee"].id: item.get("match_reasons") or []
                for item in ranked
            }
        rows = []
        for employee in matched_rows:
            if not visible_employee(employee):
                continue
            summary = _employee_summary(employee, include_contacts=can("view_reports"))
            if employee.id in fuzzy_ids:
                summary["match_type"] = "approximate_suggestion"
                summary["confirmation_required"] = True
                summary["match_reasons"] = fuzzy_reasons.get(employee.id, [])
            rows.append(summary)
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
        set_context_employee_id(e.id)
        movements = []
        if can("view_reports"):
            candidates = (
                Movement.query.filter_by(employee_id=e.id, is_active=True)
                .order_by(Movement.id.desc()).limit(30).all()
            )
            movements = [m for m in candidates if visible_movement(m)][:8]
        return {
            "ok": True,
            "employee": _employee_summary(e, include_contacts=can("view_reports")),
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
        query = Branch.query.join(Governorate, Governorate.id == Branch.governorate_id).filter(
            Branch.is_active == True, Governorate.is_active == True,
        )
        if gid:
            query = query.filter(Branch.governorate_id == gid)
        scoped_query = query
        if q:
            query = query.filter(branch_search_filter(q, include_governorate=True))
        rows = query.order_by(Branch.name).limit(limit).all()
        fuzzy_ids = set()
        if q and not rows and len(q) >= 3:
            pool = scoped_query.order_by(Branch.name).limit(2500).all()
            ranked = rank_scoped_branch_suggestions(q, pool, limit=limit)
            rows = [item['branch'] for item in ranked]
            fuzzy_ids = {item['branch'].id for item in ranked}
        return {"ok": True, "count": len(rows), "branches": [{
            "id": b.id, "name": b.name, "code": b.code,
            "governorate": b.governorate.name if b.governorate else None,
            "governorate_id": b.governorate_id,
            "match_type": "approximate_suggestion" if b.id in fuzzy_ids else "normal",
            "confirmation_required": b.id in fuzzy_ids,
        } for b in rows]}
    if name == "search_governorates":
        if not (can("manage_structure") or can("manage_movements") or can("view_reports")):
            return {"ok": False, "error": "لا تملك صلاحية استعراض المحافظات."}
        q = str(args.get("query") or "").strip().lower()
        limit = max(1, min(10, _safe_int(args.get("limit")) or 8))
        # Governorate search is a read-only directory: all official roles can
        # inspect every active governorate without choosing work scope.
        query = Governorate.query.filter(Governorate.is_active == True)
        scoped_query = query
        if q:
            query = query.filter(governorate_search_filter(q))
        rows = query.order_by(Governorate.name).limit(limit).all()
        fuzzy_ids = set()
        if q and not rows and len(q) >= 3:
            pool = scoped_query.order_by(Governorate.name).limit(2500).all()
            ranked = rank_governorate_suggestions(q, pool, limit=limit)
            rows = [item['governorate'] for item in ranked]
            fuzzy_ids = {item['governorate'].id for item in ranked}
        return {"ok": True, "count": len(rows), "governorates": [{
            "id": g.id, "name": g.name,
            "match_type": "approximate_suggestion" if g.id in fuzzy_ids else "normal",
            "confirmation_required": g.id in fuzzy_ids,
        } for g in rows]}
    if name == "search_movements":
        if not can("view_reports"):
            return {"ok": False, "error": "لا تملك صلاحية عرض التقارير والحركات."}
        query = (
            Movement.query.join(Employee).join(Branch, Employee.branch_id == Branch.id)
            .join(Governorate, Governorate.id == Branch.governorate_id)
            .filter(
                Employee.is_active == True,
                Movement.is_active == True,
                Branch.is_active == True,
                Governorate.is_active == True,
            )
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
        # Read-only movement search is global across active governorates.
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
    return None
