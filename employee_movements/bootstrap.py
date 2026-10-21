"""Database bootstrap executed once per process start (before workers fork).

This module creates missing tables, adds columns introduced by later releases
(the project predates Alembic), applies idempotent data migrations and makes
sure the initial administrator account exists.

Every data migration is recorded as a ``system_migration`` row in ``Lookup`` so
it runs only once. Nothing here ever deletes business data.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash

from .access import actual_roles, user_branch_ids
from .assignments import supervisor_for_governorate, sync_role_accounts
from .config import ConfigError
from .constants import LOGIN_ROLES
from .extensions import db
from .models import (
    AssistantAlias,  # noqa: F401 - register mapped legacy alias table
    AssistantMessage,
    AssistantSessionState,  # noqa: F401 - register server-side assistant state table
    Branch,
    Employee,
    Lookup,
    MissionEditRequest,
    MissionTicketImageDraft,
    RoleAccount,
    SupervisorEntry,
    TicketEmployeeCodeAlias,  # noqa: F401 - register mapped legacy alias table
    User,
    UserBranch,
    UserGovernorate,
    UserRole,
)
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
        'auth_version': 'INTEGER NOT NULL DEFAULT 0',
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
    # Nullable for backward compatibility. Historical conversations remain
    # unclassified and therefore are not injected into any active-role context.
    'assistant_message': {
        'active_role': 'VARCHAR(80)',
    },
}


# --------------------------------------------------------------------------- helpers
def _migration_done(key):
    return Lookup.query.filter_by(kind='system_migration', name=key).first() is not None


def _mark_migration(key):
    db.session.add(Lookup(kind='system_migration', name=key, is_active=True))


def _redact_historical_assistant_credentials():
    """One-time cleanup of credentials persisted by older assistant releases.

    Only assistant conversation text/title fields are touched. Business records,
    audit records, users, and movement history are not modified.
    """
    migration_key = 'migration:assistant-chat-credential-redaction-v68.22.58'
    if _migration_done(migration_key):
        return

    # Import locally to avoid coupling the base schema bootstrap to the assistant
    # HTTP/agent modules. This helper is a pure text sanitizer.
    from .assistant.privacy import redact_secrets_for_storage

    last_id = 0
    changed = 0
    batch_size = 400
    while True:
        rows = (
            AssistantMessage.query
            .filter(AssistantMessage.id > last_id)
            .order_by(AssistantMessage.id.asc())
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        for row in rows:
            safe_text = redact_secrets_for_storage(row.text)
            safe_title = redact_secrets_for_storage(row.title) if row.title else row.title
            if safe_text != row.text:
                row.text = safe_text
                changed += 1
            if safe_title != row.title:
                row.title = safe_title[:120] if safe_title else safe_title
                changed += 1
        last_id = rows[-1].id
        # Commit bounded batches so a large historical chat table does not hold
        # the entire migration in memory or one very long transaction.
        db.session.commit()

    _mark_migration(migration_key)
    db.session.commit()
    logger.info('Redacted sensitive credential text in %s historical assistant chat fields.', changed)


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



def _ensure_pending_mission_edit_request_index():
    """Enforce one pending edit request per mission, without limiting resolved history.

    Older schema versions used a full UNIQUE(movement_id, status) constraint. That
    also prohibited a second completed/rejected request for the same mission. The
    partial unique index is the intended invariant: one row in the pending state.
    """
    table_name = MissionEditRequest.__tablename__
    backup_table = 'mission_edit_request_legacy_status_unique_v6851'
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    if backup_table in table_names:
        raise RuntimeError(
            'وجد جدول ترحيل قديم لطلبات تعديل المأموريات. أوقف التشغيل وراجع '
            'mission_edit_request_legacy_status_unique_v6851 قبل إعادة المحاولة.'
        )
    if table_name not in table_names:
        return

    dialect = db.engine.dialect.name
    unique_constraints = inspector.get_unique_constraints(table_name)
    legacy_constraint = next((
        constraint for constraint in unique_constraints
        if set(constraint.get('column_names') or ()) == {'movement_id', 'status'}
    ), None)
    index_names = {index.get('name') for index in inspector.get_indexes(table_name)}

    create_pending_index = (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mission_edit_request_pending "
        "ON mission_edit_request (movement_id) WHERE status = 'قيد المراجعة'"
    )

    if dialect == 'postgresql':
        with db.engine.begin() as connection:
            if legacy_constraint:
                constraint_name = legacy_constraint.get('name') or 'uq_mission_edit_request_status'
                quoted_name = connection.dialect.identifier_preparer.quote(constraint_name)
                connection.execute(text(
                    f'ALTER TABLE mission_edit_request DROP CONSTRAINT IF EXISTS {quoted_name}'
                ))
            if 'uq_mission_edit_request_pending' not in index_names:
                connection.execute(text(create_pending_index))
        return

    if dialect == 'sqlite':
        if legacy_constraint:
            # SQLite cannot drop a table-level UNIQUE constraint in place. Rebuild
            # only this request-history table, copying every column and primary key.
            columns = [column.name for column in MissionEditRequest.__table__.columns]
            quoted_columns = ', '.join(
                db.engine.dialect.identifier_preparer.quote(column) for column in columns
            )
            with db.engine.connect() as connection:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
                try:
                    # If an earlier partial migration had already created the new
                    # index, remove it before the rebuild because SQLite index names
                    # are database-global and would collide with the replacement table.
                    if 'uq_mission_edit_request_pending' in index_names:
                        connection.exec_driver_sql(
                            'DROP INDEX IF EXISTS uq_mission_edit_request_pending'
                        )
                    connection.exec_driver_sql(
                        f'ALTER TABLE {table_name} RENAME TO {backup_table}'
                    )
                    MissionEditRequest.__table__.create(bind=connection, checkfirst=False)
                    connection.exec_driver_sql(
                        f'INSERT INTO {table_name} ({quoted_columns}) '
                        f'SELECT {quoted_columns} FROM {backup_table}'
                    )
                    connection.exec_driver_sql(f'DROP TABLE {backup_table}')
                    connection.exec_driver_sql(create_pending_index)
                    connection.commit()
                except Exception:
                    connection.rollback()
                    raise
            return

        if 'uq_mission_edit_request_pending' not in index_names:
            with db.engine.begin() as connection:
                connection.execute(text(create_pending_index))
        return

    raise RuntimeError(
        f'قاعدة البيانات {dialect!r} غير مدعومة لترحيل قيد طلبات تعديل المأموريات؛ '
        'المطلوب SQLite أو PostgreSQL.'
    )

def _ensure_performance_indexes():
    """Add read-path indexes to existing databases without blocking PostgreSQL writes."""
    index_specs = {
        'branch': {
            'ix_branch_governorate_active_code': 'CREATE INDEX IF NOT EXISTS ix_branch_governorate_active_code ON branch (governorate_id, is_active, code)',
        },
        'employee': {
            'ix_employee_branch_active_name': 'CREATE INDEX IF NOT EXISTS ix_employee_branch_active_name ON employee (branch_id, is_active, full_name)',
            'ix_employee_job_code': 'CREATE INDEX IF NOT EXISTS ix_employee_job_code ON employee (job_code)',
        },
        'movement': {
            'ix_movement_employee_active_from': 'CREATE INDEX IF NOT EXISTS ix_movement_employee_active_from ON movement (employee_id, is_active, from_date)',
            'ix_movement_active_created': 'CREATE INDEX IF NOT EXISTS ix_movement_active_created ON movement (is_active, created_at)',
            'ix_movement_type_active_from': 'CREATE INDEX IF NOT EXISTS ix_movement_type_active_from ON movement (movement_type, is_active, from_date)',
        },
        'assistant_message': {
            'ix_assistant_message_user_role_created': 'CREATE INDEX IF NOT EXISTS ix_assistant_message_user_role_created ON assistant_message (user_id, active_role, created_at)',
        },
    }
    dialect = db.engine.dialect.name
    if dialect not in {'postgresql', 'sqlite'}:
        raise RuntimeError(f'Performance index migration does not support database dialect {dialect!r}')

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    for table_name, indexes in index_specs.items():
        if table_name not in existing_tables:
            continue
        existing_names = {item.get('name') for item in inspector.get_indexes(table_name)}
        for index_name, create_sql in indexes.items():
            if index_name in existing_names:
                continue
            if dialect == 'postgresql':
                # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
                with db.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
                    connection.execute(text(create_sql.replace('CREATE INDEX IF NOT EXISTS', 'CREATE INDEX CONCURRENTLY IF NOT EXISTS', 1)))
            else:
                with db.engine.begin() as connection:
                    connection.execute(text(create_sql))
            logger.info('Created performance index %s on %s.', index_name, table_name)


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
    # This is a one-time, versioned data migration. Re-running table-wide UPDATEs
    # on every Gunicorn master boot adds avoidable scans/locks as movement history grows.
    migration_key = 'migration:normalize-legacy-movement-states-v68.56.0'
    if _migration_done(migration_key):
        return
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
    _mark_migration(migration_key)


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
    """Retire the obsolete entry login role once; keep branch assignments intact.

    Employee-linked EntryAssignment/EntryAssignmentBranch rows are intentionally
    preserved: they identify the branch's responsible data-entry contact, not a
    login role. Accounts that only had the retired role must no longer log in and
    read the shared directory as a roleless account.
    """
    migration_key = 'migration:retire-first-entry-login-role-v68.56.0'
    if _migration_done(migration_key):
        return
    db.session.execute(text("DELETE FROM user_role WHERE role = 'المدخل الأول'"))
    db.session.execute(text("DELETE FROM role_account WHERE role = 'المدخل الأول'"))
    db.session.expire_all()

    # Fail closed for any active account without one of the three official roles.
    # Do not touch the employee record or any organizational branch assignment.
    role_rows = UserRole.query.with_entities(UserRole.user_id, UserRole.role).all()
    roles_by_user = {}
    for user_id, role in role_rows:
        roles_by_user.setdefault(user_id, set()).add(role)
    active_users = User.query.filter_by(is_active=True).all()
    orphan_ids = [
        user.id for user in active_users
        if not (roles_by_user.get(user.id, set()) & set(LOGIN_ROLES))
    ]
    if orphan_ids:
        User.query.filter(User.id.in_(orphan_ids)).update({User.is_active: False}, synchronize_session=False)
        RoleAccount.query.filter(RoleAccount.user_id.in_(orphan_ids)).delete(synchronize_session=False)
        logger.warning(
            'Disabled %s account(s) without an official login role after retiring the first-entry role.',
            len(orphan_ids),
        )
    _mark_migration(migration_key)
    db.session.flush()


def _cleanup_expired_mission_ticket_image_drafts():
    """Delete abandoned ticket images after their short review window."""
    cutoff = datetime.utcnow() - timedelta(minutes=30)
    MissionTicketImageDraft.query.filter(MissionTicketImageDraft.created_at < cutoff).delete(
        synchronize_session=False,
    )
    db.session.commit()


def ensure_schema():
    db.create_all()
    _ensure_pending_mission_edit_request_index()
    _seed_default_lookups()
    _add_missing_columns()
    # End the additive-schema transaction before creating indexes on a second
    # connection; PostgreSQL CONCURRENTLY cannot run inside a transaction and
    # SQLite can otherwise hold a write lock while the index migration starts.
    db.session.commit()
    _ensure_performance_indexes()
    _cleanup_expired_mission_ticket_image_drafts()
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
            # Never generate a bootstrap credential that would need to be printed
            # to logs or recovered from the hosting provider's log viewer.
            raise ConfigError(
                'ADMIN_PASSWORD مطلوب لإنشاء حساب مسؤول التطبيق لأول مرة. '
                'اضبطه في متغيرات البيئة ثم أعد تشغيل التطبيق.'
            )
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
    _redact_historical_assistant_credentials()
