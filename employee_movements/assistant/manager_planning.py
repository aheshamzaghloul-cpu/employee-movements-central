"""Authorization gate and dispatcher for assistant-manager confirmation plans.

Domain planners only resolve and validate input. Mutations remain in
manager_execution and are reached only after explicit user confirmation.
"""
from .manager_access import is_app_manager
from .manager_plan_people import plan_employee_create, plan_entry_action, plan_employee_action
from .manager_plan_users import plan_user_action, plan_role_action
from .manager_plan_structure import (
    plan_delegation_create, plan_governorate_action, plan_branch_action,
    plan_lookup_action, plan_delegation_revoke,
)
from .manager_plan_movements import plan_movement_action


def build_plan(a):
    """Resolve an assistant action into a local, confirmation-ready plan."""
    if not is_app_manager():
        return {'error': 'هذه الأوامر الإدارية متاحة لمسؤول التطبيق فقط.'}
    if (a.get('intent') or a.get('kind')) == 'movement_reopen':
        return {
            'title': 'إعادة فتح مأمورية مغلقة',
            'error': 'إعادة الفتح المباشر غير متاحة. يجب تقديم طلب تعديل واعتماده من الـManager.',
        }
    intent = a.get('intent')
    if intent not in {
        'governorate_create', 'governorate_edit', 'governorate_toggle',
        'branch_create', 'branch_edit', 'branch_toggle',
        'employee_create', 'employee_edit', 'employee_delete', 'employee_restore',
        'user_create', 'user_edit', 'user_toggle', 'user_delete', 'user_password_reset',
        'user_set_governorates', 'user_set_branches',
        'role_grant', 'role_revoke',
        'lookup_create', 'lookup_edit', 'lookup_toggle', 'lookup_delete', 'movement_edit', 'movement_delete', 'movement_close', 'entry_assign', 'entry_remove', 'entry_replace',
        'delegation_create', 'delegation_revoke',
    }:
        return None

    if intent == 'employee_create':
        return plan_employee_create(a, intent)
    if intent.startswith('user_'):
        return plan_user_action(a, intent)
    if intent in ('entry_assign', 'entry_remove', 'entry_replace'):
        return plan_entry_action(a, intent)
    if intent == 'delegation_create':
        return plan_delegation_create(a, intent)
    if intent.startswith('governorate_'):
        return plan_governorate_action(a, intent)
    if intent.startswith('branch_'):
        return plan_branch_action(a, intent)
    if intent.startswith('employee_'):
        return plan_employee_action(a, intent)
    if intent in ('movement_edit', 'movement_delete', 'movement_close'):
        return plan_movement_action(a, intent)
    if intent.startswith('lookup_'):
        return plan_lookup_action(a, intent)
    if intent == 'delegation_revoke':
        return plan_delegation_revoke(a, intent)
    if intent in ('role_grant', 'role_revoke'):
        return plan_role_action(a, intent)
    return None
