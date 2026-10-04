"""Database bootstrap executed once per process start (before workers fork).

This module creates missing tables, adds columns introduced by later releases
(the project predates Alembic), applies idempotent data migrations and makes
sure the initial administrator account exists.

Every data migration is recorded as a ``system_migration`` row in ``Lookup`` so
it runs only once. Nothing here ever deletes business data.
"""

import logging
import secrets

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from .access import actual_roles, user_branch_ids
from .assignments import supervisor_for_governorate, sync_role_accounts
from .config import ConfigError
from .extensions import db
from .models import Branch, Employee, Lookup, RoleAccount, SupervisorEntry, User, UserBranch, UserGovernorate, UserRole
from .validation import valid_email

logger = logging.getLogger(__name__)

SUPERVISOR_ROLE = 'مشرف محافظة'
ADMIN_ROLE = 'مسؤول التطبيق'
ENTRY_ROLE = 'المدخل الأول'

DEFAULT_LOOKUPS = (
    ('movement', 'إجازة'),
    ('movement', 'انتداب'),
    ('movement', 'إذن'),
    ('leave', 'سنوية'),
    ('leave', 'عارضة'),
    ('leave', 'مصيف'),
    ('leave', 'وضع'),
)

# Columns added after the first release: table -> {column: SQL type}.
ADDED_COLUMNS = {
    'movement': {
        'is_active': 'BOOLEAN NOT NULL DEFAULT TRUE',
        'deleted_by': 'INTEGER',
        'deleted_at': 'TIMESTAMP',
        'rejection_reason': 'TEXT',
        'assignment_state': "VARCHAR(30) NOT NULL DEFAULT 'ساري'",
        'closed_by': 'INTEGER',
        'closed_at': 'TIMESTAMP',
        'closure_reason': 'TEXT',
        'last_assignment_notice_at': 'TIMESTAMP',
        'mission_state': "VARCHAR(30) NOT NULL DEFAULT 'تحت التحرير'",
        'approver_id': 'INTEGER',
    },
    '"user"': {
        'job_title': 'VARCHAR(200)',
        'job_code': 'VARCHAR(100)',
        'email': 'VARCHAR(254)',
    },
    'employee': {
        'user_id': 'INTEGER',
        'email': 'VARCHAR(254)',
        'deleted_at': 'TIMESTAMP',
        'deleted_by': 'INTEGER',
        'resignation_date': 'DATE',
        'rehire_date': 'DATE',
        'resignation_by': 'INTEGER',
    },
}


# --------------------------------------------------------------------------- helpers
def _migration_done(key):
    return Lookup.query.filter_by(kind='system_migration', name=key).first() is not None


def _mark_migration(key):
    db.session.add(Lookup(kind='system_migration', name=key, is_active=True))


def _ensure_role(user, role):
    if not UserRole.query.filter_by(user_id=user.id, role=role).first():
        db.session.add(UserRole(user_id=user.id, role=role))
        db.session.flush()


# --------------------------------------------------------------------------- schema
def _seed_default_lookups():
    for kind, name in DEFAULT_LOOKUPS:
        if not Lookup.query.filter_by(kind=kind, name=name).first():
            db.session.add(Lookup(kind=kind, name=name, is_active=True))
    db.session.commit()


def _add_missing_columns():
    """``db.create_all`` never alters existing tables, so add newer columns explicitly."""
    inspector = inspect(db.engine)
    for table, columns in ADDED_COLUMNS.items():
        existing = {c['name'] for c in inspector.get_columns(table.strip('"'))}
        for name, sql_type in columns.items():
            if name not in existing:
                # Identifiers and types come from the constant mapping above, never from user input.
                db.session.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {sql_type}'))
    if db.engine.dialect.name == 'postgresql':
        db.session.execute(text('ALTER TABLE employee ALTER COLUMN employee_code DROP NOT NULL'))


def _backfill_supervisor_links():
    """Link entry accounts to their supervisor when exactly one supervisor owns the governorate."""
    for entry_user in User.query.filter_by(is_active=True).all():
        if ENTRY_ROLE not in actual_roles(entry_user):
            continue
        if SupervisorEntry.query.filter_by(entry_id=entry_user.id).first():
            continue
        branch_ids = user_branch_ids(entry_user)
        governorate_ids = {
            b.governorate_id for b in Branch.query.filter(Branch.id.in_(branch_ids)).all()
        }
        if len(governorate_ids) == 1:
            supervisor = supervisor_for_governorate(next(iter(governorate_ids)))
            if supervisor:
                db.session.add(SupervisorEntry(supervisor_id=supervisor.id, entry_id=entry_user.id))


def _normalize_legacy_movements():
    # Legacy approved missions are considered closed; the rest start as drafts.
    db.session.execute(
        text(
            "UPDATE movement SET mission_state='مغلقة' WHERE movement_type='انتداب' "
            "AND status='معتمدة' AND (mission_state IS NULL OR mission_state='تحت التحرير')"
        )
    )
    # Approval/review are no longer part of the movement lifecycle: collapse legacy statuses.
    db.session.execute(
        text(
            "UPDATE movement SET status='مسجلة' WHERE status IS NULL "
            "OR status IN ('مسودة','مدخلة','تحت المراجعة','معتمدة','مرفوضة')"
        )
    )


