"""Static Gemini tool declarations, kept separate from local execution."""

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
