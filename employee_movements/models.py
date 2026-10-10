"""SQLAlchemy models."""

from datetime import datetime

from sqlalchemy import UniqueConstraint

from .extensions import db


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=True)
    job_title = db.Column(db.String(200))
    job_code = db.Column(db.String(100))
    password_hash = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    must_change_password = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)


class UserPermission(db.Model):
    __table_args__ = (UniqueConstraint('user_id', 'permission', name='uq_user_permission'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    permission = db.Column(db.String(60), nullable=False)


class UserRole(db.Model):
    __table_args__ = (UniqueConstraint('user_id', 'role', name='uq_user_role'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(40), nullable=False)


class RoleAccount(db.Model):
    __table_args__ = (UniqueConstraint('user_id', 'role', name='uq_role_account_user_role'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    role = db.Column(db.String(40), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    password_hash = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class EntryAssignment(db.Model):
    __table_args__ = (UniqueConstraint('employee_id', name='uq_entry_assignment_employee'),)
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey('employee.id', ondelete='CASCADE'),
        nullable=False,
    )
    supervisor_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='RESTRICT'),
        nullable=False,
    )
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    employee = db.relationship('Employee', foreign_keys=[employee_id])
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])


class EntryAssignmentBranch(db.Model):
    __table_args__ = (
        UniqueConstraint('entry_assignment_id', 'branch_id', name='uq_entry_assignment_branch'),
    )
    id = db.Column(db.Integer, primary_key=True)
    entry_assignment_id = db.Column(
        db.Integer,
        db.ForeignKey('entry_assignment.id', ondelete='CASCADE'),
        nullable=False,
    )
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey('branch.id', ondelete='RESTRICT'),
        nullable=False,
    )
    assignment = db.relationship('EntryAssignment', foreign_keys=[entry_assignment_id])
    branch = db.relationship('Branch', foreign_keys=[branch_id])


class Governorate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)


class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    governorate_id = db.Column(
        db.Integer,
        db.ForeignKey('governorate.id', ondelete='RESTRICT'),
        nullable=False,
    )
    name = db.Column(db.String(200), nullable=False)
    code = db.Column(db.String(80))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    governorate = db.relationship('Governorate')


class UserGovernorate(db.Model):
    __table_args__ = (UniqueConstraint('user_id', 'governorate_id', name='uq_user_gov'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    governorate_id = db.Column(
        db.Integer,
        db.ForeignKey('governorate.id', ondelete='CASCADE'),
        nullable=False,
    )


class UserBranch(db.Model):
    __table_args__ = (UniqueConstraint('user_id', 'branch_id', name='uq_user_branch'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey('branch.id', ondelete='CASCADE'),
        nullable=False,
    )


class SupervisorEntry(db.Model):
    __table_args__ = (UniqueConstraint('entry_id', 'supervisor_id', name='uq_supervisor_entry'),)
    id = db.Column(db.Integer, primary_key=True)
    supervisor_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='CASCADE'),
        nullable=False,
    )
    entry_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    entry = db.relationship('User', foreign_keys=[entry_id])


class ApprovalDelegation(db.Model):
    __table_args__ = (
        UniqueConstraint(
            'supervisor_id',
            'governorate_id',
            'starts_at',
            'ends_at',
            name='uq_approval_delegation_window',
        ),
    )
    id = db.Column(db.Integer, primary_key=True)
    supervisor_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='RESTRICT'),
        nullable=False,
    )
    delegate_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='RESTRICT'),
        nullable=False,
    )
    governorate_id = db.Column(
        db.Integer,
        db.ForeignKey('governorate.id', ondelete='RESTRICT'),
        nullable=False,
    )
    starts_at = db.Column(db.Date, nullable=False)
    ends_at = db.Column(db.Date, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_by = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='RESTRICT'),
        nullable=False,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    revoked_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.Text)
    supervisor = db.relationship('User', foreign_keys=[supervisor_id])
    delegate = db.relationship('User', foreign_keys=[delegate_id])
    governorate = db.relationship('Governorate')


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(100), unique=True, nullable=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='SET NULL'),
        unique=True,
        nullable=True,
    )
    email = db.Column(db.String(254), unique=True, nullable=True)
    full_name = db.Column(db.String(250), nullable=False)
    branch_id = db.Column(
        db.Integer,
        db.ForeignKey('branch.id', ondelete='RESTRICT'),
        nullable=False,
    )
    job_title = db.Column(db.String(200))
    job_code = db.Column(db.String(100))
    hire_date = db.Column(db.Date)
    company_phone = db.Column(db.String(80))
    personal_phone = db.Column(db.String(80))
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    resignation_date = db.Column(db.Date)
    rehire_date = db.Column(db.Date)
    resignation_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    branch = db.relationship('Branch')