def _link_entry_accounts_to_employees():
    """Attach first-level accounts to their employee record when the match is unambiguous."""
    for entry_user in User.query.filter_by(is_active=True).all():
        if ENTRY_ROLE not in actual_roles(entry_user):
            continue
        if Employee.query.filter_by(user_id=entry_user.id).first():
            continue
        query = Employee.query.filter(Employee.full_name == entry_user.full_name)
        if entry_user.job_code:
            query = query.filter(Employee.job_code == entry_user.job_code)
        branch_ids = list(user_branch_ids(entry_user))
        if branch_ids:
            query = query.filter(Employee.branch_id.in_(branch_ids))
        matches = query.order_by(Employee.id.asc()).all()
        if len(matches) == 1:
            matches[0].user_id = entry_user.id



def _remove_legacy_entry_login_roles():
    """Remove the historical first-level login role without deleting organizational data."""
    db.session.execute(text("DELETE FROM user_role WHERE role = 'المدخل الأول'"))
    db.session.execute(text("DELETE FROM role_account WHERE role = 'المدخل الأول'"))

def ensure_schema():
    db.create_all()
    _seed_default_lookups()
    _add_missing_columns()
    _backfill_supervisor_links()
    _normalize_legacy_movements()
    _remove_legacy_entry_login_roles()
    db.session.commit()


# --------------------------------------------------------------------------- administrator
def ensure_admin_account(app):
    """Return the administrator ``User``, creating it on first start."""
    username = app.config['ADMIN_USERNAME']
    email = app.config['ADMIN_EMAIL']
    email = email if valid_email(email) else None
    admin = User.query.filter_by(username=username).first()
    if admin is None:
        password = app.config['ADMIN_PASSWORD']
        if not password:
            if app.config['APP_ENV'] == 'production':
                raise ConfigError('ADMIN_PASSWORD مطلوب لإنشاء حساب مسؤول التطبيق عند أول تشغيل.')
            password = secrets.token_urlsafe(12)
            logger.warning('تم إنشاء المسؤول %r بكلمة مرور مؤقتة: %s', username, password)
        admin = User(
            username=username,
            full_name=ADMIN_ROLE,
            email=email,
            password_hash=generate_password_hash(password),
            must_change_password=False,
        )
        db.session.add(admin)
        db.session.flush()
    else:
        if email:
            admin.email = email
        admin.job_title = admin.job_title or ADMIN_ROLE
        admin.job_code = admin.job_code or 'ADMIN'
        db.session.commit()
    return admin


def apply_admin_role_migrations(admin):
    """Idempotent role corrections for the administrator account (oldest first)."""
    # v34.45 — one-off cleanup of a stale governorate scope on the admin account.
    key = 'migration:admin-supervisor-scope-cleanup-v34.45'
    if not _migration_done(key):
        UserRole.query.filter_by(user_id=admin.id, role=SUPERVISOR_ROLE).delete()
        UserGovernorate.query.filter_by(user_id=admin.id).delete()
        UserBranch.query.filter_by(user_id=admin.id).delete()
        RoleAccount.query.filter_by(user_id=admin.id, role=SUPERVISOR_ROLE).delete()
        _ensure_role(admin, ADMIN_ROLE)
        _mark_migration(key)
        db.session.flush()
    sync_role_accounts(admin)
    for user in User.query.filter_by(is_active=True).all():
        sync_role_accounts(user)
    db.session.commit()

    # v35.64 — the admin keeps a parallel «مشرف محافظة» role selectable from the role switcher.
    key = 'migration:admin-parallel-supervisor-role-v35.64'
    if not _migration_done(key):
        _ensure_role(admin, SUPERVISOR_ROLE)
        sync_role_accounts(admin)
        _mark_migration(key)
        db.session.commit()

    # v50.1 — self-healing: the parallel supervisor role must never silently disappear.
    _ensure_role(admin, SUPERVISOR_ROLE)
    sync_role_accounts(admin)
    key = 'migration:admin-parallel-supervisor-role-self-heal-v50.1'
    if not _migration_done(key):
        _mark_migration(key)
    db.session.commit()

    # v49.19 — «المدخل الأول» is an organizational classification, not a login role for the admin.
    key = 'migration:admin-remove-organizational-entry-login-v49.19'
    if not _migration_done(key):
        UserRole.query.filter_by(user_id=admin.id, role=ENTRY_ROLE).delete()
        RoleAccount.query.filter_by(user_id=admin.id, role=ENTRY_ROLE).delete()
        sync_role_accounts(admin)
        _mark_migration(key)
        db.session.commit()


def init_database(app):
    """Entry point used by :func:`employee_movements.create_app`."""
    ensure_schema()
    admin = ensure_admin_account(app)
    apply_admin_role_migrations(admin)
    db.session.commit()
