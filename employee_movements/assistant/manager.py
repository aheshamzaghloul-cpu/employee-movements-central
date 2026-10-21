"""Safe execution layer for the in-app application manager assistant.

Gemini never receives live records or secrets. It only describes the user's requested
operation; this module resolves records locally, checks permissions, creates a preview,
and performs the mutation only after explicit confirmation.
"""
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from .manager_access import ADMIN_ROLE as ADMIN_ROLE, is_app_manager as is_app_manager
from .manager_execution import execute_plan as _execute_plan
from .manager_planning import build_plan as _build_plan
from .manager_resolvers import resolve_governorate as _match_gov



def plan(a):
    """Backward-compatible entry point for building an admin confirmation plan."""
    return _build_plan(a)


def execute(plan):
    """Execute a previously previewed plan inside one atomic DB transaction.

    A failed validation must never leave partial mutations pending in the
    current SQLAlchemy session. The inner executor keeps the existing business
    logic; this wrapper owns transaction rollback/commit boundaries.
    """
    try:
        ok, message = _execute(plan)
        if not ok:
            db.session.rollback()
            return ok, message
        db.session.commit()
        return ok, message
    except IntegrityError:
        db.session.rollback()
        return False, 'تعارضت العملية مع بيانات محفوظة أو قيد فريد؛ لم يتم تثبيت أي تغيير. أعد مراجعة البيانات وحاول مرة أخرى.'
    except Exception:
        db.session.rollback()
        raise


def _execute(plan):
    """Backward-compatible entry point for the manager mutation service."""
    return _execute_plan(plan)