class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey('employee.id', ondelete='RESTRICT'),
        nullable=False,
    )
    movement_type = db.Column(db.String(30), nullable=False)
    leave_type = db.Column(db.String(100))
    destination_branch_id = db.Column(db.Integer, db.ForeignKey('branch.id', ondelete='RESTRICT'))
    from_date = db.Column(db.Date)
    to_date = db.Column(db.Date)
    permission_date = db.Column(db.Date)
    status = db.Column(db.String(30), default='مسجلة', nullable=False)
    notes = db.Column(db.Text)
    rejection_reason = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    deleted_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    deleted_at = db.Column(db.DateTime)
    created_by = db.Column(
        db.Integer,
        db.ForeignKey('user.id', ondelete='RESTRICT'),
        nullable=False,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    modified_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    modified_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    reviewed_at = db.Column(db.DateTime)
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    approved_at = db.Column(db.DateTime)
    approver_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    employee = db.relationship('Employee')
    approver = db.relationship('User', foreign_keys=[approver_id])
    destination = db.relationship('Branch', foreign_keys=[destination_branch_id])
    assignment_state = db.Column(db.String(30), default='ساري', nullable=False)
    mission_state = db.Column(db.String(30), default='تحت التحرير', nullable=False)
    closed_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    closed_at = db.Column(db.DateTime)
    closed_by_user = db.relationship('User', foreign_keys=[closed_by])
    closure_reason = db.Column(db.Text)
    last_assignment_notice_at = db.Column(db.DateTime)


class MissionEditRequest(db.Model):
    __table_args__ = (UniqueConstraint('movement_id', 'status', name='uq_mission_edit_request_status'),)
    id = db.Column(db.Integer, primary_key=True)
    movement_id = db.Column(db.Integer, db.ForeignKey('movement.id', ondelete='CASCADE'), nullable=False)
    requested_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='RESTRICT'), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    details_snapshot = db.Column(db.Text)
    status = db.Column(db.String(30), default='قيد المراجعة', nullable=False)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    reviewed_at = db.Column(db.DateTime)
    manager_notes = db.Column(db.Text)
    final_state = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    movement = db.relationship('Movement', foreign_keys=[movement_id])
    requester = db.relationship('User', foreign_keys=[requested_by])
    reviewer = db.relationship('User', foreign_keys=[reviewed_by])


class MovementHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movement_id = db.Column(
        db.Integer,
        db.ForeignKey('movement.id', ondelete='CASCADE'),
        nullable=False,
    )
    from_status = db.Column(db.String(30))
    to_status = db.Column(db.String(30))
    action = db.Column(db.String(50), nullable=False)
    reason = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    movement = db.relationship('Movement')


class Audit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    action = db.Column(db.String(80), nullable=False)
    entity = db.Column(db.String(80))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AssistantMessage(db.Model):
    """Server-side assistant conversation history.

    Keeping chat text here instead of Flask's signed cookie allows a long,
    continuous conversation without making the session cookie oversized.
    """
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    text = db.Column(db.Text, nullable=False)
    title = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)


class Lookup(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(30), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    __table_args__ = (UniqueConstraint('kind', 'name', name='uq_lookup_kind_name'),)
