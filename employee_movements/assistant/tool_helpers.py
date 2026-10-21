"""Small, provider-independent helpers shared by the assistant tool handlers."""

def _safe_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


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
