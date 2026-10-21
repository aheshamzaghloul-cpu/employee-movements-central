"""Transaction-scoped identity locks shared by entity write paths.

A single advisory key provides a stable acquisition order across employee,
branch, governorate, and confirmed-alias mutations. This is intentionally
conservative: advisory locks protect only transactions that cooperate with this
module, and do not replace database constraints or validation.
"""
from __future__ import annotations

from sqlalchemy import text


# Keep this key stable across versions. One shared key avoids deadlocks caused
# by different write paths acquiring employee/catalog namespaces in different
# orders. It serializes identity-sensitive writes across the app on PostgreSQL.
_ENTITY_IDENTITY_LOCK_KEY = 0x4944454E  # "IDEN", signed 32-bit safe


def lock_entity_identity_writes(session) -> bool:
    """Serialize identity-sensitive writes until the current transaction ends.

    Returns False on dialects without PostgreSQL advisory transaction locks.
    Callers must still perform validation and handle uniqueness violations.
    """
    bind = session.get_bind()
    dialect_name = str(getattr(getattr(bind, "dialect", None), "name", "") or "").lower()
    if dialect_name != "postgresql":
        return False
    session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": _ENTITY_IDENTITY_LOCK_KEY},
    )
    return True


def lock_employee_identity_writes(session) -> bool:
    """Compatibility wrapper for employee writers; uses the shared entity gate."""
    return lock_entity_identity_writes(session)


def lock_governorate_identity_writes(session) -> bool:
    """Compatibility wrapper for governorate writers; uses the shared entity gate."""
    return lock_entity_identity_writes(session)


def lock_branch_identity_writes(session) -> bool:
    """Compatibility wrapper for branch writers; uses the shared entity gate."""
    return lock_entity_identity_writes(session)
