"""Format locally-authorized assistant tool results for the user interface.

Live record data is rendered here and is never sent back to the external model.
"""

from ..access import can


def render_tool_result_response(name, result, args, context):
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
        lines = [" • " + ("اقتراح يحتاج تأكيدًا: " if b.get("confirmation_required") else "") + " — ".join(x for x in (b.get("name"), b.get("code"), b.get("governorate")) if x) for b in rows]
        return {"title": "بحث الفروع", "answer": (f"وجدت {len(rows)} فرعًا:\n" + "\n".join(lines)) if rows else "لم أعثر على فرع مطابق ضمن الصلاحيات."}

    if name == "search_governorates":
        rows = result.get("governorates") or []
        lines = [" • " + ("اقتراح يحتاج تأكيدًا: " if g.get("confirmation_required") else "") + str(g.get("name") or "") for g in rows]
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
