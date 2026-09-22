import os, secrets, re, json, urllib.request, urllib.error
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, has_request_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
APP_VERSION='v34.95'
DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///local.db')
if DATABASE_URL.startswith('postgres://'): DATABASE_URL=DATABASE_URL.replace('postgres://','postgresql+psycopg://',1)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or 'dev-only-change-me',SQLALCHEMY_DATABASE_URI=DATABASE_URL,SQLALCHEMY_TRACK_MODIFICATIONS=False,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1',MAX_CONTENT_LENGTH=2*1024*1024)
db=SQLAlchemy(app)
ROLES=['مسؤول التطبيق','مشرف محافظة','المدخل الأول','Manager Application Support']
MOVEMENT_TYPES=['إجازة','انتداب','إذن']
LEAVE_TYPES=['سنوية','عارضة','مصيف','وضع']
STATUSES=['مدخلة','تحت المراجعة','معتمدة','مرفوضة']
ASSIGNMENT_ALERT_DAYS=1
ASSIGNMENT_STATES=['ساري','قرب الانتهاء','انتهت المدة']

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False); full_name=db.Column(db.String(200),nullable=False); email=db.Column(db.String(254),unique=True,nullable=True); job_title=db.Column(db.String(200)); job_code=db.Column(db.String(100)); password_hash=db.Column(db.Text,nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False); must_change_password=db.Column(db.Boolean,default=True,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); last_login=db.Column(db.DateTime)
PERMISSIONS={
 'manage_users':'إدارة المستخدمين',
 'manage_structure':'إدارة المحافظات والفروع',
 'manage_employees':'إدارة الموظفين',
 'manage_movements':'تسجيل وتعديل الحركات',
 'review_movements':'مراجعة واعتماد الحركات',
 'view_reports':'التقارير',
 'view_audit':'سجل العمليات',
 'cancel_approval':'إلغاء اعتماد الحركة',
 'delete_movements':'حذف الحركات'
}
GRANTABLE_BY_SUPERVISOR={'manage_employees','manage_movements','view_reports'}
ROLE_DEFAULT_PERMISSIONS={
 'مسؤول التطبيق':set(PERMISSIONS),
 'مشرف محافظة':{'manage_users','manage_structure','manage_employees','review_movements','view_reports','cancel_approval'},
 'المدخل الأول':{'manage_employees','manage_movements','view_reports'},
 'Manager Application Support':{'manage_employees','manage_movements','view_reports'}
}
class UserPermission(db.Model):
    __table_args__=(UniqueConstraint('user_id','permission',name='uq_user_permission'),)
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False); permission=db.Column(db.String(60),nullable=False)
class UserRole(db.Model):
    __table_args__=(UniqueConstraint('user_id','role',name='uq_user_role'),)
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False); role=db.Column(db.String(40),nullable=False)
class RoleAccount(db.Model):
    __table_args__=(UniqueConstraint('user_id','role',name='uq_role_account_user_role'),)
    id=db.Column(db.Integer,primary_key=True)
    user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False)
    role=db.Column(db.String(40),nullable=False)
    username=db.Column(db.String(80),nullable=False)
    password_hash=db.Column(db.Text,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)

class EntryAssignment(db.Model):
    __table_args__=(UniqueConstraint('employee_id',name='uq_entry_assignment_employee'),)
    id=db.Column(db.Integer,primary_key=True)
    employee_id=db.Column(db.Integer,db.ForeignKey('employee.id',ondelete='CASCADE'),nullable=False)
    supervisor_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False)
    is_active=db.Column(db.Boolean,default=True,nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    employee=db.relationship('Employee',foreign_keys=[employee_id])
    supervisor=db.relationship('User',foreign_keys=[supervisor_id])

class EntryAssignmentBranch(db.Model):
    __table_args__=(UniqueConstraint('entry_assignment_id','branch_id',name='uq_entry_assignment_branch'),)
    id=db.Column(db.Integer,primary_key=True)
    entry_assignment_id=db.Column(db.Integer,db.ForeignKey('entry_assignment.id',ondelete='CASCADE'),nullable=False)
    branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT'),nullable=False)
    assignment=db.relationship('EntryAssignment',foreign_keys=[entry_assignment_id])
    branch=db.relationship('Branch',foreign_keys=[branch_id])
class Governorate(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(150),unique=True,nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False)
class Branch(db.Model):
    id=db.Column(db.Integer,primary_key=True); governorate_id=db.Column(db.Integer,db.ForeignKey('governorate.id',ondelete='RESTRICT'),nullable=False); name=db.Column(db.String(200),nullable=False); code=db.Column(db.String(80)); is_active=db.Column(db.Boolean,default=True,nullable=False); governorate=db.relationship('Governorate')
class UserGovernorate(db.Model):
    __table_args__=(UniqueConstraint('user_id','governorate_id',name='uq_user_gov'),)
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False); governorate_id=db.Column(db.Integer,db.ForeignKey('governorate.id',ondelete='CASCADE'),nullable=False)
class UserBranch(db.Model):
    __table_args__=(UniqueConstraint('user_id','branch_id',name='uq_user_branch'),)
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False); branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='CASCADE'),nullable=False)
class SupervisorEntry(db.Model):
    __table_args__=(UniqueConstraint('entry_id','supervisor_id',name='uq_supervisor_entry'),)
    id=db.Column(db.Integer,primary_key=True)
    supervisor_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False)
    entry_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    supervisor=db.relationship('User',foreign_keys=[supervisor_id])
    entry=db.relationship('User',foreign_keys=[entry_id])
class ApprovalDelegation(db.Model):
    __table_args__=(UniqueConstraint('supervisor_id','governorate_id','starts_at','ends_at',name='uq_approval_delegation_window'),)
    id=db.Column(db.Integer,primary_key=True)
    supervisor_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False)
    delegate_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False)
    governorate_id=db.Column(db.Integer,db.ForeignKey('governorate.id',ondelete='RESTRICT'),nullable=False)
    starts_at=db.Column(db.Date,nullable=False)
    ends_at=db.Column(db.Date,nullable=False)
    is_active=db.Column(db.Boolean,default=True,nullable=False)
    created_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False)
    created_at=db.Column(db.DateTime,default=datetime.utcnow)
    revoked_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL'))
    revoked_at=db.Column(db.DateTime)
    revoke_reason=db.Column(db.Text)
    supervisor=db.relationship('User',foreign_keys=[supervisor_id])
    delegate=db.relationship('User',foreign_keys=[delegate_id])
    governorate=db.relationship('Governorate')
class Employee(db.Model):
    id=db.Column(db.Integer,primary_key=True); employee_code=db.Column(db.String(100),unique=True,nullable=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL'),unique=True,nullable=True); email=db.Column(db.String(254),unique=True,nullable=True); full_name=db.Column(db.String(250),nullable=False); branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT'),nullable=False); job_title=db.Column(db.String(200)); job_code=db.Column(db.String(100)); hire_date=db.Column(db.Date); company_phone=db.Column(db.String(80)); personal_phone=db.Column(db.String(80)); is_active=db.Column(db.Boolean,default=True,nullable=False); deleted_at=db.Column(db.DateTime); deleted_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); branch=db.relationship('Branch')
class Movement(db.Model):
    id=db.Column(db.Integer,primary_key=True); employee_id=db.Column(db.Integer,db.ForeignKey('employee.id',ondelete='RESTRICT'),nullable=False); movement_type=db.Column(db.String(30),nullable=False); leave_type=db.Column(db.String(100)); destination_branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT')); from_date=db.Column(db.Date); to_date=db.Column(db.Date); permission_date=db.Column(db.Date); status=db.Column(db.String(30),default='مسودة',nullable=False); notes=db.Column(db.Text); rejection_reason=db.Column(db.Text); is_active=db.Column(db.Boolean,default=True,nullable=False); deleted_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); deleted_at=db.Column(db.DateTime); created_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); modified_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); modified_at=db.Column(db.DateTime); reviewed_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); reviewed_at=db.Column(db.DateTime); approved_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); approved_at=db.Column(db.DateTime); approver_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); employee=db.relationship('Employee'); approver=db.relationship('User',foreign_keys=[approver_id]); destination=db.relationship('Branch',foreign_keys=[destination_branch_id]); assignment_state=db.Column(db.String(30),default='ساري',nullable=False); closed_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); closed_at=db.Column(db.DateTime); closure_reason=db.Column(db.Text); last_assignment_notice_at=db.Column(db.DateTime)
class MovementHistory(db.Model):
    id=db.Column(db.Integer,primary_key=True); movement_id=db.Column(db.Integer,db.ForeignKey('movement.id',ondelete='CASCADE'),nullable=False); from_status=db.Column(db.String(30)); to_status=db.Column(db.String(30)); action=db.Column(db.String(50),nullable=False); reason=db.Column(db.Text); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); created_at=db.Column(db.DateTime,default=datetime.utcnow); movement=db.relationship('Movement')
class Audit(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); action=db.Column(db.String(80),nullable=False); entity=db.Column(db.String(80)); entity_id=db.Column(db.Integer); details=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow)
class Lookup(db.Model):
    id=db.Column(db.Integer,primary_key=True); kind=db.Column(db.String(30),nullable=False); name=db.Column(db.String(120),nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False); __table_args__=(UniqueConstraint('kind','name',name='uq_lookup_kind_name'),)

def me(): return db.session.get(User,session.get('uid'))
def actual_roles(u=None):
    u=u or me()
    return {x.role for x in UserRole.query.filter_by(user_id=u.id).all()} if u else set()

def roles(u=None):
    # For the logged-in user, an optional session role is the active UI role.
    # For any other user, always return the real stored roles.
    u = u or me()
    if not u:
        return set()
    real = actual_roles(u)
    # session is only available while handling an HTTP request.
    # Startup/database migrations also call role helpers, so never touch
    # the Flask session outside a request context.
    if has_request_context() and u.id == session.get('uid'):
        active = session.get('active_role')
        if active in real:
            return {active}
        if active:
            session.pop('active_role', None)
    return real

def has_role(*r): return bool(roles() & set(r))
def req(f):
    @wraps(f)
    def w(*a,**k):
        u=me()
        if not u or not u.is_active: session.clear(); return redirect(url_for('login'))
        if u.must_change_password and request.endpoint!='change_password': return redirect(url_for('change_password'))
        return f(*a,**k)
    return w
def only(*rs):
    def d(f):
        @wraps(f)
        def w(*a,**k):
            if not me() or not has_role(*rs): abort(403)
            return f(*a,**k)
        return w
    return d
def log(a,e='',i=None,d=''):
    db.session.add(Audit(user_id=me().id if me() else None,action=a,entity=e,entity_id=i,details=d))
def csrf_token():
    if 'csrf' not in session: session['csrf']=secrets.token_urlsafe(24)
    return session['csrf']
def user_roles(u): return roles(u)
def assignment_state(m):
    if not m or m.movement_type!='انتداب': return None
    if m.assignment_state=='مغلق': return 'مغلق'
    if not m.to_date: return 'ساري'
    today=date.today()
    if m.to_date < today: return 'انتهت المدة'
    if m.to_date <= today + timedelta(days=ASSIGNMENT_ALERT_DAYS): return 'قرب الانتهاء'
    return 'ساري'

def supervisor_for_entry(u=None):
    u=u or me()
    if not u or 'المدخل الأول' not in actual_roles(u): return None
    # Explicit hierarchy link is preferred.
    link=SupervisorEntry.query.filter_by(entry_id=u.id).order_by(SupervisorEntry.id.asc()).first()
    if link and link.supervisor and link.supervisor.is_active and 'مشرف محافظة' in actual_roles(link.supervisor):
        return link.supervisor
    # Backward-compatible fallback: infer from the governorate when exactly one supervisor is responsible.
    gids_for_user={b.governorate_id for b in Branch.query.join(UserBranch,UserBranch.branch_id==Branch.id).filter(UserBranch.user_id==u.id).all()}
    for gid in gids_for_user:
        suids=[x.user_id for x in UserGovernorate.query.filter_by(governorate_id=gid).all()]
        sups=[db.session.get(User,uid) for uid in suids]
        sups=[x for x in sups if x and x.is_active and 'مشرف محافظة' in actual_roles(x)]
        if len(sups)==1: return sups[0]
    return None

def entries_for_supervisor(supervisor, gid=None):
    if not supervisor: return []
    q=SupervisorEntry.query.filter_by(supervisor_id=supervisor.id)
    links=q.order_by(SupervisorEntry.id.asc()).all()
    out=[]
    for link in links:
        u=link.entry
        if not u or not u.is_active or 'المدخل الأول' not in actual_roles(u): continue
        if gid:
            ub=[x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()]
            if not any(b.governorate_id==gid for b in Branch.query.filter(Branch.id.in_(ub)).all()): continue
        out.append(u)
    return out

def approvers_for_employee(e):
    if not e or not e.branch: return []
    gid=e.branch.governorate_id
    suids={x.user_id for x in UserGovernorate.query.filter_by(governorate_id=gid).all()}
    users=User.query.filter(User.is_active==True).order_by(User.full_name).all()
    out=[]
    for u in users:
        rs=roles(u)
        if 'مسؤول التطبيق' in rs:
            out.append(u)
        elif 'مشرف محافظة' in rs and u.id in suids and can_for_user(u,'review_movements'):
            out.append(u)
    return out

def active_delegation_for(supervisor, gid, on_date=None):
    if not supervisor or not gid:
        return None
    on_date=on_date or date.today()
    return (ApprovalDelegation.query.filter_by(supervisor_id=supervisor.id, governorate_id=gid, is_active=True)
            .filter(ApprovalDelegation.starts_at <= on_date, ApprovalDelegation.ends_at >= on_date)
            .order_by(ApprovalDelegation.starts_at.desc(), ApprovalDelegation.id.desc()).first())

def supervisor_for_governorate(gid):
    if not gid: return None
    suids={x.user_id for x in UserGovernorate.query.filter_by(governorate_id=gid).all()}
    for u in User.query.filter(User.is_active==True).order_by(User.full_name,User.id).all():
        if u.id in suids and 'مشرف محافظة' in actual_roles(u) and can_for_user(u,'review_movements'):
            return u
    return None

def auto_approver_for_employee(e, creator=None):
    if not e or not e.branch: return None
    creator=creator or me()
    gid=e.branch.governorate_id
    # A governorate supervisor creating a movement is the approver, unless delegation is active.
    if creator and 'مشرف محافظة' in actual_roles(creator) and gid in user_gov_ids(creator):
        supervisor=creator
    elif creator and 'مسؤول التطبيق' in actual_roles(creator) and session.get('active_role')=='مشرف محافظة' and gid in user_gov_ids(creator):
        supervisor=creator
    else:
        supervisor=supervisor_for_governorate(gid)
    if not supervisor: return None
    delegation=active_delegation_for(supervisor,gid)
    if delegation and delegation.delegate and delegation.delegate.is_active and can_for_user(delegation.delegate,'review_movements') and delegation.delegate.id!=creator.id:
        return delegation.delegate
    return supervisor

def delegation_allowed_for_user(u, gid):
    return bool(u and gid and 'مشرف محافظة' in roles(u) and gid in user_gov_ids(u) and can_for_user(u,'review_movements'))

def can_for_user(u, permission):
    return bool(u and u.is_active and ('مسؤول التطبيق' in roles(u) or permission in user_permissions(u)))

def assignment_supervisor(m):
    if not m or not m.employee or not m.employee.branch: return None
    gid=m.employee.branch.governorate_id
    # The designated approver is the responsible person for this movement.
    if m.approver_id:
        designated=db.session.get(User,m.approver_id)
        if designated and designated.is_active: return designated
    # Prefer the supervisor who approved the movement when that user is a governorate supervisor.
    if m.approved_by:
        approved=db.session.get(User,m.approved_by)
        if approved and approved.is_active and 'مشرف محافظة' in roles(approved) and gid in user_gov_ids(approved):
            return approved
    suids=[x.user_id for x in UserGovernorate.query.filter_by(governorate_id=gid).all()]
    for uid in suids:
        u=db.session.get(User,uid)
        if u and u.is_active and 'مشرف محافظة' in roles(u): return u
    return None

def assignment_followups():
    today=date.today(); limit=today+timedelta(days=ASSIGNMENT_ALERT_DAYS)
    bs=bids()
    if not bs: return []
    return (Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True,Movement.movement_type=='انتداب',Movement.assignment_state!='مغلق',Movement.to_date!=None,Movement.to_date<=limit).order_by(Movement.to_date.asc()).all())

def user_permissions(u):
    explicit={x.permission for x in UserPermission.query.filter_by(user_id=u.id).all()}
    selected = None
    if u and has_request_context() and u.id == session.get('uid'):
        selected = session.get('active_role')
    effective = {selected} if selected else actual_roles(u)
    if selected:
        # الصلاحيات محفوظة للحساب ويمكن لمسؤول التطبيق زيادتها أو تقليلها؛ اختيار الدور يغيّر واجهة الدور لا يلغي الصلاحيات المخصصة.
        if explicit: return explicit
        return set(ROLE_DEFAULT_PERMISSIONS.get(selected, set()))
    if explicit: return explicit
    out=set()
    for r in effective: out |= ROLE_DEFAULT_PERMISSIONS.get(r,set())
    return out
def can(permission):
    u=me()
    return bool(u and ('مسؤول التطبيق' in roles(u) or permission in user_permissions(u)))
def user_gov_ids(u): return {x.governorate_id for x in UserGovernorate.query.filter_by(user_id=u.id).all()}
def user_branch_ids(u): return {x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()}
@app.context_processor
def inject_context():
    u=me()
    real_roles=actual_roles(u)
    active_role=session.get('active_role') if u else None
    if active_role not in real_roles:
        active_role=None
    return {'me':u,'roles':roles(),'real_roles':real_roles,'active_role':active_role,'csrf':csrf_token(),'user_roles':user_roles,'user_permissions':user_permissions,'can':can,'has_role':has_role,'PERMISSIONS':PERMISSIONS,'user_gov_ids':user_gov_ids,'user_branch_ids':user_branch_ids,'assignment_state':assignment_state,'assignment_supervisor':assignment_supervisor,'supervisor_for_entry':supervisor_for_entry,'entries_for_supervisor':entries_for_supervisor,'branch_entry':branch_entry,'auto_approver_for_employee':auto_approver_for_employee,'can_manage_employee':can_manage_employee,'ASSIGNMENT_STATES':ASSIGNMENT_STATES,'ASSIGNMENT_ALERT_DAYS':ASSIGNMENT_ALERT_DAYS}

@app.after_request
def security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options','nosniff')
    resp.headers.setdefault('X-Frame-Options','SAMEORIGIN' if request.path.startswith('/assistant') else 'DENY')
    resp.headers.setdefault('Referrer-Policy','strict-origin-when-cross-origin')
    resp.headers.setdefault('Permissions-Policy','camera=(), microphone=(), geolocation=()')
    if request.is_secure:
        resp.headers.setdefault('Strict-Transport-Security','max-age=31536000; includeSubDomains')
    return resp

def active_movement_types():
    vals=[x.name for x in Lookup.query.filter_by(kind='movement',is_active=True).order_by(Lookup.name).all()]
    return vals or MOVEMENT_TYPES

def active_leave_types():
    vals=[x.name for x in Lookup.query.filter_by(kind='leave',is_active=True).order_by(Lookup.name).all()]
    return vals or LEAVE_TYPES

def valid_email(v):
    import re
    v=(v or '').strip()
    return bool(re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', v))

def valid_password(p):
    return len(p)>=8 and any(c.isalpha() for c in p) and any(c.isdigit() for c in p)

def record_movement_history(m, old_status, new_status, action, reason=''):
    db.session.add(MovementHistory(movement_id=m.id,from_status=old_status,to_status=new_status,action=action,reason=reason,user_id=me().id if me() else None))

def parse_date_value(v):
    return parse_date(v) if v else None

def movement_overlaps(employee_id, mt, fd, td, pd, exclude_id=None):
    q=Movement.query.filter(Movement.employee_id==employee_id,Movement.is_active==True,Movement.status!='مرفوضة')
    if exclude_id: q=q.filter(Movement.id!=exclude_id)
    start=parse_date_value(fd); end=parse_date_value(td); day=parse_date_value(pd)
    for x in q.all():
        if mt=='إذن':
            if day and x.movement_type=='إذن' and x.permission_date==day: return 'يوجد إذن آخر للموظف في نفس التاريخ.'
            if day and x.from_date and x.to_date and x.from_date<=day<=x.to_date: return 'تاريخ الإذن يتعارض مع حركة أخرى للموظف.'
        elif start and end:
            if x.from_date and x.to_date and start<=x.to_date and end>=x.from_date: return 'فترة الحركة تتعارض مع حركة أخرى للموظف.'
            if x.movement_type=='إذن' and x.permission_date and start<=x.permission_date<=end: return 'فترة الحركة تتعارض مع إذن للموظف.'
    return None

def validate_movement_fields(mt, leave_type, dest, fd, td, pd):
    if mt not in active_movement_types(): return 'نوع الحركة غير صحيح.'
    if mt=='إجازة':
        if not leave_type or leave_type not in active_leave_types(): return 'نوع الإجازة غير صحيح أو غير محدد.'
        if not fd or not td: return 'حدد تاريخ البداية والنهاية.'
    elif mt=='انتداب':
        if not dest or not branch_ok(dest): return 'فرع الانتداب غير مسموح.'
        if not fd or not td: return 'حدد تاريخ البداية والنهاية.'
    elif mt=='إذن':
        if not pd: return 'حدد تاريخ الإذن.'
    if fd and td and fd>td: return 'من لا يجوز أن يكون بعد إلى.'
    return None

@app.before_request
def csrf_check():
    if request.method=='POST' and request.endpoint not in ('login',):
        token=request.form.get('_csrf')
        if not token or token!=session.get('csrf'): abort(400,'CSRF token invalid')

def gids():
    u=me()
    if not u: return []
    rs=roles(u)
    if 'مسؤول التطبيق' in rs: return [g.id for g in Governorate.query.filter_by(is_active=True)]
    if 'Manager Application Support' in rs:
        selected=session.get('manager_governorate_id')
        if selected:
            g=Governorate.query.filter_by(id=int(selected),is_active=True).first()
            return [g.id] if g else []
        return []
    return [x.governorate_id for x in UserGovernorate.query.filter_by(user_id=u.id).join(Governorate).filter(Governorate.is_active==True)]
def bids():
    u=me()
    if not u: return []
    rs=roles(u)
    if 'مسؤول التطبيق' in rs: return [b.id for b in Branch.query.filter_by(is_active=True)]
    if 'Manager Application Support' in rs:
        gids_now=gids()
        return [b.id for b in Branch.query.filter(Branch.governorate_id.in_(gids_now),Branch.is_active==True)] if gids_now else []
    if 'مشرف محافظة' in rs: return [b.id for b in Branch.query.filter(Branch.governorate_id.in_(gids()),Branch.is_active==True)]
    return [x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).join(Branch).filter(Branch.is_active==True)]
def branch_ok(i):
    try: return i is not None and int(i) in set(bids())
    except (TypeError,ValueError): return False
def parse_date(v):
    if not v: return None
    try: return datetime.strptime(v,'%Y-%m-%d').date()
    except ValueError: raise ValueError('التاريخ غير صحيح')

def allowed_create_user(role):
    rs=roles()
    if 'مسؤول التطبيق' in rs: return role in ROLES
    return role=='المدخل الأول' and 'مشرف محافظة' in rs

def allowed_target_user(target):
    current=me(); rs=roles(current)
    if not target or not target.is_active: return False
    if 'مسؤول التطبيق' in rs: return True
    if 'مشرف محافظة' not in rs or 'المدخل الأول' not in roles(target): return False
    target_govs={b.governorate_id for b in Branch.query.join(UserBranch,UserBranch.branch_id==Branch.id).filter(UserBranch.user_id==target.id)}
    return bool(set(gids()) & target_govs)

def can_manage_employee(e):
    return bool(e and branch_ok(e.branch_id) and can('manage_employees'))

def can_manage_movement(m=None):
    rs=roles()
    if 'مسؤول التطبيق' in rs: return True
    if 'Manager Application Support' in rs and can('manage_movements'): return True
    if 'مشرف محافظة' in rs and can('manage_movements'): return True
    if 'المدخل الأول' not in rs: return False
    # First-level users manage movements within their assigned branches.
    # They are not limited to movements they personally created.
    return bool(m and branch_ok(m.employee.branch_id)) if m else True

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(username=request.form.get('username','').strip()).first()
        if not u or not u.is_active or not check_password_hash(u.password_hash,request.form.get('password','')): flash('بيانات الدخول غير صحيحة.'); return render_template('login.html')
        session.clear(); session['uid']=u.id; session['csrf']=secrets.token_urlsafe(24); session.pop('active_role', None); u.last_login=datetime.utcnow(); log('LOGIN','User',u.id); db.session.commit(); return redirect('/')
    return render_template('login.html')
@app.get('/logout')
def logout(): session.clear(); return redirect('/login')

@app.post('/switch-role')
@req
def switch_role():
    u = me()
    real_roles = actual_roles(u)
    selected = request.form.get('active_role', '').strip()
    if len(real_roles) <= 1:
        session.pop('active_role', None)
    elif selected in real_roles:
        old_role = session.get('active_role')
        session['active_role'] = selected
        if old_role != selected:
            log('SWITCH_ROLE', 'User', u.id, f'{old_role or "الدور التلقائي"} -> {selected}')
            db.session.commit()
    else:
        flash('الدور المختار غير متاح لهذا الحساب.')
    return redirect(request.form.get('next') or url_for('home'))
@app.route('/change-password',methods=['GET','POST'])
@req
def change_password():
    u=me()
    if request.method=='POST':
        old=request.form.get('old_password',''); new=request.form.get('new_password',''); confirm=request.form.get('confirm_password','')
        if not check_password_hash(u.password_hash,old): flash('كلمة المرور الحالية غير صحيحة.')
        elif not valid_password(new): flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حروف وأرقام.')
        elif new!=confirm: flash('تأكيد كلمة المرور غير مطابق.')
        else: u.password_hash=generate_password_hash(new); u.must_change_password=False; sync_role_accounts(u); log('PASSWORD_CHANGE','User',u.id); db.session.commit(); flash('تم تغيير كلمة المرور بنجاح.'); return redirect('/')
    return render_template('change_password.html')
def current_employee_status_rows(branch_ids, today):
    """Return only employees with a currently active leave or assignment."""
    if not branch_ids:
        return []
    employees=(Employee.query.filter(Employee.branch_id.in_(branch_ids),Employee.is_active==True)
               .order_by(Employee.full_name.asc()).all())
    rows=[]
    for e in employees:
        moves=(Movement.query.filter_by(employee_id=e.id,is_active=True)
               .order_by(Movement.created_at.desc(),Movement.id.desc()).all())
        current=None
        for m in moves:
            if m.movement_type in ('إجازة','انتداب') and m.from_date and m.to_date and m.from_date <= today <= m.to_date:
                current=m
                break
        # الصفحة «حالة الموظفين الآن» تعرض فقط الإجازات والانتدابات السارية.
        if not current:
            continue
        if current.movement_type=='انتداب':
            state='انتداب ساري'
            place=current.destination.name if current.destination else 'جهة الانتداب غير محددة'
            until=current.to_date
            detail='من {} إلى {}'.format(current.from_date.strftime('%d/%m/%Y'),current.to_date.strftime('%d/%m/%Y'))
        else:
            state='إجازة مستمرة'
            place=current.leave_type or 'إجازة'
            until=current.to_date
            detail='من {} إلى {}'.format(current.from_date.strftime('%d/%m/%Y'),current.to_date.strftime('%d/%m/%Y'))
        remaining=(until-today).days if until else 0
        rows.append({'employee':e,'state':state,'place':place,'until':until,'detail':detail,
                     'remaining':remaining,'movement':current,
                     'ending_notice':bool(until and until <= today + timedelta(days=1)),
                     'from_date':current.from_date,'to_date':current.to_date})
    rows.sort(key=lambda r: (r['until'] or date.max, r['employee'].full_name))
    return rows

@app.get('/')
@req
def home():
    current_user=me()
    effective=roles(current_user)
    is_manager_support='Manager Application Support' in effective
    manager_gov_param=request.args.get('manager_governorate_id','').strip()
    if is_manager_support:
        if manager_gov_param.isdigit() and Governorate.query.filter_by(id=int(manager_gov_param),is_active=True).first():
            session['manager_governorate_id']=int(manager_gov_param)
        elif 'manager_governorate_id' not in session:
            session['manager_governorate_id']=None
        selected_manager_gov=session.get('manager_governorate_id')
        if selected_manager_gov:
            bs={b.id for b in Branch.query.filter_by(governorate_id=int(selected_manager_gov),is_active=True).all()}
        else:
            bs=set()
    else:
        selected_manager_gov=None
        bs=set(bids())
    today=date.today()
    tomorrow=today + timedelta(days=1)
    # بحث الموظف من لوحة «حركات الموظفين» يعرض بطاقة الموظف مباشرة داخل الصفحة الرئيسية.
    movement_employee_id=request.args.get('employee_id','').strip()
    movement_employee=None
    movement_employee_moves=[]
    movement_employee_last={}
    if movement_employee_id.isdigit():
        candidate=db.session.get(Employee,int(movement_employee_id))
        if candidate and candidate.is_active and branch_ok(candidate.branch_id):
            movement_employee=candidate
            movement_employee_moves=(Movement.query.filter_by(employee_id=candidate.id,is_active=True)
                                     .order_by(Movement.from_date.desc().nullslast(),Movement.permission_date.desc().nullslast(),Movement.id.desc()).all())
            movement_employee_last={k:next((m for m in movement_employee_moves if m.movement_type==k),None) for k in MOVEMENT_TYPES}
    pending=[]
    ending=[]
    approved_count=0
    current_status_rows=[]

    # Governorates visible to the current effective role.
    visible_govs=(Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True)
                  .order_by(Governorate.name.asc()).all() if gids() else [])

    # المدخل الأول هنا بند تنظيمي فقط: لا يحتاج حساب دخول.
    entry_rows=[]
    if 'مشرف محافظة' in effective or 'مسؤول التطبيق' in effective or is_manager_support:
        if is_manager_support:
            supervisors = [u for u in User.query.filter_by(is_active=True).order_by(User.full_name).all()
                           if 'مشرف محافظة' in actual_roles(u) and any(x.governorate_id in ({int(selected_manager_gov)} if selected_manager_gov else set()) for x in UserGovernorate.query.filter_by(user_id=u.id).all())]
        else:
            supervisors = [me()] if ('مشرف محافظة' in effective and 'مسؤول التطبيق' not in effective) else [u for u in User.query.filter_by(is_active=True).order_by(User.full_name).all() if 'مشرف محافظة' in actual_roles(u)]
        seen=set()
        for sup in supervisors:
            for a,scoped_all in organizational_entries_for_supervisor(sup):
                scoped=[b for b in scoped_all if b.id in bs]
                if not scoped or a.id in seen: continue
                seen.add(a.id)
                branch_groups=[]
                for b in scoped:
                    emps=Employee.query.filter(Employee.branch_id==b.id,Employee.is_active==True).order_by(Employee.full_name.asc()).all()
                    branch_groups.append({'branch':b,'employees':emps})
                gov_ids_for_entry={x['branch'].governorate_id for x in branch_groups}
                gov_names=[gobj.name for gobj in Governorate.query.filter(Governorate.id.in_(gov_ids_for_entry),Governorate.is_active==True).order_by(Governorate.name.asc()).all()] if gov_ids_for_entry else []
                # بيانات أزرار إدارة الفروع والاستبدال داخل الصفحة الرئيسية.
                allowed_branch_objs=Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True).order_by(Branch.name.asc()).all() if bs else []
                occupied_branch_ids=set()
                for oa in EntryAssignment.query.filter(EntryAssignment.is_active==True,EntryAssignment.id!=a.id).all():
                    occupied_branch_ids.update(x.branch_id for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=oa.id).all())
                assignment_branch_ids={x.branch_id for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).all()}
                available_entry_branches=[b for b in allowed_branch_objs if b.id not in occupied_branch_ids or b.id in assignment_branch_ids]
                entry_employee_ids={x.employee_id for x in EntryAssignment.query.filter_by(is_active=True).all()}
                replace_targets=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)).order_by(Employee.full_name.asc()).all() if bs else []
                replace_targets=[x for x in replace_targets if x.id not in entry_employee_ids and x.id!=a.employee_id]
                entry_rows.append({'assignment':a,'employee':a.employee,'branches':branch_groups,'governorates':gov_names,'supervisor':sup,'available_branches':available_entry_branches,'assignment_branch_ids':assignment_branch_ids,'replace_targets':replace_targets})
        # Legacy accounts remain visible only as compatibility records. New organizational entries never create them.
    elif 'المدخل الأول' in effective:
        # Legacy account compatibility; not used for new assignments.
        u=me(); scoped=[b for b in Branch.query.join(UserBranch,UserBranch.branch_id==Branch.id).filter(UserBranch.user_id==u.id,Branch.is_active==True).order_by(Branch.name).all() if b.id in bs]
        if scoped:
            groups=[{'branch':b,'employees':Employee.query.filter(Employee.branch_id==b.id,Employee.is_active==True).order_by(Employee.full_name).all()} for b in scoped]
            entry_rows=[{'assignment':None,'employee':Employee.query.filter_by(user_id=u.id).first(),'branches':groups,'governorates':[],'supervisor':supervisor_for_entry(u)}]

    # بيانات إضافة المدخل الأول التنظيمي في الصفحة الرئيسية يجب أن تُبنى داخل
    # نفس نطاق المستخدم؛ لا تعتمد على متغيرات غير مُمررة للقالب.
    available_entry_employees=[]
    entry_supervisors=[]
    available_entry_branches=[]
    if 'مسؤول التطبيق' in effective or 'مشرف محافظة' in effective or is_manager_support:
        allowed_branch_set=set(bs)
        if allowed_branch_set:
            candidates=Employee.query.filter(
                Employee.is_active==True,
                Employee.branch_id.in_(allowed_branch_set)
            ).order_by(Employee.full_name.asc()).all()
            available_entry_employees=[e for e in candidates if not entry_role_exists(e)]
            occupied_entry_branch_ids=set()
            for oa in EntryAssignment.query.filter_by(is_active=True).all():
                occupied_entry_branch_ids.update(x.branch_id for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=oa.id).all())
            available_entry_branches=[b for b in Branch.query.filter(Branch.id.in_(allowed_branch_set),Branch.is_active==True).order_by(Branch.name.asc()).all() if b.id not in occupied_entry_branch_ids]
        if 'مسؤول التطبيق' in effective:
            entry_supervisors=[u for u in User.query.filter_by(is_active=True).order_by(User.full_name.asc()).all()
                               if 'مشرف محافظة' in actual_roles(u)]
        elif is_manager_support:
            entry_supervisors=supervisors
        else:
            entry_supervisors=[me()]

    if bs:
        # الحركات أصبحت معلومات تشغيلية مباشرة وليست دورة اعتماد.
        if has_role('مشرف محافظة','مسؤول التطبيق','المدخل الأول','Manager Application Support'):
            current_status_rows=current_employee_status_rows(bs,today)
            # ending_notice is calculated while building the current-status rows.
        # تبقى بيانات الاعتماد القديمة قابلة للعرض في السجلات القديمة، لكن لا تُستخدم
        # لتحديد حالة الموظف الحالية.
        ending=[]

    return render_template(
        'home.html',
        g=len(visible_govs),
        b=len(bs),
        e=(Employee.query.filter(Employee.branch_id.in_(bs),Employee.is_active==True).count() if bs else 0),
        visible_govs=visible_govs,
        entry_rows=entry_rows,
        pending=pending,
        ending=ending,
        approved_count=approved_count,
        current_status_rows=current_status_rows,
        available_entry_employees=available_entry_employees,
        available_entry_branches=available_entry_branches,
        entry_supervisors=entry_supervisors,
        today=today,
        tomorrow=tomorrow,
        is_admin=has_role('مسؤول التطبيق'),
        is_manager_support=is_manager_support,
        manager_governorates=Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all() if is_manager_support else [],
        selected_manager_gov=selected_manager_gov,
        movement_search_governorates=Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all() if (is_manager_support or 'مشرف محافظة' in effective or 'مسؤول التطبيق' in effective) else visible_govs,
        movement_search_branches=Branch.query.filter_by(is_active=True).order_by(Branch.name.asc()).all(),
        movement_search_employees=Employee.query.filter_by(is_active=True).order_by(Employee.full_name.asc()).all(),
        movement_employee=movement_employee,
        movement_employee_moves=movement_employee_moves,
        movement_employee_last=movement_employee_last,
        movement_employee_id=(int(movement_employee_id) if movement_employee_id.isdigit() else None)
    )

@app.get('/api/entry-ids/<int:gid>')
@req
def entry_ids_for_governorate(gid):
    # لا نكشف أي مدخلين خارج نطاق المستخدم الحالي.
    if gid not in set(gids()): abort(403)
    bids_g={b.id for b in Branch.query.filter_by(governorate_id=gid,is_active=True).all()}
    if not bids_g: return {'entry_ids': []}
    ids={x.user_id for x in UserBranch.query.filter(UserBranch.branch_id.in_(bids_g)).all()}
    return {'entry_ids': sorted(ids)}

def organizational_entries_for_supervisor(supervisor, gid=None):
    if not supervisor: return []
    q=EntryAssignment.query.filter_by(supervisor_id=supervisor.id,is_active=True)
    out=[]
    for a in q.order_by(EntryAssignment.id.asc()).all():
        if not a.employee or not a.employee.is_active: continue
        branch_ids={x.branch_id for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).all()}
        branches=Branch.query.filter(Branch.id.in_(branch_ids),Branch.is_active==True).order_by(Branch.name).all() if branch_ids else []
        if gid: branches=[b for b in branches if b.governorate_id==gid]
        if branches or not gid: out.append((a,branches))
    return out

def organizational_entry_for_employee(e):
    if not e: return None
    return EntryAssignment.query.filter_by(employee_id=e.id,is_active=True).first()

def entry_role_exists(e):
    return bool(organizational_entry_for_employee(e) or (e.user_id and 'المدخل الأول' in actual_roles(db.session.get(User,e.user_id))))

def sync_role_accounts(u):
    if not u: return
    real=actual_roles(u)
    existing={x.role:x for x in RoleAccount.query.filter_by(user_id=u.id).all()}
    for role in list(existing):
        if role not in real:
            db.session.delete(existing[role])
    for role in real:
        x=existing.get(role)
        if not x:
            db.session.add(RoleAccount(user_id=u.id,role=role,username=u.username,password_hash=u.password_hash))
        else:
            x.username=u.username; x.password_hash=u.password_hash

def branch_entry(b):
    # التنظيم الجديد أولًا، ثم روابط الحسابات القديمة للتوافق.
    link=EntryAssignmentBranch.query.join(EntryAssignment).filter(EntryAssignmentBranch.branch_id==b.id,EntryAssignment.is_active==True).first()
    if link and link.assignment and link.assignment.employee: return link.assignment.employee
    links=UserBranch.query.filter_by(branch_id=b.id).all()
    for link in links:
        u=db.session.get(User,link.user_id)
        if u and u.is_active and 'المدخل الأول' in actual_roles(u): return u
    return None

@app.get('/structure')
@req
def structure():
    # الإدارة متاحة فقط لمسؤول التطبيق ولمشرف المحافظة.
    current=me()
    # صفحة الإدارة تلتزم بالدور النشط؛ الحساب متعدد الأدوار يبدّل الدور من رأس التطبيق.
    real=actual_roles(current)
    effective=roles(current)
    is_admin = 'مسؤول التطبيق' in effective
    is_supervisor = 'مشرف محافظة' in effective
    is_manager_support = 'Manager Application Support' in effective
    is_entry = 'المدخل الأول' in effective
    if not is_admin and not is_supervisor and not is_manager_support:
        abort(403)
    if is_supervisor and not is_admin:
        session['active_role']='مشرف محافظة'

    # مسؤول التطبيق يرى كل المحافظات، والمشرف يرى محافظاته فقط.
    selected_gov=request.args.get('governorate_id','').strip()
    if is_admin:
        all_govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if selected_gov.isdigit() and any(g.id==int(selected_gov) for g in all_govs):
            govs=[db.session.get(Governorate,int(selected_gov))]
        else:
            # لا نبني شجرة المحافظات كاملة قبل الاختيار؛ هذا يمنع أخطاء البيانات
            # في أي فرع غير مختار ويجعل صفحة الإدارة أخف وأوضح.
            govs=[]
            selected_gov=''
    elif is_manager_support:
        allowed_govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if selected_gov.isdigit() and any(g.id==int(selected_gov) for g in allowed_govs):
            govs=[db.session.get(Governorate,int(selected_gov))]
        else:
            govs=[]
            selected_gov=''
    elif is_supervisor:
        supervisor_gids = list(user_gov_ids(current))
        allowed_govs=Governorate.query.filter(Governorate.id.in_(supervisor_gids),Governorate.is_active==True).order_by(Governorate.name).all() if supervisor_gids else []
        if selected_gov.isdigit() and any(g.id==int(selected_gov) for g in allowed_govs):
            govs=[db.session.get(Governorate,int(selected_gov))]
        elif len(allowed_govs)==1:
            # فتح المحافظة المسجلة للمشرف تلقائيًا إذا كانت له محافظة واحدة.
            govs=[allowed_govs[0]]
            selected_gov=str(allowed_govs[0].id)
        else:
            govs=[]
            selected_gov=''
    else:
        entry_branch_ids=user_branch_ids(current)
        entry_gids={b.governorate_id for b in Branch.query.filter(Branch.id.in_(entry_branch_ids),Branch.is_active==True).all()} if entry_branch_ids else set()
        govs=Governorate.query.filter(Governorate.id.in_(entry_gids),Governorate.is_active==True).order_by(Governorate.name).all() if entry_gids else []
        selected_gov=''

    tree=[]
    # لا نعرض تفاصيل الهيكل قبل اختيار المحافظة صراحةً.
    for g in govs:
        bs=Branch.query.filter_by(governorate_id=g.id,is_active=True).order_by(Branch.name).all()
        supervisors=[]
        suids=[x.user_id for x in UserGovernorate.query.filter_by(governorate_id=g.id).all()]
        for u in User.query.filter(User.id.in_(suids),User.is_active==True).order_by(User.full_name).all() if suids else []:
            if 'مشرف محافظة' not in actual_roles(u): continue
            if is_supervisor and not is_manager_support and u.id != current.id: continue
            supervisors.append(u)
        entries=[]
        # التنظيم الجديد: المدخل الأول موظف/تصنيف إداري فقط، بلا حساب دخول.
        org_entries=[]
        if is_admin:
            org_entries=[(a,[b for b in Branch.query.join(EntryAssignmentBranch,EntryAssignmentBranch.branch_id==Branch.id).filter(EntryAssignmentBranch.entry_assignment_id==a.id,Branch.is_active==True).all()],a.supervisor) for a in EntryAssignment.query.filter_by(is_active=True).all() if a.employee and a.employee.is_active]
        elif is_manager_support:
            org_entries=[]
            for su in supervisors:
                org_entries.extend([(a,bs2,a.supervisor) for a,bs2 in organizational_entries_for_supervisor(su,g.id)])
        elif is_supervisor:
            org_entries=[(a,bs2,a.supervisor) for a,bs2 in organizational_entries_for_supervisor(current,g.id)]
        for a,scoped,sup in org_entries:
            if not scoped and g.id: continue
            scoped=[b for b in scoped if b.governorate_id==g.id]
            if not scoped: continue
            for b in scoped:
                b.employee_items=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
            entries.append((a.employee,scoped,sup,a,None))
        # Legacy account entries kept only for backward compatibility.
        candidate_entries = []
        if is_admin:
            candidate_entries = User.query.filter_by(is_active=True).order_by(User.full_name).all()
        elif is_manager_support:
            candidate_entries=[]
            for su in supervisors:
                candidate_entries.extend(entries_for_supervisor(su, g.id))
        elif is_supervisor:
            candidate_entries = entries_for_supervisor(current, g.id)
        else:
            candidate_entries = [current]
        for u in candidate_entries:
            if 'المدخل الأول' not in actual_roles(u): continue
            ubids={x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()}
            scoped=[b for b in bs if b.id in ubids]
            for b in scoped:
                b.employee_items=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
            sup_link=SupervisorEntry.query.filter_by(entry_id=u.id).order_by(SupervisorEntry.id.asc()).first()
            sup=sup_link.supervisor if sup_link else None
            if is_supervisor and sup and sup.id != current.id: continue
            if is_entry and u.id != current.id: continue
            if not sup and len({b.governorate_id for b in scoped})==1: sup=supervisor_for_governorate(g.id)
            entries.append((u,scoped,sup,None,Employee.query.filter_by(user_id=u.id).first()))
        counts={b.id:Employee.query.filter_by(branch_id=b.id,is_active=True).count() for b in bs}
        for b in bs:
            if not hasattr(b,'employee_items'):
                b.employee_items=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
        tree.append((g,bs,supervisors,entries,counts))
    govs_all=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if (is_admin or is_manager_support) else govs
    admin_stats = None
    if is_admin:
        admin_stats = {
            'governorates': Governorate.query.filter_by(is_active=True).count(),
            'branches': Branch.query.filter_by(is_active=True).count(),
            'employees': Employee.query.filter_by(is_active=True).count(),
            'users': User.query.filter_by(is_active=True).count(),
            'supervisors': sum(1 for u in User.query.filter_by(is_active=True).all() if 'مشرف محافظة' in actual_roles(u)),
            'entries': sum(1 for u in User.query.filter_by(is_active=True).all() if 'المدخل الأول' in actual_roles(u)),
            'movements': Movement.query.filter_by(is_active=True).count(),
        }
    available_entry_employees=[]
    if is_admin or is_supervisor or is_manager_support:
        allowed_branch_set=set(bids())
        available_entry_employees=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(allowed_branch_set)).order_by(Employee.full_name).all() if allowed_branch_set else []
        available_entry_employees=[e for e in available_entry_employees if not entry_role_exists(e)]
    entry_supervisors=[u for u in User.query.filter_by(is_active=True).order_by(User.full_name).all() if 'مشرف محافظة' in actual_roles(u)]
    return render_template(
        'structure.html',
        tree=tree,
        is_admin=is_admin,
        is_supervisor=is_supervisor,
        is_manager_support=is_manager_support,
        is_entry=is_entry,
        govs_all=govs_all,
        selected_governorate=selected_gov,
        admin_stats=admin_stats,
        available_entry_employees=available_entry_employees, entry_supervisors=entry_supervisors
    )


@app.post('/entry-role/<int:employee_id>/branches')
@req
def update_organizational_entry_branches(employee_id):
    if not has_role('مسؤول التطبيق','مشرف محافظة','Manager Application Support'): abort(403)
    e=db.session.get(Employee,employee_id)
    a=EntryAssignment.query.filter_by(employee_id=employee_id,is_active=True).first() if e else None
    if not e or not a or not e.is_active: abort(404)
    if 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles() and a.supervisor_id != me().id: abort(403)
    allowed=set(bids())
    chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & allowed
    if not chosen:
        flash('يجب اختيار فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
        return redirect('/#entry-directory')
    occupied={}
    for oa in EntryAssignment.query.filter(EntryAssignment.is_active==True,EntryAssignment.id!=a.id).all():
        for link in EntryAssignmentBranch.query.filter_by(entry_assignment_id=oa.id).all():
            occupied[link.branch_id]=oa.employee_id
    conflict=[bid for bid in chosen if bid in occupied]
    if conflict:
        flash('يوجد فرع من الفروع المختارة مسند بالفعل إلى مدخل أول آخر.')
        return redirect('/#entry-directory')
    EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).delete()
    for bid in sorted(chosen): db.session.add(EntryAssignmentBranch(entry_assignment_id=a.id,branch_id=bid))
    log('ASSIGN','Employee',employee_id,'تحديث فروع مسؤولية المدخل الأول من الصفحة الرئيسية')
    db.session.commit()
    flash('تم تحديث فروع مسؤولية المدخل الأول بنجاح.')
    return redirect('/#entry-directory')

@app.post('/entry-role/<int:employee_id>/replace')
@req
def replace_organizational_entry_from_home(employee_id):
    if not has_role('مسؤول التطبيق','مشرف محافظة','Manager Application Support'): abort(403)
    old=db.session.get(Employee,employee_id)
    a=EntryAssignment.query.filter_by(employee_id=employee_id,is_active=True).first() if old else None
    new_id=request.form.get('new_entry_employee_id','').strip()
    new=db.session.get(Employee,int(new_id)) if new_id.isdigit() else None
    if not old or not a or not old.is_active:
        flash('الموظف المحدد ليس مدخلًا أول تنظيميًا حاليًا.')
        return redirect('/#entry-directory')
    if 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles() and a.supervisor_id != me().id: abort(403)
    if not new or not new.is_active or new.id==old.id or not branch_ok(new.branch_id):
        flash('اختر موظفًا بديلًا نشطًا داخل نطاقك.')
        return redirect('/#entry-directory')
    if EntryAssignment.query.filter_by(employee_id=new.id,is_active=True).first():
        flash('الموظف البديل لديه بالفعل دور مدخل أول. اختر موظفًا آخر.')
        return redirect('/#entry-directory')
    a.employee_id=new.id
    log('REPLACE','Employee',old.id,f'استبدال المدخل الأول بالموظف البديل {new.full_name} من الصفحة الرئيسية')
    log('REPLACE','Employee',new.id,f'استلام دور المدخل الأول بدل {old.full_name} من الصفحة الرئيسية')
    db.session.commit()
    flash(f'تم استبدال دور المدخل الأول بالموظف {new.full_name} مع نقل فروع المسؤولية والحفاظ على سجل الموظف القديم.')
    return redirect('/#entry-directory')

@app.route('/replacement', methods=['GET','POST'])
@req
def replacement():
    if 'مسؤول التطبيق' not in roles():
        abort(403)
    mode=request.form.get('mode','') if request.method=='POST' else request.args.get('mode','supervisor')
    if request.method=='POST':
        if mode=='supervisor':
            old_id=request.form.get('old_supervisor_id','').strip()
            new_id=request.form.get('new_supervisor_id','').strip()
            old=db.session.get(User,int(old_id)) if old_id.isdigit() else None
            new=db.session.get(User,int(new_id)) if new_id.isdigit() else None
            if not old or not new or old.id==new.id or not old.is_active or not new.is_active:
                flash('يجب اختيار مشرف حالي وبديل نشط مختلف عنه.')
                return redirect(url_for('replacement',mode='supervisor'))
            if 'مشرف محافظة' not in actual_roles(old):
                flash('الشخص المحدد للاستبدال ليس مشرف محافظة حاليًا.')
                return redirect(url_for('replacement',mode='supervisor'))
            # Target receives the supervisor role and its default permissions; existing target roles remain intact.
            if 'مشرف محافظة' not in actual_roles(new):
                db.session.add(UserRole(user_id=new.id,role='مشرف محافظة'))
                for perm in ROLE_DEFAULT_PERMISSIONS['مشرف محافظة']:
                    if not UserPermission.query.filter_by(user_id=new.id,permission=perm).first():
                        db.session.add(UserPermission(user_id=new.id,permission=perm))
            # Move governorate scope and subordinate entry relationships.
            old_govs=UserGovernorate.query.filter_by(user_id=old.id).all()
            moved=0
            for link in old_govs:
                if not UserGovernorate.query.filter_by(user_id=new.id,governorate_id=link.governorate_id).first():
                    db.session.add(UserGovernorate(user_id=new.id,governorate_id=link.governorate_id))
                moved+=1
            UserGovernorate.query.filter_by(user_id=old.id).delete()
            for rel in SupervisorEntry.query.filter_by(supervisor_id=old.id).all():
                exists=SupervisorEntry.query.filter_by(supervisor_id=new.id,entry_id=rel.entry_id).first()
                if exists:
                    db.session.delete(rel)
                else:
                    rel.supervisor_id=new.id
            # Active approval delegations tied to the outgoing supervisor follow the replacement.
            for d in ApprovalDelegation.query.filter_by(supervisor_id=old.id,is_active=True).all():
                d.supervisor_id=new.id
            # Remove only the replaced role from the old user; preserve other roles and employee history.
            UserRole.query.filter_by(user_id=old.id,role='مشرف محافظة').delete()
            UserPermission.query.filter_by(user_id=old.id,permission='review_movements').delete()
            sync_role_accounts(old); sync_role_accounts(new)
            if not actual_roles(old):
                old.is_active=False
            log('REPLACE','User',old.id,f'استبدال مشرف محافظة بالبديل {new.full_name} — نقل {moved} ارتباط محافظة')
            log('REPLACE','User',new.id,f'استلام دور ونطاق مشرف المحافظة بدل {old.full_name}')
            db.session.commit()
            flash(f'تم استبدال المشرف ونقل نطاقه وارتباطاته إلى {new.full_name} دون حذف الموظف أو تاريخه.')
            return redirect(url_for('replacement',mode='supervisor'))
        if mode=='entry':
            old_id=request.form.get('old_entry_employee_id','').strip()
            new_id=request.form.get('new_entry_employee_id','').strip()
            old=db.session.get(Employee,int(old_id)) if old_id.isdigit() else None
            new=db.session.get(Employee,int(new_id)) if new_id.isdigit() else None
            if not old or not new or old.id==new.id or not old.is_active or not new.is_active:
                flash('يجب اختيار مدخل أول حالي وموظف بديل نشط مختلف عنه.')
                return redirect(url_for('replacement',mode='entry'))
            old_a=EntryAssignment.query.filter_by(employee_id=old.id,is_active=True).first()
            new_a=EntryAssignment.query.filter_by(employee_id=new.id,is_active=True).first()
            if not old_a:
                flash('الموظف المحدد ليس مدخلًا أول تنظيميًا حاليًا.')
                return redirect(url_for('replacement',mode='entry'))
            if new_a:
                flash('الموظف البديل لديه بالفعل دور مدخل أول. اختر موظفًا آخر.')
                return redirect(url_for('replacement',mode='entry'))
            # Transfer the same assignment object to preserve branch responsibility and supervisor link.
            old_a.employee_id=new.id
            # Legacy compatibility: if the old entry still has an account role, transfer its branch/supervisor links too.
            if old.user_id and new.user_id:
                old_u=db.session.get(User,old.user_id); new_u=db.session.get(User,new.user_id)
                if old_u and new_u:
                    for link in UserBranch.query.filter_by(user_id=old_u.id).all():
                        if not UserBranch.query.filter_by(user_id=new_u.id,branch_id=link.branch_id).first():
                            db.session.add(UserBranch(user_id=new_u.id,branch_id=link.branch_id))
                    UserBranch.query.filter_by(user_id=old_u.id).delete()
                    for rel in SupervisorEntry.query.filter_by(entry_id=old_u.id).all():
                        if not SupervisorEntry.query.filter_by(supervisor_id=rel.supervisor_id,entry_id=new_u.id).first():
                            rel.entry_id=new_u.id
                        else:
                            db.session.delete(rel)
                    UserRole.query.filter_by(user_id=old_u.id,role='المدخل الأول').delete()
                    sync_role_accounts(old_u); sync_role_accounts(new_u)
                    if not actual_roles(old_u): old_u.is_active=False
            log('REPLACE','Employee',old.id,f'استبدال المدخل الأول بالموظف البديل {new.full_name}')
            log('REPLACE','Employee',new.id,f'استلام دور المدخل الأول بدل {old.full_name}')
            db.session.commit()
            flash(f'تم استبدال المدخل الأول ونقل الفروع والمسؤولية إلى {new.full_name} مع الحفاظ على سجل الموظف القديم.')
            return redirect(url_for('replacement',mode='entry'))
        flash('نوع الاستبدال غير صحيح.')
    supervisors=[u for u in User.query.filter_by(is_active=True).order_by(User.full_name).all() if 'مشرف محافظة' in actual_roles(u)]
    supervisor_targets=[u for u in User.query.filter_by(is_active=True).order_by(User.full_name).all() if u not in supervisors and u.id!=me().id]
    entry_assignments=EntryAssignment.query.filter_by(is_active=True).order_by(EntryAssignment.id.asc()).all()
    entry_employees=[a.employee for a in entry_assignments if a.employee and a.employee.is_active]
    entry_ids={e.id for e in entry_employees}
    entry_targets=Employee.query.filter(Employee.is_active==True,~Employee.id.in_(entry_ids) if entry_ids else True).order_by(Employee.full_name).all()
    return render_template('replacement.html',mode=mode,supervisors=supervisors,supervisor_targets=supervisor_targets,entry_assignments=entry_assignments,entry_employees=entry_employees,entry_targets=entry_targets)

@app.post('/entry-role/add')
@req
def add_organizational_entry_role():
    if not has_role('مسؤول التطبيق','مشرف محافظة','Manager Application Support'): abort(403)
    eid=request.form.get('employee_id','').strip()
    if not eid.isdigit():
        flash('اختر موظفًا مسجلًا أولًا.'); return redirect('/#entry-directory')
    e=db.session.get(Employee,int(eid))
    if not e or not e.is_active:
        flash('الموظف غير موجود أو غير نشط.'); return redirect('/#entry-directory')
    existing_entry=EntryAssignment.query.filter_by(employee_id=e.id).first()
    if existing_entry and existing_entry.is_active:
        flash('هذا الموظف لديه بالفعل دور المدخل الأول التنظيمي.'); return redirect('/#entry-directory')
    if 'مسؤول التطبيق' in roles() or 'Manager Application Support' in roles():
        sup_id=request.form.get('supervisor_id','').strip()
        sup=db.session.get(User,int(sup_id)) if sup_id.isdigit() else None
        if not sup or 'مشرف محافظة' not in actual_roles(sup) or not sup.is_active:
            flash('اختر المشرف المسؤول.'); return redirect('/#entry-directory')
        if 'Manager Application Support' in roles():
            selected=session.get('manager_governorate_id')
            if not selected or int(selected) not in user_gov_ids(sup):
                abort(403)
    else:
        sup=me()
        if e.branch.governorate_id not in user_gov_ids(sup): abort(403)
    branch_ids={int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
    allowed=set(bids()) if 'مسؤول التطبيق' not in roles() and 'Manager Application Support' not in roles() else {b.id for b in Branch.query.filter_by(is_active=True).all()}
    if 'مسؤول التطبيق' in roles() or 'Manager Application Support' in roles():
        if 'Manager Application Support' in roles():
            selected=session.get('manager_governorate_id')
            allowed_govs={int(selected)} if selected else set()
        else:
            allowed_govs=user_gov_ids(sup)
        allowed={b.id for b in Branch.query.filter(Branch.id.in_(allowed),Branch.governorate_id.in_(allowed_govs),Branch.is_active==True).all()}
    branch_ids &= allowed
    if not branch_ids:
        branch_ids={e.branch_id} if e.branch_id in allowed else set()
    if not branch_ids:
        flash('اختر فرع مسؤولية واحدًا على الأقل ضمن نطاق المشرف المسؤول.'); return redirect('/#entry-directory')
    # لا يُسمح بفرع مسؤولية مرتبط بمدخل تنظيمي آخر.
    taken={x.branch_id for x in EntryAssignmentBranch.query.join(EntryAssignment).filter(EntryAssignment.is_active==True).all()}
    if branch_ids & taken:
        flash('يوجد فرع من الفروع المختارة مسند بالفعل إلى مدخل أول آخر.'); return redirect('/#entry-directory')
    if existing_entry:
        a=existing_entry; a.supervisor_id=sup.id; a.is_active=True
        EntryAssignmentBranch.query.filter_by(entry_assignment_id=a.id).delete()
    else:
        a=EntryAssignment(employee_id=e.id,supervisor_id=sup.id,is_active=True); db.session.add(a); db.session.flush()
    for bid in branch_ids: db.session.add(EntryAssignmentBranch(entry_assignment_id=a.id,branch_id=bid))
    log('ROLE_CHANGE','Employee',e.id,'إضافة دور المدخل الأول التنظيمي بدون حساب دخول'); db.session.commit()
    flash('تمت إضافة دور المدخل الأول التنظيمي. لم يتم إنشاء حساب أو اسم مستخدم للمدخل.')
    return redirect('/#entry-directory')

@app.post('/entry-role/<int:employee_id>/remove')
@req
def remove_organizational_entry_role(employee_id):
    e=db.session.get(Employee,employee_id); a=organizational_entry_for_employee(e) if e else None
    if not a: abort(404)
    if 'مسؤول التطبيق' not in roles():
        if 'مشرف محافظة' not in roles() or a.supervisor_id!=me().id: abort(403)
    a.is_active=False
    db.session.commit(); log('ROLE_CHANGE','Employee',employee_id,'إزالة دور المدخل الأول التنظيمي'); db.session.commit()
    flash('تمت إزالة دور المدخل الأول التنظيمي، وأصبحت فروع مسؤوليته متاحة لإسنادها من جديد.')
    return redirect('/structure#entry-role-chain')

@app.get('/employee-role-select')
@req
@only('مسؤول التطبيق')
def employee_role_select():
    eid=request.args.get('employee_id','').strip()
    if not eid.isdigit():
        flash('اختر موظفًا مسجلًا أولًا.')
        return redirect('/structure#add-entry-role')
    e=db.session.get(Employee,int(eid))
    if not e or not e.is_active:
        flash('الموظف غير موجود أو غير نشط.')
        return redirect('/structure#add-entry-role')
    if e.user_id and 'المدخل الأول' in actual_roles(db.session.get(User,e.user_id)):
        flash('هذا الموظف مسجل بالفعل كمدخل أول.')
        return redirect('/structure#add-entry-role')
    return redirect(url_for('employee_convert_role',i=e.id))

@app.get('/employee-search')
@req
def employee_search():
    q=request.args.get('q','').strip()
    if len(q)<2:
        return {'results': []}
    bs=bids()
    if not bs:
        return {'results': []}
    like=f'%{q}%'
    rows=(Employee.query.filter(Employee.is_active==True, Employee.branch_id.in_(bs))
          .filter((Employee.full_name.ilike(like)) | (Employee.job_code.ilike(like)) | (Employee.job_title.ilike(like)))
          .order_by(Employee.full_name).limit(12).all())
    results=[]
    for e in rows:
        moves=Movement.query.filter_by(employee_id=e.id,is_active=True).order_by(Movement.id.desc()).limit(80).all()
        latest={}
        for mv in moves:
            if mv.movement_type not in latest:
                latest[mv.movement_type]=mv
        def fmt(mv):
            if not mv: return None
            if mv.movement_type=='إجازة':
                dates=''
                if mv.from_date and mv.to_date: dates=f"{mv.from_date.strftime('%Y-%m-%d')} ← {mv.to_date.strftime('%Y-%m-%d')}"
                return {'label':mv.leave_type or 'إجازة','detail':dates,'status':mv.status}
            if mv.movement_type=='انتداب':
                dates=''
                if mv.from_date and mv.to_date: dates=f"{mv.from_date.strftime('%Y-%m-%d')} ← {mv.to_date.strftime('%Y-%m-%d')}"
                return {'label':mv.destination.name if mv.destination else 'انتداب','detail':dates,'status':mv.status}
            return {'label':'إذن','detail':mv.permission_date.strftime('%Y-%m-%d') if mv.permission_date else '—','status':mv.status}
        results.append({'id':e.id,'name':e.full_name,'code':e.job_code or '','branch':e.branch.name if e.branch else '',
                        'last_leave':fmt(latest.get('إجازة')),'last_assignment':fmt(latest.get('انتداب')),'last_permission':fmt(latest.get('إذن'))})
    return {'results':results}

@app.route('/governorates',methods=['GET','POST'])
@req
@only('مسؤول التطبيق')
def governorates():
    if request.method=='POST':
        name=request.form.get('name','').strip()
        if not name: flash('اكتب اسم المحافظة.')
        elif Governorate.query.filter_by(name=name).first(): flash('المحافظة موجودة بالفعل.')
        else: x=Governorate(name=name); db.session.add(x); db.session.commit(); log('ADD','Governorate',x.id,name); db.session.commit(); flash('تمت الإضافة.')
    return render_template('governorates.html',rows=Governorate.query.order_by(Governorate.name))
@app.route('/governorates/<int:i>/edit',methods=['POST'])
@req
@only('مسؤول التطبيق')
def ge(i):
    x=db.session.get(Governorate,i)
    if not x: abort(404)
    n=request.form.get('name','').strip(); dup=Governorate.query.filter(Governorate.name==n,Governorate.id!=i).first()
    if not n or dup: flash('الاسم غير صالح أو مكرر.')
    else: x.name=n; log('EDIT','Governorate',i,n); db.session.commit(); flash('تم التعديل.')
    return redirect('/governorates')
@app.post('/governorates/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def gt(i):
    x=db.session.get(Governorate,i)
    if not x: abort(404)
    x.is_active=not x.is_active; log('TOGGLE','Governorate',i); db.session.commit(); return redirect('/governorates')
@app.post('/governorates/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def gd(i):
    x=db.session.get(Governorate,i)
    if not x: abort(404)
    if Branch.query.filter_by(governorate_id=i).count() or UserGovernorate.query.filter_by(governorate_id=i).count(): flash('لا يمكن الحذف لوجود ارتباطات؛ استخدم التعطيل.')
    else: db.session.delete(x); log('DELETE','Governorate',i); db.session.commit(); flash('تم الحذف.')
    return redirect('/governorates')

@app.route('/branches',methods=['GET','POST'])
@req
def branches():
    if not can('manage_structure') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    if request.method=='GET':
        # صفحة الفروع مستقلة لمسؤول التطبيق والمشرف، وتحتوي على نموذج إضافة الفرع.
        # مسؤول التطبيق يرى جميع المحافظات، بينما المشرف يرى محافظاته فقط.
        gs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all() if gids() else []
        rows=Branch.query.filter(Branch.governorate_id.in_(gids())).order_by(Branch.governorate_id,Branch.name).all() if gids() else []
        return render_template('branches.html',rows=rows,gs=gs,is_admin=('مسؤول التطبيق' in roles()))
    if request.method=='POST':
        gid=request.form.get('governorate_id'); name=request.form.get('name','').strip(); code=request.form.get('code','').strip(); entry_user_id=request.form.get('entry_user_id','').strip()
        g=db.session.get(Governorate,int(gid)) if gid and gid.isdigit() else None
        if not g or not g.is_active or not name or not code:
            flash('جميع بيانات الفرع مطلوبة: المحافظة والاسم والكود.')
        elif 'مسؤول التطبيق' not in roles() and g.id not in set(gids()):
            abort(403)
        elif Branch.query.filter_by(governorate_id=g.id,name=name).first():
            flash('الفرع موجود بالفعل في هذه المحافظة.')
        else:
            x=Branch(governorate_id=g.id,name=name,code=code); db.session.add(x); db.session.flush();
            if entry_user_id.isdigit():
                eu=db.session.get(User,int(entry_user_id))
                valid_entry = bool(eu and eu.is_active and 'المدخل الأول' in actual_roles(eu))
                if valid_entry:
                    # الربط هنا خاص بفروع المسؤولية فقط، ولا يغيّر فرع التعيين الوظيفي للمدخل.
                    if 'مسؤول التطبيق' not in roles() and not (set(gids()) & {g.id}): abort(403)
                    if 'مسؤول التطبيق' in roles() or g.id in {b.governorate_id for b in Branch.query.filter(Branch.id.in_(user_branch_ids(eu))).all()}:
                        db.session.add(UserBranch(user_id=eu.id,branch_id=x.id))
            db.session.commit(); log('ADD','Branch',x.id,name); db.session.commit(); flash('تمت إضافة الفرع وربطه بالمدخل الأول تلقائيًا.')
    gs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all()
    rows=Branch.query.filter(Branch.governorate_id.in_(gids())).order_by(Branch.name).all() if gids() else []
    return render_template('branches.html',rows=rows,gs=gs)
@app.post('/branches/<int:i>/edit')
@req
def be(i):
    if not can('manage_structure') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    x=db.session.get(Branch,i); g=db.session.get(Governorate,int(request.form.get('governorate_id','0'))); n=request.form.get('name','').strip(); code=request.form.get('code','').strip()
    if not x or not g or not g.is_active or not n or not code: flash('جميع بيانات الفرع مطلوبة.'); return redirect('/branches')
    if 'مسؤول التطبيق' not in roles() and (x.governorate_id not in set(gids()) or g.id not in set(gids())): abort(403)
    dup=Branch.query.filter(Branch.governorate_id==g.id,Branch.name==n,Branch.id!=i).first()
    if dup: flash('الفرع موجود بالفعل في هذه المحافظة.')
    else:
        x.governorate_id=g.id; x.name=n; x.code=code; log('EDIT','Branch',i,n); db.session.commit(); flash('تم التعديل.')
    return redirect('/branches')
@app.post('/branches/<int:i>/toggle')
@req
def bt(i):
    if not can('manage_structure') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    x=db.session.get(Branch,i)
    if not x: abort(404)
    if 'مسؤول التطبيق' not in roles() and x.governorate_id not in set(gids()): abort(403)
    x.is_active=not x.is_active; log('TOGGLE','Branch',i); db.session.commit(); return redirect('/branches')
@app.post('/branches/<int:i>/delete')
@req
def bd(i):
    if not can('manage_structure') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    x=db.session.get(Branch,i)
    if not x: abort(404)
    if 'مسؤول التطبيق' not in roles() and x.governorate_id not in set(gids()): abort(403)
    if Employee.query.filter_by(branch_id=i).count() or UserBranch.query.filter_by(branch_id=i).count() or Movement.query.filter_by(destination_branch_id=i).count():
        flash('لا يمكن حذف الفرع لوجود موظفين أو مستخدمين أو حركات مرتبطة به؛ استخدم التعطيل.')
    else:
        db.session.delete(x); log('DELETE','Branch',i); db.session.commit(); flash('تم حذف الفرع نهائيًا.')
    return redirect('/branches')

@app.route('/users',methods=['GET','POST'])
@req
def users():
    if not can('manage_users') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    u=me(); visible=User.query.order_by(User.id.desc()).all() if 'مسؤول التطبيق' in roles(u) else [x for x in User.query.order_by(User.id.desc()).all() if x.id==u.id or allowed_target_user(x)]
    if request.method=='POST':
        selected_roles=[r for r in request.form.getlist('roles') if r in ROLES] or ([request.form.get('role')] if request.form.get('role') in ROLES else [])
        username=request.form.get('username','').strip(); full=request.form.get('full_name','').strip(); email=request.form.get('email','').strip(); job_title=request.form.get('job_title','').strip(); job_code=request.form.get('job_code','').strip(); password=request.form.get('password','')
        if not selected_roles or any(not allowed_create_user(r) for r in selected_roles): abort(403)
        if not username or not full or not email or not valid_email(email) or not job_title or not job_code or not valid_password(password) or User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first(): flash('جميع بيانات الحساب مطلوبة، واسم المستخدم فريد وكلمة المرور 8 أحرف على الأقل.')
        else:
            nu=User(username=username,full_name=full,email=email,job_title=job_title,job_code=job_code,password_hash=generate_password_hash(password)); db.session.add(nu); db.session.flush()
            for role in selected_roles: db.session.add(UserRole(user_id=nu.id,role=role))
            # صلاحيات الدور تضاف تلقائيًا عند إنشاء الحساب، ويمكن لمسؤول التطبيق تعديلها لاحقًا بالزيادة أو النقصان.
            selected_perms={x for x in request.form.getlist('permissions') if x in PERMISSIONS}
            defaults=set()
            for r in selected_roles: defaults |= ROLE_DEFAULT_PERMISSIONS.get(r,set())
            if 'مسؤول التطبيق' not in roles(u):
                defaults &= GRANTABLE_BY_SUPERVISOR
                selected_perms &= GRANTABLE_BY_SUPERVISOR
            selected_perms |= defaults
            for perm in selected_perms: db.session.add(UserPermission(user_id=nu.id,permission=perm))
            if 'مشرف محافظة' in selected_roles:
                chosen={int(x) for x in request.form.getlist('governorate_id') if x.isdigit()}
                allowed=set(gids()) if 'مسؤول التطبيق' not in roles(u) else {g.id for g in Governorate.query.filter_by(is_active=True)}
                chosen &= allowed
                if not chosen:
                    db.session.rollback(); flash('يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.'); return redirect('/users')
                for gid in chosen: db.session.add(UserGovernorate(user_id=nu.id,governorate_id=gid))
            if 'المدخل الأول' in selected_roles:
                chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & set(bids())
                if not chosen:
                    db.session.rollback(); flash('يجب إسناد فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.'); return redirect('/users')
                for bid in chosen: db.session.add(UserBranch(user_id=nu.id,branch_id=bid))
                # The employee's appointment branch is separate from the branches managed by the first-level user.
                appointment_raw=request.form.get('employee_branch_id','').strip()
                appointment_bid=int(appointment_raw) if appointment_raw.isdigit() else 0
                appointment_branch=db.session.get(Branch,appointment_bid) if appointment_bid else None
                if not appointment_branch or not appointment_branch.is_active or ('مسؤول التطبيق' not in roles(u) and appointment_branch.governorate_id not in set(gids())):
                    db.session.rollback(); flash('يجب اختيار فرع تعيين تابع لمحافظة ضمن نطاقك.'); return redirect('/users')
                # Link first-level user to the responsible supervisor automatically.
                gid_values={db.session.get(Branch,bid).governorate_id for bid in chosen if db.session.get(Branch,bid)}
                requested_sup=request.form.get('supervisor_id','').strip()
                sup=None
                if requested_sup.isdigit():
                    candidate=db.session.get(User,int(requested_sup))
                    if candidate and 'مشرف محافظة' in actual_roles(candidate) and candidate.is_active and gid_values & user_gov_ids(candidate): sup=candidate
                if not sup and 'مسؤول التطبيق' not in roles(u): sup=u if 'مشرف محافظة' in actual_roles(u) else None
                if not sup and len(gid_values)==1: sup=supervisor_for_governorate(next(iter(gid_values)))
                if sup: db.session.add(SupervisorEntry(supervisor_id=sup.id,entry_id=nu.id))
                # The first-level user is also an employee; employee data is completed in the same registration.
                if 'المدخل الأول' in selected_roles and chosen:
                    hire_date_raw=request.form.get('employee_hire_date','').strip()
                    company_phone=request.form.get('employee_company_phone','').strip()
                    personal_phone=request.form.get('employee_personal_phone','').strip()
                    if not hire_date_raw or not parse_date(hire_date_raw) or not company_phone or not personal_phone:
                        db.session.rollback(); flash('بيانات الموظف للمدخل الأول مكتملة إلزاميًا: تاريخ التعيين وهاتف الشركة والهاتف الشخصي.'); return redirect('/structure')
                    employee=Employee.query.filter_by(user_id=nu.id).first()
                    if not employee:
                        employee=Employee(user_id=nu.id,employee_code=None,email=nu.email,full_name=nu.full_name,branch_id=appointment_bid,job_title=nu.job_title,job_code=nu.job_code,hire_date=parse_date(request.form.get('employee_hire_date','').strip()),company_phone=request.form.get('employee_company_phone','').strip(),personal_phone=request.form.get('employee_personal_phone','').strip(),is_active=True)
                        db.session.add(employee)
                    else:
                        employee.full_name=nu.full_name; employee.email=nu.email; employee.job_title=nu.job_title; employee.job_code=nu.job_code
            sync_role_accounts(nu); log('ADD','User',nu.id,username); db.session.commit(); flash('تم إنشاء الحساب وربطه تلقائيًا بالهيكل.')
    gs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).all() if 'مسؤول التطبيق' not in roles(u) else Governorate.query.filter_by(is_active=True).all()
    bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all() if 'مسؤول التطبيق' not in roles(u) else Branch.query.filter_by(is_active=True).all()
    role_default_permissions={r:sorted(ROLE_DEFAULT_PERMISSIONS.get(r,set())) for r in ROLES}
    # الحساب الوهمي لكل دور محفوظ ككيان RoleAccount مستقل؛ نعرضه للإدارة
    # حتى يكون واضحًا أن كل دور إضافي له حسابه الداخلي المستقل بنفس بيانات الدخول.
    role_accounts_by_user={u.id: RoleAccount.query.filter_by(user_id=u.id).order_by(RoleAccount.role.asc()).all() for u in visible}
    supervisor_choices=[x for x in User.query.filter_by(is_active=True).order_by(User.full_name).all() if 'مشرف محافظة' in actual_roles(x)]
    return render_template('users.html',rows=visible,gs=gs,bs=bs,role_default_permissions=role_default_permissions,role_accounts_by_user=role_accounts_by_user,supervisor_choices=supervisor_choices)
@app.route('/users/<int:i>/edit',methods=['GET','POST'])
@req
def user_edit(i):
    target=db.session.get(User,i)
    if not target or not can('manage_users') or not allowed_target_user(target) and i!=me().id: abort(403)
    if 'مسؤول التطبيق' not in roles() and 'المدخل الأول' not in roles(target): abort(403)
    u=target
    if request.method=='POST':
        u.full_name=request.form.get('full_name','').strip() or u.full_name
        email=request.form.get('email','').strip()
        if not email or not valid_email(email):
            flash('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.'); return redirect(url_for('user_edit',i=i))
        duplicate_email=User.query.filter(User.email==email,User.id!=i).first()
        if duplicate_email:
            flash('البريد الإلكتروني مستخدم بالفعل.'); return redirect(url_for('user_edit',i=i))
        u.email=email
        u.job_title=request.form.get('job_title','').strip() or None
        u.job_code=request.form.get('job_code','').strip() or None
        if not u.full_name or not u.job_title or not u.job_code:
            flash('الاسم والوظيفة والكود الوظيفي حقول إجبارية.'); return redirect(url_for('user_edit',i=i))
        if 'مسؤول التطبيق' in roles():
            selected=[r for r in request.form.getlist('roles') if r in ROLES]
            if not selected: flash('يجب اختيار دور واحد على الأقل.'); return redirect(url_for('user_edit',i=i))
            if i==me().id and 'مسؤول التطبيق' not in selected: flash('لا يمكن إزالة دور مسؤول التطبيق من حسابك هنا.'); return redirect(url_for('user_edit',i=i))
            selected_perm_set={x for x in request.form.getlist('permissions') if x in PERMISSIONS}
            old_roles=actual_roles(target)
            # عند إضافة دور جديد تُضاف صلاحياته الافتراضية تلقائيًا، أما الصلاحيات الموجودة فيمكن لمسؤول التطبيق زيادتها أو تقليلها.
            newly_added=set(selected)-set(old_roles)
            defaults=set()
            for r in newly_added: defaults |= ROLE_DEFAULT_PERMISSIONS.get(r,set())
            if 'مسؤول التطبيق' not in roles():
                defaults &= GRANTABLE_BY_SUPERVISOR
                selected_perm_set &= GRANTABLE_BY_SUPERVISOR
            selected_perm_set |= defaults
            UserRole.query.filter_by(user_id=i).delete(); UserPermission.query.filter_by(user_id=i).delete()
            for r in selected: db.session.add(UserRole(user_id=i,role=r))
            for perm in selected_perm_set: db.session.add(UserPermission(user_id=i,permission=perm))
            sync_role_accounts(target)
            # Always clear old scope assignments first so removing a role also removes its old scope.
            UserGovernorate.query.filter_by(user_id=i).delete()
            UserBranch.query.filter_by(user_id=i).delete()
            if 'مشرف محافظة' in selected:
                allowed_govs={g.id for g in Governorate.query.filter_by(is_active=True).all()} if 'مسؤول التطبيق' in roles() else set(gids())
                chosen={int(x) for x in request.form.getlist('governorate_id') if x.isdigit()} & allowed_govs
                if not chosen:
                    db.session.rollback(); flash('يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.'); return redirect(url_for('user_edit',i=i))
                for gid in chosen: db.session.add(UserGovernorate(user_id=i,governorate_id=gid))
            if 'المدخل الأول' in selected:
                allowed_branches={b.id for b in Branch.query.filter_by(is_active=True).all()} if 'مسؤول التطبيق' in roles() else set(bids())
                chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & allowed_branches
                if not chosen:
                    db.session.rollback(); flash('يجب إسناد فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.'); return redirect(url_for('user_edit',i=i))
                appointment_raw=request.form.get('employee_branch_id','').strip()
                appointment_bid=int(appointment_raw) if appointment_raw.isdigit() else 0
                appointment_branch=db.session.get(Branch,appointment_bid) if appointment_bid else None
                if not appointment_branch or not appointment_branch.is_active or ('مسؤول التطبيق' not in roles() and appointment_branch.governorate_id not in set(gids())):
                    db.session.rollback(); flash('يجب اختيار فرع تعيين تابع لمحافظة ضمن نطاقك.'); return redirect(url_for('user_edit',i=i))
                for bid in chosen: db.session.add(UserBranch(user_id=i,branch_id=bid))
            # Explicitly keep the simple hierarchy link: first-level user -> responsible supervisor.
            SupervisorEntry.query.filter_by(entry_id=i).delete()
            if 'المدخل الأول' in selected:
                chosen_gids={db.session.get(Branch,bid).governorate_id for bid in chosen if db.session.get(Branch,bid)}
                sid=request.form.get('supervisor_id','').strip()
                sup=db.session.get(User,int(sid)) if sid.isdigit() else None
                if not sup and len(chosen_gids)==1:
                    sup=supervisor_for_governorate(next(iter(chosen_gids)))
                if sup and sup.is_active and 'مشرف محافظة' in actual_roles(sup) and chosen_gids & user_gov_ids(sup):
                    db.session.add(SupervisorEntry(supervisor_id=sup.id,entry_id=i))
                linked_emp=Employee.query.filter_by(user_id=i).first()
                hire_date_raw=request.form.get('employee_hire_date','').strip()
                company_phone=request.form.get('employee_company_phone','').strip()
                personal_phone=request.form.get('employee_personal_phone','').strip()
                if not hire_date_raw or not parse_date(hire_date_raw) or not company_phone or not personal_phone:
                    db.session.rollback(); flash('بيانات الموظف للمدخل الأول مكتملة إلزاميًا: تاريخ التعيين وهاتف الشركة والهاتف الشخصي.'); return redirect(url_for('user_edit',i=i))
                if linked_emp:
                    linked_emp.full_name=u.full_name; linked_emp.email=u.email; linked_emp.job_title=u.job_title; linked_emp.job_code=u.job_code
                    linked_emp.branch_id=appointment_bid; linked_emp.hire_date=parse_date(hire_date_raw); linked_emp.company_phone=company_phone; linked_emp.personal_phone=personal_phone; linked_emp.is_active=True
                elif chosen:
                    db.session.add(Employee(user_id=i,employee_code=None,email=u.email,full_name=u.full_name,branch_id=appointment_bid,job_title=u.job_title,job_code=u.job_code,hire_date=parse_date(hire_date_raw),company_phone=company_phone,personal_phone=personal_phone,is_active=True))
        else:
            # Supervisor may only edit first-level users in his governorate(s).
            selected_perm_set={x for x in request.form.getlist('permissions') if x in GRANTABLE_BY_SUPERVISOR}
            UserPermission.query.filter_by(user_id=i).delete()
            for perm in selected_perm_set: db.session.add(UserPermission(user_id=i,permission=perm))
            sync_role_accounts(target)
            chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & set(bids())
            if not chosen: flash('يجب إسناد فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.'); return redirect(url_for('user_edit',i=i))
            appointment_raw=request.form.get('employee_branch_id','').strip()
            appointment_bid=int(appointment_raw) if appointment_raw.isdigit() else 0
            appointment_branch=db.session.get(Branch,appointment_bid) if appointment_bid else None
            if not appointment_branch or not appointment_branch.is_active or appointment_branch.governorate_id not in set(gids()):
                flash('يجب اختيار فرع تعيين تابع لمحافظة ضمن نطاقك.'); return redirect(url_for('user_edit',i=i))
            UserBranch.query.filter_by(user_id=i).delete()
            for bid in chosen: db.session.add(UserBranch(user_id=i,branch_id=bid))
            SupervisorEntry.query.filter_by(entry_id=i).delete()
            chosen_gids={db.session.get(Branch,bid).governorate_id for bid in chosen if db.session.get(Branch,bid)}
            sup=me() if 'مشرف محافظة' in actual_roles(me()) else None
            if sup and sup.is_active and chosen_gids & user_gov_ids(sup):
                db.session.add(SupervisorEntry(supervisor_id=sup.id,entry_id=i))
            linked_emp=Employee.query.filter_by(user_id=i).first()
            hire_date_raw=request.form.get('employee_hire_date','').strip()
            company_phone=request.form.get('employee_company_phone','').strip()
            personal_phone=request.form.get('employee_personal_phone','').strip()
            if not hire_date_raw or not parse_date(hire_date_raw) or not company_phone or not personal_phone:
                flash('بيانات الموظف للمدخل الأول مكتملة إلزاميًا: تاريخ التعيين وهاتف الشركة والهاتف الشخصي.'); return redirect(url_for('user_edit',i=i))
            if linked_emp:
                linked_emp.full_name=u.full_name; linked_emp.email=u.email; linked_emp.job_title=u.job_title; linked_emp.job_code=u.job_code
                linked_emp.branch_id=appointment_bid; linked_emp.hire_date=parse_date(hire_date_raw); linked_emp.company_phone=company_phone; linked_emp.personal_phone=personal_phone; linked_emp.is_active=True
            else:
                db.session.add(Employee(user_id=i,employee_code=None,email=u.email,full_name=u.full_name,branch_id=appointment_bid,job_title=u.job_title,job_code=u.job_code,hire_date=parse_date(hire_date_raw),company_phone=company_phone,personal_phone=personal_phone,is_active=True))
        log('EDIT','User',i,'تعديل الحساب والنطاق والصلاحيات'); db.session.commit(); flash('تم حفظ التعديلات.'); return redirect('/users')
    gs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).all() if 'مسؤول التطبيق' not in roles() else Governorate.query.filter_by(is_active=True).all()
    bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all() if 'مسؤول التطبيق' not in roles() else Branch.query.filter_by(is_active=True).all()
    linked=SupervisorEntry.query.filter_by(entry_id=i).order_by(SupervisorEntry.id.asc()).first()
    entry_supervisor=linked.supervisor if linked else supervisor_for_entry(u)
    supervisor_choices=[]
    if 'المدخل الأول' in actual_roles(u):
        gids_u={b.governorate_id for b in Branch.query.filter(Branch.id.in_(user_branch_ids(u))).all()}
        if gids_u:
            suids={x.user_id for x in UserGovernorate.query.filter(UserGovernorate.governorate_id.in_(gids_u)).all()}
            supervisor_choices=[x for x in User.query.filter(User.id.in_(suids),User.is_active==True).order_by(User.full_name).all() if 'مشرف محافظة' in actual_roles(x)] if suids else []
    linked_emp=Employee.query.filter_by(user_id=i).first()
    return render_template('user_edit.html',u=u,selected_roles=roles(u),selected_permissions=user_permissions(u),gs=gs,bs=bs,entry_supervisor=entry_supervisor,supervisor_choices=supervisor_choices,linked_emp=linked_emp)
@app.post('/users/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def ud(i):
    if i==me().id: flash('لا يمكن حذف الحساب المستخدم حاليًا.')
    else:
        u=db.session.get(User,i)
        if not u: abort(404)
        if Movement.query.filter((Movement.created_by==i)|(Movement.modified_by==i)|(Movement.reviewed_by==i)|(Movement.approved_by==i)).count(): flash('لا يمكن حذف المستخدم لوجود حركات مرتبطة به؛ استخدم التعطيل.')
        else: db.session.delete(u); log('DELETE','User',i); db.session.commit(); flash('تم حذف المستخدم.')
    return redirect('/users')
@app.post('/users/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def ut(i):
    if i==me().id: flash('لا يمكن تعطيل الحساب المستخدم حاليًا.')
    else:
        u=db.session.get(User,i); u.is_active=not u.is_active; log('TOGGLE','User',i); db.session.commit()
    return redirect('/users')
@app.post('/users/<int:i>/reset')
@req
def ur(i):
    if not can('manage_users') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    u=db.session.get(User,i)
    if not u: abort(404)
    if 'مسؤول التطبيق' not in roles() and not ('المدخل الأول' in roles(u) and bool(set(gids()) & {b.governorate_id for b in Branch.query.join(UserBranch,UserBranch.branch_id==Branch.id).filter(UserBranch.user_id==i).all()})): abort(403)
    p=request.form.get('password','')
    if not valid_password(p): flash('كلمة المرور يجب أن تكون 8 أحرف على الأقل وتحتوي على حروف وأرقام.')
    else: u.password_hash=generate_password_hash(p); u.must_change_password=True; sync_role_accounts(u); log('PASSWORD_RESET','User',i); db.session.commit(); flash('تمت إعادة التعيين.')
    return redirect('/users')
@app.post('/users/<int:i>/govs')
@req
@only('مسؤول التطبيق')
def ug(i):
    u=db.session.get(User,i); allowed={g.id for g in Governorate.query.filter_by(is_active=True)}; chosen={int(x) for x in request.form.getlist('governorate_id')}; UserGovernorate.query.filter_by(user_id=i).delete()
    for gid in chosen & allowed: db.session.add(UserGovernorate(user_id=i,governorate_id=gid))
    log('ASSIGN','User',i,'محافظات'); db.session.commit(); return redirect('/users')
@app.post('/users/<int:i>/branches')
@req
@only('مسؤول التطبيق','مشرف محافظة')
def ub(i):
    u=db.session.get(User,i)
    if not u or 'المدخل الأول' not in roles(u): abort(400)
    if not allowed_target_user(u): abort(403)
    allowed=set(bids())
    chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & allowed
    if not chosen:
        flash('يجب إسناد فرع واحد على الأقل للمدخل الأول.'); return redirect('/users')
    UserBranch.query.filter_by(user_id=i).delete()
    for bid in chosen: db.session.add(UserBranch(user_id=i,branch_id=bid))
    linked_emp=Employee.query.filter_by(user_id=i).first()
    if linked_emp:
        # فرع التعيين كموظف مستقل تمامًا عن فروع المسؤولية.
        linked_emp.full_name=u.full_name; linked_emp.email=u.email; linked_emp.job_title=u.job_title; linked_emp.job_code=u.job_code; linked_emp.is_active=True
    else:
        # لا ننشئ سجل موظف ناقصًا من شاشة إدارة فروع المسؤولية؛ إنشاء المدخل الأول ينشئ الموظف كاملًا.
        flash('تم تحديث فروع المسؤولية. سجل الموظف غير مكتمل، يرجى فتح تعديل المدخل لاستكمال بيانات الموظف.')
    log('ASSIGN','User',i,'فروع المسؤولية'); db.session.commit(); return redirect('/structure')


@app.route('/users/<int:i>/entry-management',methods=['GET','POST'])
@req
def entry_management(i):
    u=db.session.get(User,i)
    if not u or 'المدخل الأول' not in actual_roles(u): abort(404)
    if not allowed_target_user(u): abort(403)
    if 'مسؤول التطبيق' not in roles() and 'مشرف محافظة' not in roles(): abort(403)
    current_ids=user_branch_ids(u)
    allowed_branch_objs=Branch.query.filter(Branch.is_active==True, Branch.governorate_id.in_(gids() if 'مسؤول التطبيق' not in roles() else [g.id for g in Governorate.query.filter_by(is_active=True).all()])).order_by(Branch.name.asc()).all() if gids() or 'مسؤول التطبيق' in roles() else []
    # الفرع المتاح للمدخل = غير مرتبط بمدخل أول آخر، أو مرتبط بالمدخل الحالي.
    available=[]
    for b in allowed_branch_objs:
        owners=[x.user_id for x in UserBranch.query.filter_by(branch_id=b.id).all() if x.user_id!=u.id]
        occupied=False
        for oid in owners:
            ou=db.session.get(User,oid)
            if ou and ou.is_active and 'المدخل الأول' in actual_roles(ou):
                occupied=True; break
        if not occupied or b.id in current_ids: available.append(b)
    if request.method=='POST':
        action=request.form.get('action','branches')
        if action=='branches':
            chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
            allowed_ids={b.id for b in available}
            chosen &= allowed_ids
            if not chosen:
                flash('يجب اختيار فرع واحد على الأقل للمدخل الأول.')
                return redirect(url_for('entry_management',i=i))
            UserBranch.query.filter_by(user_id=i).delete()
            for bid in sorted(chosen): db.session.add(UserBranch(user_id=i,branch_id=bid))
            log('ASSIGN','User',i,'تحديث فروع مسؤولية المدخل الأول'); db.session.commit(); flash('تم تحديث فروع مسؤولية المدخل الأول بنجاح.')
            return redirect(url_for('entry_management',i=i))
        if action=='remove_role':
            if 'مسؤول التطبيق' not in roles(): abort(403)
            linked=Employee.query.filter_by(user_id=u.id).first()
            UserRole.query.filter_by(user_id=u.id,role='المدخل الأول').delete()
            UserBranch.query.filter_by(user_id=u.id).delete()
            SupervisorEntry.query.filter_by(entry_id=u.id).delete()
            remaining=actual_roles(u)-{'المدخل الأول'}
            if not remaining: u.is_active=False
            if linked: linked.user_id=None
            log('ROLE_CHANGE','User',i,'إزالة دور المدخل الأول'); db.session.commit(); flash('تمت إزالة دور المدخل الأول مع الاحتفاظ بسجل الموظف وحركاته.')
            return redirect('/')
    return render_template('entry_management.html',u=u,branches=available,current_ids=current_ids,linked_emp=Employee.query.filter_by(user_id=u.id).first(),supervisors=[s for s in User.query.all() if s.is_active and 'مشرف محافظة' in actual_roles(s)],is_admin=('مسؤول التطبيق' in roles()))

@app.route('/employees',methods=['GET','POST'])
@req
def employees():
    bs=bids()
    if request.method=='POST':
        if not can('manage_employees'): abort(403)
        bid=int(request.form.get('branch_id','0')) if request.form.get('branch_id','').isdigit() else 0
        if not branch_ok(bid): abort(403)
        submitted_gid=int(request.form.get('governorate_id','0')) if request.form.get('governorate_id','').isdigit() else 0
        branch_obj=db.session.get(Branch,bid)
        name=request.form.get('full_name','').strip(); email=request.form.get('email','').strip(); job_title=request.form.get('job_title','').strip(); job_code=request.form.get('job_code','').strip(); hire_date=request.form.get('hire_date','').strip(); company_phone=request.form.get('company_phone','').strip(); personal_phone=request.form.get('personal_phone','').strip()
        if not branch_obj or branch_obj.governorate_id!=submitted_gid: flash('يجب اختيار محافظة وفرع صحيحين.')
        elif not all([name,email,job_title,job_code,hire_date,company_phone,personal_phone]): flash('جميع بيانات الموظف مطلوبة.')
        elif not valid_email(email): flash('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.')
        elif not parse_date(hire_date): flash('تاريخ التعيين مطلوب وبصيغة صحيحة.')
        else:
            existing=Employee.query.filter_by(email=email).first()
            if existing:
                if existing.is_active:
                    flash('البريد الإلكتروني مستخدم بالفعل لموظف آخر.')
                    return redirect(url_for('employees'))
                # الموظف غير ظاهر في القائمة لأنه معطّل. لا ننشئ سجلًا ثانيًا؛ نستعيد نفس السجل ونحافظ على تاريخه وحركاته.
                existing.full_name=name; existing.email=email; existing.branch_id=bid; existing.job_title=job_title; existing.job_code=job_code
                existing.hire_date=parse_date(hire_date); existing.company_phone=company_phone; existing.personal_phone=personal_phone; existing.is_active=True; existing.deleted_at=None; existing.deleted_by=None
                log('RESTORE','Employee',existing.id,existing.full_name); db.session.commit()
                flash('تمت استعادة الموظف السابق وتحديث بياناته، مع الاحتفاظ بكل تاريخه وحركاته.')
                return redirect(url_for('card',i=existing.id))
            e=Employee(employee_code=None,email=email,full_name=name,branch_id=bid,job_title=job_title,job_code=job_code,hire_date=parse_date(hire_date),company_phone=company_phone,personal_phone=personal_phone); db.session.add(e); db.session.commit(); log('ADD','Employee',e.id,e.full_name); db.session.commit(); flash('تمت إضافة الموظف بنجاح. يمكنك الآن تسجيل أول حركة له.'); return redirect(url_for('card',i=e.id))
    # في شاشة الموظفين، المشرف يستطيع اختيار أي محافظة للبحث والاستعراض.
    # هذا لا يمنحه صلاحيات تعديل/حذف خارج نطاقه؛ عمليات التعديل والحذف تظل محكومة بدوال الصلاحيات.
    supervisor_search_all = 'مشرف محافظة' in roles() or 'Manager Application Support' in roles()
    search_branch_ids = [b.id for b in Branch.query.filter(Branch.is_active==True).all()] if supervisor_search_all else bs
    branches=Branch.query.filter(Branch.id.in_(search_branch_ids),Branch.is_active==True).order_by(Branch.name).all() if search_branch_ids else []
    q=request.args.get('q','').strip()
    employee_filter=request.args.get('employee_id','').strip()
    branch_filter=request.args.get('branch_id','').strip()
    allowed_search_branch_ids=set(search_branch_ids)
    gov_filter=request.args.get('governorate_id','').strip()
    query=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(search_branch_ids)) if search_branch_ids else Employee.query.filter(False)
    if q:
        like=f'%{q}%'; query=query.filter(db.or_(Employee.full_name.ilike(like),Employee.job_code.ilike(like),Employee.job_title.ilike(like)))
    if branch_filter.isdigit() and int(branch_filter) in allowed_search_branch_ids:
        query=query.filter(Employee.branch_id==int(branch_filter))
    rows=query.order_by(Employee.full_name).all()
    govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if supervisor_search_all else (Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all() if gids() else [])
    allowed_search_gov_ids={g.id for g in govs}
    if gov_filter.isdigit() and int(gov_filter) in allowed_search_gov_ids:
        branches=Branch.query.filter(Branch.governorate_id==int(gov_filter),Branch.is_active==True,Branch.id.in_(search_branch_ids)).order_by(Branch.name).all()
        if not (branch_filter.isdigit() and int(branch_filter) in [b.id for b in branches]): branch_filter=''
        query=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_([b.id for b in branches]))
        if q:
            like=f'%{q}%'; query=query.filter(db.or_(Employee.full_name.ilike(like),Employee.job_code.ilike(like),Employee.job_title.ilike(like)))
        rows=query.order_by(Employee.full_name).all()
    if employee_filter.isdigit():
        eid=int(employee_filter)
        rows=[e for e in rows if e.id==eid]
    # المدخل الأول المسؤول عن كل موظف: يُحسب من فروع المسؤولية التنظيمية،
    # مع الاحتفاظ بسجل موظف واحد وعدم إنشاء سجل إضافي للمدخل.
    entry_map={}
    if rows:
        row_ids={e.id for e in rows}
        assignments=EntryAssignment.query.filter(EntryAssignment.employee_id.in_(row_ids),EntryAssignment.is_active==True).all()
        for a in assignments:
            entry_map[a.employee_id]=a.employee.full_name if a.employee else ''

    # عرض جميع المحافظات في قائمة البحث للحسابات ذات النطاق الشامل،
    # بينما تبقى نتائج الموظفين نفسها محكومة بصلاحيات/nطاق الحساب.
    filter_govs = Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if (supervisor_search_all or 'مسؤول التطبيق' in roles() or 'Manager Application Support' in roles()) else govs
    # محافظة الإضافة تبقى مقيدة بنطاق الإدارة للمستخدم، بينما قائمة البحث يمكن أن تشمل كل المحافظات للمشرف.
    add_govs = Governorate.query.filter(Governorate.id.in_(gids()), Governorate.is_active==True).order_by(Governorate.name).all() if gids() else []
    add_branch_ids = {b.id for b in Branch.query.filter(Branch.governorate_id.in_([g.id for g in add_govs]), Branch.is_active==True).all()} if add_govs else set()
    add_branches = Branch.query.filter(Branch.id.in_(add_branch_ids), Branch.is_active==True).order_by(Branch.name).all() if add_branch_ids else []
    return render_template('employees.html',rows=rows,bs=branches,add_govs=add_govs,add_bs=add_branches,q=q,govs=filter_govs,gov_filter=gov_filter,entry_map=entry_map)
@app.get('/employees/edit-data')
@req
def employee_edit_data():
    if not can('manage_employees'): abort(403)
    bs=bids()
    rows=Employee.query.join(Branch, Employee.branch_id==Branch.id).filter(Employee.is_active==True,Branch.is_active==True,Employee.branch_id.in_(bs)).order_by(Employee.full_name).all() if bs else []
    q=request.args.get('q','').strip()
    if q:
        ql=q.lower()
        rows=[e for e in rows if ql in (e.full_name or '').lower() or ql in (e.job_code or '').lower() or ql in (e.email or '').lower()]
    return render_template('employee_edit_data.html',rows=rows,q=q)

@app.route('/employees/<int:i>/edit',methods=['GET','POST'])
@req
def employee_edit(i):
    e=db.session.get(Employee,i)
    if not e or e.deleted_at is not None or not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if request.method=='POST':
        bid=int(request.form['branch_id'])
        if not branch_ok(bid): abort(403)
        submitted_gid=int(request.form.get('governorate_id','0')) if request.form.get('governorate_id','').isdigit() else 0
        branch_obj=db.session.get(Branch,bid)
        if not branch_obj or branch_obj.governorate_id!=submitted_gid: flash('يجب اختيار فرع تابع للمحافظة المحددة.'); return redirect(url_for('employee_edit',i=i))
        name=request.form.get('full_name','').strip(); email=request.form.get('email','').strip(); job_title=request.form.get('job_title','').strip(); job_code=request.form.get('job_code','').strip(); hire_date=request.form.get('hire_date','').strip(); company_phone=request.form.get('company_phone','').strip(); personal_phone=request.form.get('personal_phone','').strip()
        if not all([name,email,job_title,job_code,hire_date,company_phone,personal_phone]): flash('جميع بيانات الموظف مطلوبة.'); return redirect(url_for('employee_edit',i=i))
        if not valid_email(email): flash('البريد الإلكتروني مطلوب ويجب أن يكون بصيغة صحيحة.'); return redirect(url_for('employee_edit',i=i))
        dup=Employee.query.filter(Employee.email==email,Employee.id!=i).first()
        if dup: flash('البريد الإلكتروني مستخدم بالفعل لموظف آخر.'); return redirect(url_for('employee_edit',i=i))
        if not parse_date(hire_date): flash('تاريخ التعيين مطلوب وبصيغة صحيحة.'); return redirect(url_for('employee_edit',i=i))
        e.full_name=name; e.email=email; e.branch_id=bid; e.job_title=job_title; e.job_code=job_code
        if e.user_id:
            linked_user=db.session.get(User,e.user_id)
            if linked_user:
                other=User.query.filter(User.email==email,User.id!=linked_user.id).first()
                if other: flash('البريد الإلكتروني مستخدم بالفعل لحساب آخر.'); return redirect(url_for('employee_edit',i=i))
                linked_user.email=email; linked_user.full_name=name; linked_user.job_title=job_title; linked_user.job_code=job_code
        e.hire_date=parse_date(hire_date); e.company_phone=company_phone; e.personal_phone=personal_phone; log('EDIT','Employee',i,e.full_name); db.session.commit(); flash('تم تعديل الموظف.'); return redirect(url_for('employees'))
    return render_template('employee_edit.html',e=e,bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all(),govs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all())
@app.route('/employees/<int:i>/convert-role', methods=['GET','POST'])
@req
@only('مسؤول التطبيق')
def employee_convert_role(i):
    e=db.session.get(Employee,i)
    if not e or not e.is_active: abort(404)
    assignment=organizational_entry_for_employee(e)
    is_entry=bool(assignment)
    if request.method=='POST':
        action=request.form.get('action')
        if action=='to_entry':
            branch_ids={int(x) for x in request.form.getlist('branch_id') if x.isdigit()}
            allowed_branch_ids={b.id for b in Branch.query.filter_by(is_active=True).all()}
            branch_ids &= allowed_branch_ids
            if not branch_ids:
                flash('يجب اختيار فرع واحد على الأقل ضمن فروع مسؤولية المدخل الأول.')
                return redirect(url_for('employee_convert_role',i=i))
            sup_id=request.form.get('supervisor_id','').strip()
            sup=db.session.get(User,int(sup_id)) if sup_id.isdigit() else None
            gov_ids={b.governorate_id for b in Branch.query.filter(Branch.id.in_(branch_ids),Branch.is_active==True).all()}
            if not sup or 'مشرف محافظة' not in actual_roles(sup) or not sup.is_active or not (gov_ids & user_gov_ids(sup)):
                flash('يجب اختيار مشرف محافظة صحيح لفروع المسؤولية.')
                return redirect(url_for('employee_convert_role',i=i))
            # الدور هنا تنظيمي فقط: لا ننشئ اسم مستخدم أو كلمة مرور جديدة.
            if assignment:
                assignment.supervisor_id=sup.id
                assignment.is_active=True
                EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).delete()
            else:
                assignment=EntryAssignment(employee_id=e.id,supervisor_id=sup.id,is_active=True)
                db.session.add(assignment)
                db.session.flush()
            for bid in sorted(branch_ids):
                db.session.add(EntryAssignmentBranch(entry_assignment_id=assignment.id,branch_id=bid))
            # توافق مع البيانات القديمة: إذا كان للموظف حساب دخول قديم يحمل دور المدخل الأول،
            # أزل الدور القديم فقط ولا تحذف الحساب إذا كان له أدوار أخرى.
            if e.user_id:
                old_user=db.session.get(User,e.user_id)
                if old_user and 'المدخل الأول' in actual_roles(old_user):
                    UserRole.query.filter_by(user_id=old_user.id,role='المدخل الأول').delete()
                    UserBranch.query.filter_by(user_id=old_user.id).delete()
                    SupervisorEntry.query.filter_by(entry_id=old_user.id).delete()
                    if not actual_roles(old_user):
                        old_user.is_active=False
                    sync_role_accounts(old_user)
            log('ROLE_CHANGE','Employee',e.id,'تحويل الموظف إلى مدخل أول تنظيمي بدون حساب دخول')
            db.session.commit()
            flash('تم تحويل الموظف إلى مدخل أول تنظيمي مع الاحتفاظ بسجل الموظف وفرع التعيين والحركات السابقة.')
            return redirect(url_for('employee_edit',i=e.id))
        if action=='to_employee':
            if not assignment:
                flash('الموظف ليس مدخلًا أول.')
                return redirect(url_for('employee_convert_role',i=i))
            EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).delete()
            db.session.delete(assignment)
            # تنظيف أي ارتباطات قديمة مرتبطة بحساب سابق لهذا الموظف دون حذف الموظف أو تاريخه.
            if e.user_id:
                old_user=db.session.get(User,e.user_id)
                if old_user and 'المدخل الأول' in actual_roles(old_user):
                    UserRole.query.filter_by(user_id=old_user.id,role='المدخل الأول').delete()
                    UserBranch.query.filter_by(user_id=old_user.id).delete()
                    SupervisorEntry.query.filter_by(entry_id=old_user.id).delete()
                    if not actual_roles(old_user):
                        old_user.is_active=False
                    sync_role_accounts(old_user)
            log('ROLE_CHANGE','Employee',e.id,'إرجاع المدخل الأول التنظيمي إلى موظف عادي')
            db.session.commit()
            flash('تم إرجاع الموظف إلى موظف عادي مع الاحتفاظ بكل بياناته وحركاته. لم تُحذف الفروع أو الموظفون التابعون له.')
            return redirect(url_for('employee_edit',i=e.id))
    branches=Branch.query.filter_by(is_active=True).order_by(Branch.name).all()
    supervisors=[u for u in User.query.filter_by(is_active=True).order_by(User.full_name).all() if 'مشرف محافظة' in actual_roles(u)]
    current_branch_ids={x.branch_id for x in EntryAssignmentBranch.query.filter_by(entry_assignment_id=assignment.id).all()} if assignment else set()
    current_sup=assignment.supervisor if assignment else None
    return render_template('employee_role_convert.html',e=e,is_entry=is_entry,branches=branches,supervisors=supervisors,current_branch_ids=current_branch_ids,current_sup=current_sup)

@app.post('/employees/<int:i>/toggle')
@req
def et(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if e.deleted_at is not None:
        flash('الموظف محذوف. استخدم صفحة الموظفين المحذوفين لاستعادته.')
    else:
        e.is_active=not e.is_active; log('TOGGLE','Employee',i)
        db.session.commit()
    return redirect('/employees')
@app.post('/employees/<int:i>/delete')
@req
def ed(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if not e: abort(404)
    # حذف منطقي: لا نحذف سجل الموظف أو حركاته، بل نضعه في حالة (محذوف).
    # نلتقط التكليف التنظيمي قبل تعطيل الموظف حتى يمكن تحرير فروع مسؤوليته.
    assignment=organizational_entry_for_employee(e)
    e.is_active=False
    e.deleted_at=datetime.utcnow()
    e.deleted_by=me().id if me() else None
    if assignment:
        assignment.is_active=False
    # دعم السجلات القديمة التي كان فيها المدخل الأول حسابًا: إزالة دوره التنظيمي فقط،
    # مع إبقاء حساب المستخدم وأي أدوار أخرى محفوظة.
    if e.user_id:
        linked_user=db.session.get(User,e.user_id)
        if linked_user:
            UserRole.query.filter_by(user_id=linked_user.id,role='المدخل الأول').delete()
            UserBranch.query.filter_by(user_id=linked_user.id).delete()
            SupervisorEntry.query.filter_by(entry_id=linked_user.id).delete()
    log('DELETE','Employee',i,f'حذف منطقي للموظف: {e.full_name}')
    db.session.commit()
    flash('تم حذف الموظف منطقيًا. بقي سجله وحركاته محفوظة وتم وضع علامة «محذوف».')
    return redirect(url_for('employees'))

@app.get('/employees/deleted')
@req
def deleted_employees():
    if not can('manage_employees'): abort(403)
    bs=bids()
    rows=(Employee.query.filter(Employee.deleted_at.isnot(None),Employee.branch_id.in_(bs)).order_by(Employee.deleted_at.desc(),Employee.full_name).all() if bs else [])
    return render_template('employee_deleted.html',rows=rows)

@app.post('/employees/<int:i>/restore')
@req
def employee_restore(i):
    e=db.session.get(Employee,i)
    if not e or e.deleted_at is None: abort(404)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    e.is_active=True
    e.deleted_at=None
    e.deleted_by=None
    log('RESTORE','Employee',i,f'استعادة الموظف: {e.full_name}')
    db.session.commit()
    flash('تمت استعادة الموظف مع الاحتفاظ بسجله وحركاته.')
    return redirect(url_for('deleted_employees'))
@app.get('/employee/<int:i>')
@req
def card(i):
    e=db.session.get(Employee,i)
    if not e or not branch_ok(e.branch_id): abort(403)
    ms=Movement.query.filter_by(employee_id=i,is_active=True).order_by(Movement.from_date.desc().nullslast(),Movement.permission_date.desc().nullslast(),Movement.id.desc()).all(); last={k:next((m for m in ms if m.movement_type==k),None) for k in MOVEMENT_TYPES}; return render_template('employee.html',e=e,ms=ms,last=last)

@app.get('/review')
@req
def review():
    if not can('review_movements') or not has_role('مسؤول التطبيق','مشرف محافظة'):
        abort(403)
    bs=bids()
    q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True) if bs else Movement.query.filter(False)
    tab=request.args.get('tab','pending')
    today=date.today()
    tomorrow=today + timedelta(days=ASSIGNMENT_ALERT_DAYS)
    if tab=='approved':
        rows=q.filter(Movement.status=='معتمدة').order_by(Movement.approved_at.desc(),Movement.id.desc()).all()
    elif tab=='rejected':
        rows=q.filter(Movement.status=='مرفوضة').order_by(Movement.reviewed_at.desc(),Movement.id.desc()).all()
    elif tab=='assignments':
        # متابعة المأموريات: قائمة متابعة قابلة للبحث والتصفية.
        # بدون فلاتر تاريخية إضافية تبقى قاعدة المتابعة الحالية: انتهت أو تنتهي اليوم/غدًا.
        assignment_q=q.filter(
            Movement.movement_type=='انتداب',
            Movement.to_date!=None
        )
        search=request.args.get('q','').strip()
        status_filter=request.args.get('status','').strip()
        state_filter=request.args.get('state','').strip()
        date_from=parse_date(request.args.get('date_from')) if request.args.get('date_from') else None
        date_to=parse_date(request.args.get('date_to')) if request.args.get('date_to') else None
        if search:
            like=f'%{search}%'
            assignment_q=assignment_q.filter((Employee.full_name.ilike(like)) | (Employee.job_code.ilike(like)) | (Employee.job_title.ilike(like)))
        if status_filter in STATUSES:
            assignment_q=assignment_q.filter(Movement.status==status_filter)
        if state_filter in ASSIGNMENT_STATES:
            assignment_q=assignment_q.filter(Movement.assignment_state==state_filter)
        if date_from:
            assignment_q=assignment_q.filter(Movement.to_date>=date_from)
        if date_to:
            assignment_q=assignment_q.filter(Movement.from_date<=date_to)
        if not date_from and not date_to:
            assignment_q=assignment_q.filter(Movement.to_date<=tomorrow)
        rows=assignment_q.order_by(Movement.to_date.asc(),Movement.id.desc()).all()
    else:
        tab='pending'
        rows=q.filter(Movement.status=='تحت المراجعة').filter((Movement.approver_id==me().id) if 'مسؤول التطبيق' not in roles() else True).order_by(Movement.modified_at.desc(),Movement.id.desc()).all()
    counts={
        'pending':(q.filter(Movement.status=='تحت المراجعة').filter((Movement.approver_id==me().id) if 'مسؤول التطبيق' not in roles() else True).count()),
        'approved':q.filter(Movement.status=='معتمدة').count(),
        'rejected':q.filter(Movement.status=='مرفوضة').count(),
        'assignments':q.filter(
            Movement.movement_type=='انتداب',
            Movement.to_date!=None,
            Movement.to_date<=tomorrow
        ).count(),
    }
    approved_ids={m.approved_by for m in rows if m.approved_by}
    approved_people={u.id:u for u in User.query.filter(User.id.in_(approved_ids)).all()} if approved_ids else {}
    return render_template('review.html',rows=rows,tab=tab,counts=counts,today=today,tomorrow=tomorrow,
                           assignment_search=request.args.get('q','').strip(),
                           assignment_status=request.args.get('status','').strip(),
                           assignment_state_filter=request.args.get('state','').strip(),
                           assignment_date_from=request.args.get('date_from','').strip(),
                           assignment_date_to=request.args.get('date_to','').strip(),
                           assignment_states=ASSIGNMENT_STATES, approved_people=approved_people)


# v34.91 — إصلاح نافذة المساعد العائمة داخل التطبيق وإزالة حجب X-Frame-Options.
def assistant_scope_employee_query():
    bs=bids()
    return Employee.query.filter(Employee.is_active==True, Employee.branch_id.in_(bs)).order_by(Employee.full_name).all() if bs else []

def assistant_find_employee(value):
    value=(value or '').strip()
    if not value: return None, []
    rows=assistant_scope_employee_query()
    exact=[e for e in rows if e.full_name.strip().lower()==value.lower() or (e.job_code and e.job_code.strip().lower()==value.lower())]
    if len(exact)==1: return exact[0], exact
    parts=[x for x in re.split(r'\s+',value.lower()) if len(x)>=2]
    matches=[e for e in rows if value.lower() in (e.full_name or '').lower() or (e.job_code and value.lower() in e.job_code.lower())]
    if not matches and parts:
        matches=[e for e in rows if all(part in (e.full_name or '').lower() for part in parts)]
    return (matches[0] if len(matches)==1 else None), matches

def assistant_find_branch(value, governorate_id=None):
    value=(value or '').strip()
    q=Branch.query.filter(Branch.is_active==True)
    if governorate_id: q=q.filter(Branch.governorate_id==governorate_id)
    allowed=set(bids())
    rows=q.filter(Branch.id.in_(allowed)).order_by(Branch.name).all() if allowed else []
    exact=[b for b in rows if b.name.strip().lower()==value.lower() or (b.code and b.code.strip().lower()==value.lower())]
    if len(exact)==1: return exact[0], exact
    matches=[b for b in rows if value.lower() in (b.name or '').lower() or (b.code and value.lower() in b.code.lower())]
    return (matches[0] if len(matches)==1 else None), matches

def assistant_normalize(text):
    trans=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')
    return (text or '').translate(trans).strip()

def assistant_parse_date(text):
    m=re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})', text or '')
    if not m: return None
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

def assistant_parse(text):
    t=assistant_normalize(text)
    # فهم لغوي مرن: نطبع الصيغ الشائعة ونفسر المقصود حتى لو لم يستخدم المستخدم
    # نفس تسمية الزر داخل التطبيق.
    low=t.lower()
    compact=re.sub(r'[\s_\-]+','',low)
    def has_any(*words):
        return any(w in t or w in low for w in words)
    # عبارات موضوعية مباشرة: أي صياغة تدل على الإجازة/الانتداب/الإذن/المدخل الأول.
    leave_words=('إجازة','اجازة','اجازات','الإجازات','الاجازات','عطلة','عطلات')
    assign_words=('انتداب','انتدابات','مأمورية','مأموريات')
    perm_words=('إذن','اذن','أذونات','اذونات')
    entry_words=('مدخل أول','مدخل الاول','مدخل الأول','المدخل الأول','المدخل الاول','مدخلين أوائل','المدخلين الأوائل')
    action_words=('سجل','تسجيل','سجّل','ادخل','إدخال','أدخل','اضف','أضف','إضافة','اعمل','عمل','نفذ','تنفيذ','عين','تعيين')
    query_words=('حالة','اعرض','عرض','استعلم','استعلام','اسم','من هو','مين','موظفين','الموظفون','الموظفين','بيانات','سجل')
    # استعلام ذكي عن المدخل الأول المسؤول عن فرع محدد.
    if has_any(*entry_words) and has_any('فرع','الفرع') and has_any('اسم','من هو','مين','مسؤول','مسئول','يتبع'):
        bm=re.search(r'(?:فرع|الفرع)\s+([^؟?،,؛\n]+)',t)
        name=bm.group(1).strip() if bm else ''
        br,matches=assistant_find_branch(name)
        return {'intent':'branch_entry','branch_id':br.id if br else None,'branch_name':name,'candidate_ids':[b.id for b in matches[:10]]}
    # إذا ذكر المستخدم موظفي فرع/العاملين بفرع، فهو استعلام عن موظفي الفرع حتى لو لم يقل
    # حرفيًا "حالة الفرع".
    if (has_any('موظفي','الموظفين','الموظفون','العاملين','العاملون','موظفين') and has_any('فرع','الفرع')):
        bm=re.search(r'(?:فرع|الفرع)\s+([^؟?،,؛\n]+)',t)
        name=bm.group(1).strip() if bm else ''
        br,matches=assistant_find_branch(name)
        return {'intent':'branch_status','branch_id':br.id if br else None,'branch_name':name,'candidate_ids':[b.id for b in matches[:10]]}
    # صياغات مثل "إدخال إجازة" و"إضافة إجازة" و"اعمل إجازة" تعني تسجيل إجازة.
    if has_any(*leave_words) and has_any(*action_words):
        mt='إجازة'
    elif has_any(*assign_words) and has_any(*action_words):
        mt='انتداب'
    elif has_any(*perm_words) and has_any(*action_words):
        mt='إذن'
    else:
        mt=None
    if mt:
        em=re.search(r'(?:للموظف|لـ|ل |الموظف|موظف)\s*([^،,؛\n]+?)(?=\s+(?:من|بتاريخ|في|إجازة|اجازة|انتداب|إذن|اذن)|$)',t,re.I)
        name=em.group(1).strip() if em else ''
        emp,matches=assistant_find_employee(name)
        dates=re.findall(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}',t)
        fd=assistant_parse_date(dates[0]) if dates else None
        td=assistant_parse_date(dates[1]) if len(dates)>1 else fd
        pd=assistant_parse_date(dates[0]) if dates else None
        leave_type=None
        if mt=='إجازة':
            for x in active_leave_types():
                if x in t: leave_type=x; break
            if not leave_type and has_any('سنوي','سنوية'): leave_type='سنوية'
        dest=None
        if mt=='انتداب':
            dm=re.search(r'(?:إلى|الى|لـ|لفرع|إلى فرع|الى فرع)\s+(?:فرع\s+)?([^،,؛\n]+?)(?=\s+(?:من|بتاريخ)|$)',t,re.I)
            if dm: dest,_=assistant_find_branch(dm.group(1).strip())
        return {'intent':'register_movement','movement_type':mt,'employee_id':emp.id if emp else None,'employee_name':name,'candidate_ids':[e.id for e in matches[:10]],'leave_type':leave_type,'destination_branch_id':dest.id if dest else None,'destination_name':dest.name if dest else '','from_date':fd,'to_date':td,'permission_date':pd if mt=='إذن' else None}
    # كلمة الموضوع وحدها أو مع صياغة غير مكتملة تعرض خيارات الموضوع.
    if has_any(*entry_words) and not has_any('فرع','الفرع'):
        return {'intent':'topic_options','topic':'entry'}
    if has_any(*leave_words) and not mt:
        return {'intent':'topic_options','topic':'leave'}
    if has_any(*assign_words) and not mt:
        return {'intent':'topic_options','topic':'assignment'}
    if has_any(*perm_words) and not mt:
        return {'intent':'topic_options','topic':'permission'}
    # v34.89 — الكلمات المفتاحية تفتح مسار الموضوع بدل اعتبارها طلبًا نهائيًا.
    # مثال: "إجازة" يعرض كل ما يمكن فعله/الاستعلام عنه بخصوص الإجازات،
    # و"مدخل أول" يعرض الإجراءات والاستعلامات الخاصة بالمدخل الأول، وفق الصلاحيات.
    if low.strip() in ('اجازة','إجازة','الإجازة','الاجازات','الإجازات'):
        return {'intent':'topic_options','topic':'leave'}
    if low.strip() in ('انتداب','الانتداب','مأمورية','المأمورية'):
        return {'intent':'topic_options','topic':'assignment'}
    if low.strip() in ('اذن','إذن','الأذن','الاذونات','الأذونات'):
        return {'intent':'topic_options','topic':'permission'}
    if low.strip() in ('مدخل اول','مدخل أول','المدخل الاول','المدخل الأول','مدخل أولاً','المدخل الاول'):
        return {'intent':'topic_options','topic':'entry'}
    if any(x in t for x in ['سجل حركة','سجل له','سجل للموظف','تسجيل إجازة','تسجيل انتداب','تسجيل اذن','تسجيل إذن','اضف إجازة','أضف إجازة','اضف انتداب','أضف انتداب','اضف اذن','أضف إذن']):
        mt='إجازة' if 'إجازة' in t or 'اجازة' in t else ('انتداب' if 'انتداب' in t or 'مأمورية' in t else 'إذن')
        if mt=='إجازة': mt='إجازة'
        if mt=='إذن': mt='إذن'
        em=re.search(r'(?:للموظف|لـ|ل )\s*([^،,؛\n]+?)(?=\s+(?:من|بتاريخ|في|إجازة|اجازة|انتداب|إذن|اذن)|$)',t,re.I)
        name=em.group(1).strip() if em else ''
        emp,matches=assistant_find_employee(name)
        dates=re.findall(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}',t)
        if mt in ('إجازة','انتداب'):
            fd=assistant_parse_date(dates[0]) if dates else None
            td=assistant_parse_date(dates[1]) if len(dates)>1 else fd
        else:
            pd=assistant_parse_date(dates[0]) if dates else None
            fd=td=None
        leave_type=None
        if mt=='إجازة':
            for x in active_leave_types():
                if x in t: leave_type=x; break
            if not leave_type:
                leave_type='سنوية' if 'سنوي' in t else None
        dest=None
        if mt=='انتداب':
            dm=re.search(r'(?:إلى|الى)\s+(?:فرع\s+)?([^،,؛\n]+?)(?=\s+(?:من|بتاريخ)|$)',t,re.I)
            if dm:
                dest,_=assistant_find_branch(dm.group(1).strip())
        return {'intent':'register_movement','movement_type':mt,'employee_id':emp.id if emp else None,'employee_name':name,'candidate_ids':[e.id for e in matches[:10]],'leave_type':leave_type,'destination_branch_id':dest.id if dest else None,'destination_name':dest.name if dest else '','from_date':fd,'to_date':td,'permission_date':pd if mt=='إذن' else None}
    if any(x in t for x in ['سجل حركات','تاريخ حركات','حركات الموظف','حركات موظف']):
        em=re.search(r'(?:الموظف|موظف)\s+([^؟?،,؛\n]+)',t)
        name=em.group(1).strip() if em else t
        emp,matches=assistant_find_employee(name)
        return {'intent':'employee_movements','employee_id':emp.id if emp else None,'employee_name':name,'candidate_ids':[e.id for e in matches[:10]]}
    if any(x in t for x in ['حالة موظفي','موظفي فرع','حالة الفرع','حالة موظفين']):
        bm=re.search(r'(?:فرع)\s+([^؟?،,؛\n]+)',t)
        name=bm.group(1).strip() if bm else ''
        br,matches=assistant_find_branch(name)
        return {'intent':'branch_status','branch_id':br.id if br else None,'branch_name':name,'candidate_ids':[b.id for b in matches[:10]]}
    if any(x in t for x in ['حالة الموظف','ما حالة','حاله الموظف','حالة']):
        em=re.search(r'(?:الموظف|موظف)\s+([^؟?،,؛\n]+)',t)
        name=em.group(1).strip() if em else t.replace('ما حالة','').replace('حالة الموظف','').strip(' ؟?')
        emp,matches=assistant_find_employee(name)
        return {'intent':'employee_status','employee_id':emp.id if emp else None,'employee_name':name,'candidate_ids':[e.id for e in matches[:10]]}
    return {'intent':'help'}

def assistant_topic_options(topic):
    """Return contextual next-step choices for a keyword/topic, filtered by role permissions."""
    if topic=='leave':
        items=[
            {'label':'تسجيل إجازة','prompt':'تسجيل إجازة','icon':'🌿','kind':'action'},
            {'label':'تقرير الإجازات','prompt':'أريد تقرير الإجازات','icon':'📊','kind':'report'},
            {'label':'حالة إجازة موظف','prompt':'ما حالة إجازة الموظف ','icon':'👤','kind':'query'},
            {'label':'سجل إجازات موظف','prompt':'اعرض سجل حركات الموظف ','icon':'📋','kind':'query'},
        ]
        if not can('manage_movements'): items=[x for x in items if x['kind']!='action']
        if not can('view_reports'): items=[x for x in items if x['label'] not in ('تقرير الإجازات',)]
        return {'title':'خيارات الإجازات','answer':'اختر ما تريد بخصوص الإجازات، أو اكتب طلبك مباشرة.','topic_items':items}
    if topic=='assignment':
        items=[
            {'label':'تسجيل انتداب','prompt':'تسجيل انتداب','icon':'↔️','kind':'action'},
            {'label':'تقرير الانتدابات','prompt':'أريد تقرير الانتدابات','icon':'📊','kind':'report'},
            {'label':'حالة انتداب موظف','prompt':'اعرض حالة انتداب الموظف ','icon':'👤','kind':'query'},
            {'label':'سجل انتدابات موظف','prompt':'اعرض سجل حركات الموظف ','icon':'📋','kind':'query'},
            {'label':'طباعة المأموريات','prompt':'أريد طباعة المأموريات','icon':'🖨️','kind':'report'},
        ]
        if not can('manage_movements'): items=[x for x in items if x['kind']!='action']
        if not can('view_reports'): items=[x for x in items if x['kind']!='report']
        return {'title':'خيارات الانتداب','answer':'اختر الإجراء أو الاستعلام المطلوب بخصوص الانتدابات.','topic_items':items}
    if topic=='permission':
        items=[
            {'label':'تسجيل إذن','prompt':'تسجيل إذن','icon':'🕒','kind':'action'},
            {'label':'تقرير الأذونات','prompt':'أريد تقرير الأذونات','icon':'📊','kind':'report'},
            {'label':'سجل أذونات موظف','prompt':'اعرض سجل حركات الموظف ','icon':'📋','kind':'query'},
        ]
        if not can('manage_movements'): items=[x for x in items if x['kind']!='action']
        if not can('view_reports'): items=[x for x in items if x['kind']!='report']
        return {'title':'خيارات الأذونات','answer':'اختر ما تريد بخصوص الأذونات، أو اكتب طلبك مباشرة.','topic_items':items}
    if topic=='entry':
        items=[]
        if can('manage_structure'):
            items += [
                {'label':'تعيين مدخل أول','prompt':'أريد تعيين مدخل أول','icon':'👥','kind':'action'},
                {'label':'إزالة دور مدخل أول','prompt':'أريد إزالة دور مدخل أول','icon':'↩️','kind':'action'},
                {'label':'إدارة المدخلين الأوائل','prompt':'أريد إدارة المدخلين الأوائل','icon':'⚙️','kind':'action'},
                {'label':'فروع مسؤولية مدخل أول','prompt':'اعرض فروع مسؤولية مدخل أول','icon':'🏬','kind':'query'},
                {'label':'موظفو مدخل أول','prompt':'اعرض موظفي مدخل أول','icon':'👤','kind':'query'},
            ]
        if not items:
            items=[{'label':'عرض المدخل الأول','prompt':'اعرض بيانات المدخل الأول','icon':'👥','kind':'query'}]
        return {'title':'خيارات المدخل الأول','answer':'هذه الإجراءات والاستعلامات المتاحة لك بخصوص المدخل الأول.','topic_items':items}
    return {'title':'المساعد الذكي','answer':'اكتب الموضوع الذي تريد المساعدة فيه.'}

def assistant_render_branch_entry(a):
    br=db.session.get(Branch,a.get('branch_id')) if a.get('branch_id') else None
    if not br:
        matches=[db.session.get(Branch,i) for i in a.get('candidate_ids',[]) if db.session.get(Branch,i)]
        if len(matches)==1: br=matches[0]
        elif matches:
            return {'title':'تحديد الفرع','error':'وجدت أكثر من فرع مطابق. اختر الفرع المقصود.','choices':matches}
        else:
            return {'title':'تحديد الفرع','error':'لم أجد فرعًا مطابقًا. اكتب اسم الفرع بصورة أوضح.'}
    link=EntryAssignmentBranch.query.join(EntryAssignment).filter(EntryAssignmentBranch.branch_id==br.id,EntryAssignment.is_active==True).first()
    if not link or not link.assignment or not link.assignment.employee:
        return {'title':'مدخل أول الفرع','answer':f'الفرع: {br.name} — لا يوجد مدخل أول معين حاليًا لهذا الفرع.'}
    e=link.assignment.employee
    return {'title':'مدخل أول الفرع','answer':f'الفرع: {br.name}\nالمدخل الأول: {e.full_name}\nالمشرف: {link.assignment.supervisor.full_name if link.assignment.supervisor else "غير محدد"}'}

def assistant_status_for_employee(e):
    today=date.today()
    active=Movement.query.filter_by(employee_id=e.id,is_active=True).filter(
        ((Movement.movement_type.in_(['إجازة','انتداب'])) & (Movement.from_date<=today) & (Movement.to_date>=today)) |
        ((Movement.movement_type=='إذن') & (Movement.permission_date==today))
    ).order_by(Movement.id.desc()).all()
    if not active: return 'على رأس العمل'
    m=active[0]
    if m.movement_type=='إجازة': return f'إجازة — {m.leave_type or ""} — حتى {m.to_date}'
    if m.movement_type=='انتداب': return f'انتداب — {m.destination.name if m.destination else "غير محدد"} — حتى {m.to_date}'
    return 'إذن اليوم'

def assistant_render_read(a):
    intent=a.get('intent')
    if intent=='employee_status':
        e=db.session.get(Employee,a.get('employee_id')) if a.get('employee_id') else None
        if not e or not e.is_active or not branch_ok(e.branch_id):
            return {'title':'نتيجة البحث','error':'لم أجد موظفًا واحدًا مطابقًا.','choices':[db.session.get(Employee,i) for i in a.get('candidate_ids',[]) if db.session.get(Employee,i)]}
        return {'title':'حالة الموظف','answer':f'الموظف: {e.full_name}\nالفرع: {e.branch.name}\nالمحافظة: {e.branch.governorate.name}\nالحالة الآن: {assistant_status_for_employee(e)}'}
    if intent=='branch_status':
        b=db.session.get(Branch,a.get('branch_id')) if a.get('branch_id') else None
        if not b or not branch_ok(b.id):
            return {'title':'نتيجة البحث','error':'لم أجد فرعًا واحدًا مطابقًا.','choices':[db.session.get(Branch,i) for i in a.get('candidate_ids',[]) if db.session.get(Branch,i)]}
        employees=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
        lines=[f'{e.full_name} — {assistant_status_for_employee(e)}' for e in employees]
        return {'title':f'حالة موظفي فرع {b.name}','answer':f'المحافظة: {b.governorate.name}\nعدد الموظفين: {len(employees)}\n'+'\n'.join(lines)}
    if intent=='employee_movements':
        e=db.session.get(Employee,a.get('employee_id')) if a.get('employee_id') else None
        if not e or not branch_ok(e.branch_id):
            return {'title':'نتيجة البحث','error':'لم أجد موظفًا واحدًا مطابقًا.','choices':[db.session.get(Employee,i) for i in a.get('candidate_ids',[]) if db.session.get(Employee,i)]}
        ms=Movement.query.filter_by(employee_id=e.id,is_active=True).order_by(Movement.id.desc()).limit(30).all()
        if not ms: ans=f'{e.full_name}: لا توجد حركات مسجلة.'
        else:
            lines=[]
            for m in ms:
                detail=m.leave_type or (m.destination.name if m.destination else '') or ''
                period=m.permission_date or (f'{m.from_date} إلى {m.to_date}' if m.from_date or m.to_date else '')
                lines.append(f'{m.movement_type} — {detail} — {period} — {m.status}')
            ans=f'سجل حركات {e.full_name}:\n'+'\n'.join(lines)
        return {'title':'سجل حركات الموظف','answer':ans}
    return {'title':'المساعد الذكي','answer':'يمكنك أن تسأل مثلًا: ما حالة الموظف أحمد؟ أو ما حالة موظفي فرع المدينة؟ أو اعرض سجل حركات أحمد. ويمكنك طلب تسجيل إجازة أو انتداب أو إذن، وسيطلب منك تأكيد الحفظ.'}

@app.route('/assistant', methods=['GET','POST'])
@req
def assistant():
    result=None; prompt=''
    chat=session.get('assistant_chat', [])
    if request.method=='POST':
        prompt=(request.form.get('prompt') or '').strip()
        if prompt:
            chat.append({'role':'user','text':prompt})
        if not prompt:
            result={'title':'المساعد الذكي','error':'اكتب طلبك أولًا.'}
        else:
            a=assistant_parse(prompt)
            if a.get('intent')=='topic_options':
                result=assistant_topic_options(a.get('topic'))
            elif a.get('intent')=='register_movement':
                if not can('manage_movements'):
                    result={'title':'تسجيل حركة','error':'لا تملك صلاحية تسجيل الحركات.'}
                elif not a.get('employee_id'):
                    result={'title':'تحديد الموظف','error':'لم أستطع تحديد موظف واحد. اكتب الاسم بشكل أوضح.','choices':[db.session.get(Employee,i) for i in a.get('candidate_ids',[]) if db.session.get(Employee,i)]}
                else:
                    e=db.session.get(Employee,a['employee_id']); dest=db.session.get(Branch,a.get('destination_branch_id')) if a.get('destination_branch_id') else None
                    err=validate_movement_fields(a.get('movement_type'),a.get('leave_type'),dest.id if dest else None,a.get('from_date'),a.get('to_date'),a.get('permission_date'))
                    if err: result={'title':'مراجعة الحركة','error':err}
                    elif not e or not branch_ok(e.branch_id): result={'title':'تسجيل حركة','error':'الموظف خارج نطاق صلاحياتك.'}
                    elif a.get('movement_type')=='انتداب' and (not dest or not branch_ok(dest.id)): result={'title':'تسجيل انتداب','error':'فرع الانتداب غير موجود أو خارج نطاق صلاحياتك.'}
                    elif movement_overlaps(e.id,a['movement_type'],a.get('from_date'),a.get('to_date'),a.get('permission_date')): result={'title':'تعارض في الحركة','error':movement_overlaps(e.id,a['movement_type'],a.get('from_date'),a.get('to_date'),a.get('permission_date'))}
                    else:
                        session['assistant_pending']=a
                        dest_text=f' إلى {dest.governorate.name} — {dest.name}' if dest else ''
                        period=(f" من {a.get('from_date')} إلى {a.get('to_date')}" if a.get('from_date') else (f" بتاريخ {a.get('permission_date')}" if a.get('permission_date') else ''))
                        result={'title':'تأكيد تسجيل الحركة','preview':f"{a['movement_type']} للموظف {e.full_name}{dest_text}{period}"}
            else:
                if a.get('intent')=='branch_entry':
                    result=assistant_render_branch_entry(a)
                else:
                    result=assistant_render_read(a)
    if request.method=='POST' and prompt and result:
        assistant_text = result.get('answer') or result.get('error') or result.get('preview') or result.get('title') or 'تمت معالجة طلبك.'
        chat.append({'role':'assistant','text':assistant_text,'title':result.get('title','المساعد الذكي')})
        session['assistant_chat']=chat[-24:]
    # v34.88 — قائمة قدرات المساعد ديناميكية حسب صلاحيات الدور الحالي.
    # تعرض الاستعلامات والتنفيذات الممكنة، ولا تظهر وظائف لا يملك المستخدم صلاحيتها.
    assistant_options=[
        {'group':'استعلامات الموظفين','items':[
            {'label':'حالة موظف','prompt':'ما حالة الموظف ؟','icon':'👤','kind':'query'},
            {'label':'سجل حركات موظف','prompt':'اعرض سجل حركات الموظف ؟','icon':'📋','kind':'query'},
            {'label':'بيانات موظف','prompt':'اعرض بيانات الموظف ؟','icon':'🪪','kind':'query'},
        ]},
        {'group':'استعلامات الفروع والحركات','items':[
            {'label':'حالة فرع','prompt':'ما حالة موظفي فرع ؟','icon':'🏢','kind':'query'},
            {'label':'حالة الموظفين الآن','prompt':'اعرض حالة الموظفين الآن','icon':'📊','kind':'query'},
            {'label':'الحركات المنتهية قريبًا','prompt':'اعرض الحركات التي تنتهي قريبًا','icon':'⏳','kind':'query'},
        ]},
    ]
    if can('manage_movements'):
        assistant_options.append({'group':'تسجيل الحركات','items':[
            {'label':'إجازة','prompt':'تسجيل إجازة للموظف ','icon':'🌿','kind':'action'},
            {'label':'انتداب','prompt':'تسجيل انتداب للموظف ','icon':'↔️','kind':'action'},
            {'label':'إذن','prompt':'تسجيل إذن للموظف ','icon':'🕒','kind':'action'},
        ]})
    if can('manage_employees'):
        assistant_options.append({'group':'إدارة الموظفين','items':[
            {'label':'إضافة موظف','prompt':'أريد إضافة موظف','icon':'➕','kind':'action','url':'/employees'},
            {'label':'تعديل موظف','prompt':'أريد تعديل بيانات موظف','icon':'✏️','kind':'action','url':'/employees/edit-data'},
            {'label':'حذف موظف','prompt':'أريد حذف موظف','icon':'🗑️','kind':'action','url':'/employees'},
            {'label':'الموظفون المحذوفون','prompt':'اعرض الموظفين المحذوفين','icon':'♻️','kind':'query','url':'/employees/deleted'},
        ]})
    if can('manage_structure'):
        assistant_options.append({'group':'الإدارة التنظيمية','items':[
            {'label':'المحافظات','prompt':'أريد إدارة المحافظات','icon':'🗺️','kind':'action','url':'/governorates'},
            {'label':'الفروع','prompt':'أريد إدارة الفروع','icon':'🏬','kind':'action','url':'/branches'},
            {'label':'المدخل الأول','prompt':'أريد إدارة المدخلين الأوائل','icon':'👥','kind':'action','url':'/structure'},
            {'label':'الاستبدال','prompt':'أريد تنفيذ الاستبدال','icon':'🔁','kind':'action','url':'/replacement'},
        ]})
    if can('manage_users'):
        assistant_options.append({'group':'المستخدمون والصلاحيات','items':[
            {'label':'المستخدمون','prompt':'أريد إدارة المستخدمين','icon':'👤','kind':'action','url':'/users'},
            {'label':'الأدوار والصلاحيات','prompt':'أريد إدارة الأدوار والصلاحيات','icon':'🔐','kind':'action','url':'/users'},
            {'label':'تفويض الاعتماد','prompt':'أريد إدارة تفويضات الاعتماد','icon':'🤝','kind':'action','url':'/delegations'},
        ]})
    if can('review_movements'):
        assistant_options.append({'group':'المراجعة والاعتماد','items':[
            {'label':'مراجعة الحركات','prompt':'أريد مراجعة واعتماد الحركات','icon':'✅','kind':'action','url':'/review'},
        ]})
    if can('cancel_approval'):
        assistant_options.append({'group':'الاعتماد','items':[
            {'label':'إلغاء اعتماد','prompt':'أريد إلغاء اعتماد حركة','icon':'↩️','kind':'action','url':'/review'},
        ]})
    if can('delete_movements'):
        assistant_options.append({'group':'حذف الحركات','items':[
            {'label':'حذف حركة','prompt':'أريد حذف حركة','icon':'🗑️','kind':'action','url':'/movements'},
        ]})
    if can('view_reports'):
        assistant_options.append({'group':'التقارير والطباعة','items':[
            {'label':'تقرير الإجازات','prompt':'أريد تقرير الإجازات','icon':'🌿','kind':'report','url':'/reports/leaves'},
            {'label':'تقرير الانتدابات','prompt':'أريد تقرير الانتدابات','icon':'↔️','kind':'report','url':'/reports/assignments'},
            {'label':'تقرير الأذونات','prompt':'أريد تقرير الأذونات','icon':'🕒','kind':'report','url':'/reports/permissions'},
            {'label':'طباعة المأموريات','prompt':'أريد طباعة المأموريات','icon':'🖨️','kind':'report','url':'/reports/assignments/print-missions'},
        ]})
    if can('view_audit'):
        assistant_options.append({'group':'المتابعة','items':[
            {'label':'سجل العمليات','prompt':'أريد سجل العمليات','icon':'🧾','kind':'query','url':'/audit'},
            {'label':'القوائم الأساسية','prompt':'أريد إدارة القوائم الأساسية','icon':'⚙️','kind':'action','url':'/lookups'},
        ]})
    # Flatten for the existing template while retaining grouping metadata.
    assistant_option_groups=assistant_options
    assistant_options=[item for group in assistant_option_groups for item in group['items']]
    embed=request.args.get('embed')=='1'
    template='assistant_embed.html' if embed else 'assistant.html'
    return render_template(template,result=result,prompt=prompt,assistant_options=assistant_options,assistant_option_groups=assistant_option_groups,embed=embed,chat=session.get('assistant_chat',[]))


@app.post('/assistant/clear')
@req
def assistant_clear():
    session.pop('assistant_chat', None)
    session.pop('assistant_pending', None)
    return redirect('/assistant?embed=1' if request.form.get('embed')=='1' else '/assistant')


@app.post('/assistant/confirm')
@req
def assistant_confirm():
    embed=request.form.get('embed')=='1'
    back='/assistant?embed=1' if embed else '/assistant'
    a=session.pop('assistant_pending',None)
    if not a: flash('لا توجد حركة معلقة للتأكيد.'); return redirect(back)
    if not can('manage_movements'): abort(403)
    e=db.session.get(Employee,a.get('employee_id')); dest=db.session.get(Branch,a.get('destination_branch_id')) if a.get('destination_branch_id') else None
    if not e or not e.is_active or not branch_ok(e.branch_id): flash('الموظف خارج نطاق صلاحياتك.'); return redirect(back)
    err=validate_movement_fields(a.get('movement_type'),a.get('leave_type'),dest.id if dest else None,a.get('from_date'),a.get('to_date'),a.get('permission_date'))
    if err: flash(err); return redirect(back)
    if a.get('movement_type')=='انتداب' and (not dest or not branch_ok(dest.id)): flash('فرع الانتداب غير مسموح.'); return redirect(back)
    overlap=movement_overlaps(e.id,a['movement_type'],a.get('from_date'),a.get('to_date'),a.get('permission_date'))
    if overlap: flash(overlap); return redirect(back)
    m=Movement(employee_id=e.id,movement_type=a['movement_type'],leave_type=a.get('leave_type'),destination_branch_id=dest.id if dest else None,from_date=parse_date(a.get('from_date')),to_date=parse_date(a.get('to_date')),permission_date=parse_date(a.get('permission_date')),notes=None,created_by=me().id,status='مدخلة',assignment_state='ساري',approver_id=None)
    db.session.add(m); db.session.flush(); record_movement_history(m,None,'مدخلة','AI_ASSISTANT_ADD','تسجيل الحركة من المساعد الذكي — لا تحتاج لاعتماد'); log('AI_ASSISTANT_ADD','Movement',m.id,f'{m.movement_type} — {e.full_name}'); db.session.commit(); flash('تم تسجيل الحركة بنجاح من خلال المساعد الذكي.'); return redirect(back)

@app.route('/movements',methods=['GET','POST'])
@req
def movements():
    bs=bids()
    if request.method=='POST' and (not can_manage_movement() or not can('manage_movements')): abort(403)
    emps=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)).order_by(Employee.full_name).all() if bs else []
    if request.method=='POST':
        f=request.form; eid=int(f.get('employee_id','0')) if f.get('employee_id','').isdigit() else 0; e=db.session.get(Employee,eid)
        if not e or not branch_ok(e.branch_id): abort(403)
        mt=f.get('movement_type'); fd=f.get('from_date'); td=f.get('to_date'); pd=f.get('permission_date'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id','').isdigit() else None; status='مدخلة'; approver_id=None
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,fd,td,pd)
        if err: flash(err); return redirect('/movements')
        overlap=movement_overlaps(e.id,mt,fd,td,pd)
        if overlap: flash(overlap); return redirect('/movements')
        m=Movement(employee_id=e.id,movement_type=mt,leave_type=f.get('leave_type') or None,destination_branch_id=dest,from_date=parse_date(fd),to_date=parse_date(td),permission_date=parse_date(pd),notes=None,created_by=me().id,status=status,assignment_state='ساري',approver_id=None); db.session.add(m); db.session.commit(); record_movement_history(m,None,status,'ADD','تسجيل الحركة — لا تحتاج لاعتماد'); log('ADD','Movement',m.id,status); db.session.commit(); flash('تم تسجيل الحركة وأصبحت ظاهرة مباشرة في متابعة الموظفين.')
    rows=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True).order_by(Movement.created_at.desc()).all() if bs else []
    selected_employee_id=request.args.get('employee_id', type=int)
    return render_template('movements.html',rows=rows,emps=emps,bs=Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True).all() if bs else [],leave_types=active_leave_types(),movement_types=active_movement_types(),statuses=STATUSES,selected_employee_id=selected_employee_id,approvers={e.id:approvers_for_employee(e) for e in emps})
@app.route('/movements/<int:i>/edit',methods=['GET','POST'])
@req
def movement_edit(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    # الحركات معلومات تشغيلية مباشرة ويمكن تعديلها دون انتظار اعتماد.
    last_history=MovementHistory.query.filter_by(movement_id=i).order_by(MovementHistory.id.desc()).first()
    dates_edit_after_cancel=False
    if not can_manage_movement(m) or not can('manage_movements'):
        abort(403)
    if request.method=='POST':
        f=request.form
        mt=f.get('movement_type'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id','').isdigit() else None
        approver_id=None
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,f.get('from_date'),f.get('to_date'),f.get('permission_date'))
        if err: flash(err); return redirect(url_for('movement_edit',i=i))
        overlap=movement_overlaps(m.employee_id,mt,f.get('from_date'),f.get('to_date'),f.get('permission_date'),i)
        if overlap: flash(overlap); return redirect(url_for('movement_edit',i=i))
        old_status=m.status
        m.movement_type=mt; m.leave_type=f.get('leave_type') or None; m.destination_branch_id=dest; m.from_date=parse_date(f.get('from_date')); m.to_date=parse_date(f.get('to_date')); m.permission_date=parse_date(f.get('permission_date')); m.approver_id=None; m.notes=None; m.modified_by=me().id; m.modified_at=datetime.utcnow(); m.status='مدخلة'; m.rejection_reason=None; record_movement_history(m,old_status,'مدخلة','EDIT','تعديل بيانات الحركة — لا تحتاج لاعتماد'); log('EDIT','Movement',i,'تعديل الحركة'); db.session.commit(); flash('تم تعديل الحركة وحفظها مباشرة.'); return redirect('/movements')
    return render_template('movement_edit.html',m=m,emps=Employee.query.filter(Employee.branch_id.in_(bids()),Employee.is_active==True).order_by(Employee.full_name).all(),bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all(),leave_types=active_leave_types(),movement_types=active_movement_types(),approvers=approvers_for_employee(m.employee))
@app.post('/movements/<int:i>/submit')
@req
def movement_submit(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id) or not can_manage_movement(m): abort(403)
    if m.status in ('مسودة','مدخلة','مرفوضة','تحت المراجعة'):
        old_status=m.status; m.status='مدخلة'; m.approver_id=None; m.rejection_reason=None; m.modified_by=me().id; m.modified_at=datetime.utcnow(); record_movement_history(m,old_status,'مدخلة','SUBMIT','تثبيت الحركة كمعلومة تشغيلية — لا تحتاج لاعتماد'); log('SUBMIT','Movement',i,'الحركة لا تحتاج اعتمادًا'); db.session.commit(); flash('الحركة مسجلة مباشرة ولا تحتاج إلى اعتماد.')
    return redirect('/movements')
@app.post('/movements/<int:i>/approver')
@req
def movement_change_approver(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if m.status=='معتمدة':
        flash('المعتمد يحدد تلقائيًا حسب التبعية ولا يمكن تغييره يدويًا بعد الاعتماد.')
        return redirect('/movements')
    approver=auto_approver_for_employee(m.employee, me())
    if not approver:
        flash('لا يوجد معتمد محدد تلقائيًا لهذه المحافظة.')
        return redirect('/movements')
    old=m.approver_id
    m.approver_id=approver.id; m.modified_by=me().id; m.modified_at=datetime.utcnow()
    record_movement_history(m,m.status,m.status,'AUTO_APPROVER',f'تحديد المعتمد تلقائيًا حسب التبعية إلى {approver.id}')
    log('AUTO_APPROVER','Movement',i,f'المعتمد التلقائي: {approver.id}')
    db.session.commit()
    flash('تم تحديث المعتمد تلقائيًا حسب التبعية.')
    return redirect('/movements')
@app.post('/movements/<int:i>/status')
@req
def ms(i):
    if not can('review_movements') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if m.approver_id and m.approver_id!=me().id and 'مسؤول التطبيق' not in roles(): abort(403)
    s=request.form.get('status'); reason=(request.form.get('reason') or '').strip()
    if s=='مرفوضة' and len(reason)<3: flash('يجب إدخال سبب الرفض.'); return redirect('/movements')
    if s not in ('معتمدة','مرفوضة') or m.status!='تحت المراجعة': abort(400)
    old_status=m.status; m.status=s; m.rejection_reason=reason if s=='مرفوضة' else None; m.reviewed_by=me().id; m.reviewed_at=datetime.utcnow(); m.approved_by=me().id if s=='معتمدة' else None; m.approved_at=datetime.utcnow() if s=='معتمدة' else None; record_movement_history(m,old_status,s,'APPROVE' if s=='معتمدة' else 'REJECT',reason); log('APPROVE' if s=='معتمدة' else 'REJECT','Movement',i,reason or s); db.session.commit(); return redirect('/movements')
@app.post('/movements/<int:i>/cancel-approval')
@req
def movement_cancel_approval(i):
    if not can('cancel_approval') or not has_role('مسؤول التطبيق','مشرف محافظة'): abort(403)
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if m.status!='معتمدة':
        flash('لا يمكن إلغاء اعتماد حركة غير معتمدة.')
        return redirect('/movements')
    reason=(request.form.get('reason') or '').strip()
    if len(reason)<3:
        flash('يجب إدخال سبب إلغاء الاعتماد.')
        return redirect('/movements')
    old_status=m.status; m.status='تحت المراجعة'; m.rejection_reason=None; m.modified_by=me().id; m.modified_at=datetime.utcnow(); m.reviewed_by=None; m.reviewed_at=None; m.approved_by=None; m.approved_at=None
    record_movement_history(m,old_status,'تحت المراجعة','CANCEL_APPROVAL',reason); log('CANCEL_APPROVAL','Movement',i,reason); db.session.commit()
    flash('تم إلغاء الاعتماد وإعادة الحركة للمراجعة.')
    return redirect('/movements')

@app.get('/movements/<int:i>/assignment-form')
@req
def assignment_form(i):
    m=db.session.get(Movement,i)
    if not m or m.movement_type!='انتداب' or not branch_ok(m.employee.branch_id): abort(403)
    if m.status!='معتمدة':
        flash('لا يمكن طباعة نموذج المأمورية إلا بعد اعتماد الحركة.')
        return redirect('/movements')
    return render_template('assignment_form.html',m=m,today=date.today())

@app.post('/movements/<int:i>/delete')
@req
def md(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if not can('delete_movements'):
        flash('لا تملك صلاحية حذف المأموريات والحركات.')
    elif not can_manage_movement(m) and 'مسؤول التطبيق' not in roles():
        flash('لا تملك صلاحية حذف هذه الحركة ضمن نطاقك.')
    elif not m.is_active:
        flash('الحركة محذوفة بالفعل.')
    else:
        old_status=m.status
        m.is_active=False
        m.deleted_by=me().id
        m.deleted_at=datetime.utcnow()
        record_movement_history(m,old_status,old_status,'DELETE','حذف/إخفاء الحركة')
        log('DELETE','Movement',i,f'حذف الحركة؛ الحالة قبل الحذف: {old_status}')
        db.session.commit()
        flash('تم حذف الحركة بنجاح.')
    return redirect('/movements')

@app.route('/lookups',methods=['GET','POST'])
@req
@only('مسؤول التطبيق')
def lookups():
    if request.method=='POST':
        kind=request.form.get('kind'); name=request.form.get('name','').strip()
        if kind not in ('movement','leave') or not name: flash('بيانات القائمة غير صحيحة.')
        elif Lookup.query.filter_by(kind=kind,name=name).first(): flash('العنصر موجود بالفعل.')
        else: x=Lookup(kind=kind,name=name); db.session.add(x); db.session.commit(); log('ADD','Lookup',x.id,name); db.session.commit(); flash('تمت الإضافة.')
    rows=Lookup.query.order_by(Lookup.kind,Lookup.name).all(); return render_template('lookups.html',rows=rows)
@app.post('/lookups/<int:i>/edit')
@req
@only('مسؤول التطبيق')
def le(i):
    x=db.session.get(Lookup,i)
    if not x: abort(404)
    n=request.form.get('name','').strip()
    dup=Lookup.query.filter(Lookup.kind==x.kind,Lookup.name==n,Lookup.id!=i).first()
    if not n or dup: flash('الاسم غير صالح أو مكرر.')
    else:
        x.name=n; log('EDIT','Lookup',i,n); db.session.commit(); flash('تم التعديل.')
    return redirect('/lookups')
@app.post('/lookups/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def lt(i):
    x=db.session.get(Lookup,i)
    if not x: abort(404)
    x.is_active=not x.is_active; log('TOGGLE','Lookup',i); db.session.commit(); return redirect('/lookups')
@app.post('/lookups/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def ld(i):
    x=db.session.get(Lookup,i)
    if x:
        used=(x.kind=='movement' and Movement.query.filter_by(movement_type=x.name).count()) or (x.kind=='leave' and Movement.query.filter_by(leave_type=x.name).count())
        if used: flash('لا يمكن حذف عنصر مستخدم في حركات تاريخية؛ استخدم التعطيل.')
        else: db.session.delete(x); log('DELETE','Lookup',i); db.session.commit(); flash('تم الحذف.')
    return redirect('/lookups')

@app.get('/movements/<int:i>/history')
@req
def movement_history(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if not can('view_audit'): abort(403)
    rows=MovementHistory.query.filter_by(movement_id=i).order_by(MovementHistory.created_at.desc()).all()
    users={u.id:u.full_name for u in User.query.filter(User.id.in_([x.user_id for x in rows if x.user_id])).all()} if rows else {}
    return render_template('movement_history.html',m=m,rows=rows,history_users=users)

@app.get('/delegations')
@req
def delegations():
    u=me()
    if 'مسؤول التطبيق' not in roles(u) and 'مشرف محافظة' not in roles(u): abort(403)
    q=ApprovalDelegation.query
    if 'مسؤول التطبيق' not in roles(u):
        gids=user_gov_ids(u)
        q=q.filter(ApprovalDelegation.supervisor_id==u.id, ApprovalDelegation.governorate_id.in_(gids)) if gids else q.filter(False)
    rows=q.order_by(ApprovalDelegation.is_active.desc(),ApprovalDelegation.starts_at.desc(),ApprovalDelegation.id.desc()).all()
    if 'مسؤول التطبيق' in roles(u):
        supervisors=[x for x in User.query.filter(User.is_active==True).order_by(User.full_name).all() if 'مشرف محافظة' in roles(x)]
        govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
    else:
        supervisors=[u]; govs=Governorate.query.filter(Governorate.id.in_(user_gov_ids(u))).filter_by(is_active=True).order_by(Governorate.name).all()
    delegates=[x for x in User.query.filter(User.is_active==True).order_by(User.full_name).all() if 'مشرف محافظة' in roles(x) and can_for_user(x,'review_movements')]
    return render_template('delegations.html',rows=rows,supervisors=supervisors,govs=govs,delegates=delegates)

@app.post('/delegations/add')
@req
def delegation_add():
    u=me()
    if 'مسؤول التطبيق' not in roles(u) and 'مشرف محافظة' not in roles(u): abort(403)
    sup_id=int(request.form.get('supervisor_id') or 0); delegate_id=int(request.form.get('delegate_id') or 0); gid=int(request.form.get('governorate_id') or 0)
    try:
        starts=date.fromisoformat(request.form.get('starts_at','')); ends=date.fromisoformat(request.form.get('ends_at',''))
    except ValueError:
        starts=ends=None
    sup=db.session.get(User,sup_id); delegate=db.session.get(User,delegate_id); gov=db.session.get(Governorate,gid)
    if 'مسؤول التطبيق' not in roles(u): sup=u
    if not sup or not delegate or not gov or not starts or not ends or starts>ends:
        flash('جميع بيانات التفويض مطلوبة، ويجب أن تكون بداية التفويض قبل أو مساوية لنهايته.'); return redirect('/delegations')
    if not delegation_allowed_for_user(sup,gid):
        flash('المشرف أو المحافظة لا يتطابقان مع التبعية.'); return redirect('/delegations')
    if delegate.id==sup.id:
        flash('لا يمكن اختيار المشرف نفسه كبديل.'); return redirect('/delegations')
    if 'مشرف محافظة' not in roles(delegate) or not can_for_user(delegate,'review_movements') or gid not in user_gov_ids(delegate):
        flash('البديل يجب أن يكون مشرف محافظة مؤهلًا ومكلفًا بالمحافظة نفسها.'); return redirect('/delegations')
    overlap=(ApprovalDelegation.query.filter_by(supervisor_id=sup.id,governorate_id=gid,is_active=True)
             .filter(ApprovalDelegation.starts_at <= ends, ApprovalDelegation.ends_at >= starts).first())
    if overlap:
        flash('يوجد تفويض ساري متداخل مع الفترة المحددة.'); return redirect('/delegations')
    d=ApprovalDelegation(supervisor_id=sup.id,delegate_id=delegate.id,governorate_id=gid,starts_at=starts,ends_at=ends,created_by=u.id)
    db.session.add(d); db.session.flush(); log('ADD','ApprovalDelegation',d.id,f'تفويض {sup.full_name} إلى {delegate.full_name} للمحافظة {gov.name} من {starts} إلى {ends}'); db.session.commit(); flash('تم إنشاء التفويض.'); return redirect('/delegations')

@app.post('/delegations/<int:i>/revoke')
@req
def delegation_revoke(i):
    u=me(); d=db.session.get(ApprovalDelegation,i)
    if not d: abort(404)
    if 'مسؤول التطبيق' not in roles(u) and not (d.supervisor_id==u.id and delegation_allowed_for_user(u,d.governorate_id)): abort(403)
    if not d.is_active: flash('التفويض غير ساري بالفعل.'); return redirect('/delegations')
    reason=request.form.get('reason','').strip()
    if len(reason)<3: flash('سبب إلغاء التفويض إجباري.'); return redirect('/delegations')
    d.is_active=False; d.revoked_by=u.id; d.revoked_at=datetime.utcnow(); d.revoke_reason=reason; log('REVOKE','ApprovalDelegation',d.id,reason); db.session.commit(); flash('تم إلغاء التفويض فورًا.'); return redirect('/delegations')

@app.get('/audit')
@req
def audit():
    if not can('view_audit'): abort(403)
    rows=Audit.query.order_by(Audit.created_at.desc()).limit(1000).all()
    ids={x.user_id for x in rows if x.user_id}
    audit_users={u.id:u.full_name for u in User.query.filter(User.id.in_(ids)).all()} if ids else {}
    return render_template('audit.html',rows=rows,audit_users=audit_users)

@app.get('/reports/assignments/print-missions')
@req
def mission_print_list():
    if not can('view_reports'): abort(403)
    bs=bids()
    q=(Movement.query.join(Employee).filter(
        Employee.branch_id.in_(bs), Movement.is_active==True, Movement.movement_type=='انتداب'
    ) if bs else Movement.query.filter(False))

    gov=request.args.get('governorate_id','').strip()
    branch=request.args.get('branch_id','').strip()
    employee=request.args.get('employee_id','').strip()
    status=request.args.get('status','').strip()
    date_from=request.args.get('date_from','').strip()
    date_to=request.args.get('date_to','').strip()

    allowed_gov_ids=set(gids()) if gids() else set()
    govs=Governorate.query.filter(Governorate.is_active==True).order_by(Governorate.name.asc()).all()
    govs=[g for g in govs if g.id in allowed_gov_ids]
    branches=Branch.query.filter(Branch.is_active==True, Branch.id.in_(bs)).order_by(Branch.name.asc()).all() if bs else []
    branches=[b for b in branches if b.governorate_id in allowed_gov_ids]

    selected_gov=None
    if gov.isdigit() and int(gov) in allowed_gov_ids:
        selected_gov=db.session.get(Governorate,int(gov))
        branches=[b for b in branches if b.governorate_id==selected_gov.id]
    else:
        gov=''

    selected_branch=None
    if branch.isdigit() and any(b.id==int(branch) for b in branches):
        selected_branch=db.session.get(Branch,int(branch))
        q=q.filter(Employee.branch_id==selected_branch.id)
    elif selected_gov:
        q=q.filter(Employee.branch.has(Branch.governorate_id==selected_gov.id))
    else:
        branch=''

    employees_q=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)) if bs else Employee.query.filter(False)
    if selected_branch:
        employees_q=employees_q.filter(Employee.branch_id==selected_branch.id)
    elif selected_gov:
        employees_q=employees_q.join(Branch).filter(Branch.governorate_id==selected_gov.id)
    employees=employees_q.order_by(Employee.full_name.asc()).all()

    if employee.isdigit() and any(e.id==int(employee) for e in employees):
        q=q.filter(Movement.employee_id==int(employee))
    else:
        employee=''
    if status in STATUSES: q=q.filter(Movement.status==status)

    from datetime import date as _date
    def _parse_report_date(value):
        try: return _date.fromisoformat(value) if value else None
        except ValueError: return None
    df=_parse_report_date(date_from); dt=_parse_report_date(date_to)
    if df and dt and df>dt: df,dt=dt,df
    if df: q=q.filter(Movement.to_date >= df)
    if dt: q=q.filter(Movement.from_date <= dt)

    rows=q.order_by(Movement.from_date.desc(),Movement.id.desc()).all()
    return render_template('mission_reports.html', rows=rows, statuses=STATUSES,
        report_governorates=govs, report_branches=branches, employees=employees,
        selected_governorate=gov, selected_branch=branch, selected_employee=employee,
        status=status, date_from=date_from, date_to=date_to)

@app.get('/reports/assignments/print-mission/<int:movement_id>')
@req
def mission_print(movement_id):
    m = db.session.get(Movement, movement_id)
    if not m: abort(404)
    if not can_manage_movement(m): abort(403)
    if m.movement_type != 'انتداب': abort(400)
    employee = db.session.get(Employee, m.employee_id)
    branch = db.session.get(Branch, employee.branch_id) if employee else None
    gov = db.session.get(Governorate, branch.governorate_id) if branch else None
    approver = db.session.get(User, m.approver_id) if getattr(m, 'approver_id', None) else None
    approved_by_person = db.session.get(User, m.approved_by) if getattr(m, 'approved_by', None) else None
    creator = db.session.get(User, m.created_by) if getattr(m, 'created_by', None) else None
    return render_template(
        'mission_print.html',
        movement=m, employee=employee, branch=branch, governorate=gov,
        approver=approver, approved_by_person=approved_by_person, creator=creator, printed_at=datetime.now(),
        mission_state=('مغلق' if m.status == 'معتمدة' else 'تحت التحرير')
    )

@app.get('/reports')
@req
def reports():
    if not can('view_reports'): abort(403)
    bs=bids(); q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True) if bs else Movement.query.filter(False)
    status=request.args.get('status','').strip(); mt=request.args.get('movement_type','').strip();
    if status in STATUSES: q=q.filter(Movement.status==status)
    if mt in active_movement_types(): q=q.filter(Movement.movement_type==mt)
    summary={s:q.filter(Movement.status==s).count() for s in STATUSES}; by_type={t:q.filter(Movement.movement_type==t).count() for t in MOVEMENT_TYPES}
    return render_template('reports.html',summary=summary,by_type=by_type,status=status,movement_type=mt,statuses=STATUSES,movement_types=active_movement_types())
@app.get('/reports/<report_type>')
@req
def employee_type_report(report_type):
    if not can('view_reports'): abort(403)
    mapping={'leaves':'إجازة','assignments':'انتداب','permissions':'إذن'}
    if report_type not in mapping: abort(404)
    mt=mapping[report_type]
    bs=bids()
    q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True,Movement.movement_type==mt) if bs else Movement.query.filter(False)
    status=request.args.get('status','').strip()
    employee_id=request.args.get('employee_id','').strip()
    date_from=request.args.get('date_from','').strip()
    date_to=request.args.get('date_to','').strip()
    from datetime import date as _date
    def _parse_report_date(value):
        try: return _date.fromisoformat(value) if value else None
        except ValueError: return None
    date_from_obj=_parse_report_date(date_from)
    date_to_obj=_parse_report_date(date_to)
    if date_from_obj and date_to_obj and date_from_obj > date_to_obj:
        date_from_obj, date_to_obj = date_to_obj, date_from_obj
    if status in STATUSES: q=q.filter(Movement.status==status)
    if employee_id.isdigit(): q=q.filter(Movement.employee_id==int(employee_id))
    report_gov=request.args.get('governorate_id','').strip()
    report_branch=request.args.get('branch_id','').strip()
    if report_gov.isdigit():
        gid=int(report_gov)
        gov_allowed = {g.id for g in Governorate.query.filter(Governorate.is_active==True).all() if g.id in set(gids())} if gids() else set()
        if gid in gov_allowed:
            q=q.filter(Employee.branch.has(Branch.governorate_id==gid))
    if report_branch.isdigit():
        bid=int(report_branch)
        if bid in set(bs):
            q=q.filter(Employee.branch_id==bid)
    if date_from_obj:
        if mt in ('إجازة','انتداب'):
            q=q.filter(Movement.to_date >= date_from_obj)
        else:
            q=q.filter(Movement.permission_date >= date_from_obj)
    if date_to_obj:
        if mt in ('إجازة','انتداب'):
            q=q.filter(Movement.from_date <= date_to_obj)
        else:
            q=q.filter(Movement.permission_date <= date_to_obj)
    rows=q.order_by(Employee.full_name.asc(),Movement.from_date.desc(),Movement.permission_date.desc(),Movement.created_at.desc()).all()
    grouped=[]
    current=None
    for m in rows:
        if current is None or current['employee'].id != m.employee.id:
            current={'employee':m.employee,'rows':[]}
            grouped.append(current)
        current['rows'].append(m)
    # Cascading report filters: governorate -> branch -> employee.
    selected_gov=request.args.get('governorate_id','').strip()
    selected_branch=request.args.get('branch_id','').strip()

    allowed_gov_ids=set(gids())
    allowed_govs=Governorate.query.filter(Governorate.is_active==True, Governorate.id.in_(allowed_gov_ids)).order_by(Governorate.name.asc()).all() if allowed_gov_ids else []
    allowed_branches=Branch.query.filter(Branch.is_active==True,Branch.id.in_(bs)).order_by(Branch.name.asc()).all() if bs else []
    if allowed_gov_ids:
        allowed_branches=[b for b in allowed_branches if b.governorate_id in allowed_gov_ids]
    else:
        allowed_branches=[]

    selected_gov_obj=None
    if selected_gov.isdigit() and int(selected_gov) in allowed_gov_ids:
        selected_gov_obj=db.session.get(Governorate,int(selected_gov))
        allowed_branches=[b for b in allowed_branches if b.governorate_id==selected_gov_obj.id]
    else:
        selected_gov=''

    selected_branch_obj=None
    if selected_branch.isdigit() and any(b.id==int(selected_branch) for b in allowed_branches):
        selected_branch_obj=db.session.get(Branch,int(selected_branch))
    else:
        selected_branch=''

    employees_q=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)) if bs else Employee.query.filter(False)
    if selected_branch_obj:
        employees_q=employees_q.filter(Employee.branch_id==selected_branch_obj.id)
    elif selected_gov_obj:
        employees_q=employees_q.join(Branch).filter(Branch.governorate_id==selected_gov_obj.id)
    employees=employees_q.order_by(Employee.full_name.asc()).all()

    return render_template(
        'employee_type_report.html',
        report_type=report_type,
        title={'leaves':'تقرير إجازات الموظفين','assignments':'تقرير انتدابات الموظفين','permissions':'تقرير أذونات الموظفين'}[report_type],
        rows=grouped,
        employees=employees,
        status=status,
        statuses=STATUSES,
        date_from=date_from,
        date_to=date_to,
        report_governorates=allowed_govs,
        report_branches=allowed_branches,
        selected_governorate=selected_gov,
        selected_branch=selected_branch,
        selected_employee=employee_id if employee_id.isdigit() else ''
    )

@app.get('/reports/<report_type>.csv')
@req
def employee_type_report_csv(report_type):
    if not can('view_reports'): abort(403)
    mapping={'leaves':'إجازة','assignments':'انتداب','permissions':'إذن'}
    if report_type not in mapping: abort(404)
    mt=mapping[report_type]
    import csv,io
    bs=bids(); q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True,Movement.movement_type==mt) if bs else Movement.query.filter(False)
    status=request.args.get('status','').strip(); employee_id=request.args.get('employee_id','').strip()
    date_from=request.args.get('date_from','').strip(); date_to=request.args.get('date_to','').strip()
    from datetime import date as _date
    def _parse_report_date(value):
        try: return _date.fromisoformat(value) if value else None
        except ValueError: return None
    date_from_obj=_parse_report_date(date_from); date_to_obj=_parse_report_date(date_to)
    if date_from_obj and date_to_obj and date_from_obj > date_to_obj:
        date_from_obj, date_to_obj = date_to_obj, date_from_obj
    if status in STATUSES: q=q.filter(Movement.status==status)
    if employee_id.isdigit(): q=q.filter(Movement.employee_id==int(employee_id))
    report_gov=request.args.get('governorate_id','').strip()
    report_branch=request.args.get('branch_id','').strip()
    if report_gov.isdigit():
        gid=int(report_gov)
        gov_allowed = {g.id for g in Governorate.query.filter(Governorate.is_active==True).all() if g.id in set(gids())} if gids() else set()
        if gid in gov_allowed:
            q=q.filter(Employee.branch.has(Branch.governorate_id==gid))
    if report_branch.isdigit():
        bid=int(report_branch)
        if bid in set(bs):
            q=q.filter(Employee.branch_id==bid)
    if date_from_obj:
        if mt in ('إجازة','انتداب'): q=q.filter(Movement.to_date >= date_from_obj)
        else: q=q.filter(Movement.permission_date >= date_from_obj)
    if date_to_obj:
        if mt in ('إجازة','انتداب'): q=q.filter(Movement.from_date <= date_to_obj)
        else: q=q.filter(Movement.permission_date <= date_to_obj)
    rows=q.order_by(Employee.full_name.asc(),Movement.from_date.desc(),Movement.permission_date.desc()).all()
    out=io.StringIO(); w=csv.writer(out)
    w.writerow(['JobCode','EmployeeName','Governorate','Branch','MovementType','LeaveType','DestinationBranch','From','To','PermissionDate','Status','RejectionReason'])
    for m in rows:
        w.writerow([m.employee.job_code or '',m.employee.full_name,m.employee.branch.governorate.name if m.employee.branch and m.employee.branch.governorate else '',m.employee.branch.name if m.employee.branch else '',m.movement_type,m.leave_type or '',m.destination.name if m.destination else '',m.from_date or '',m.to_date or '',m.permission_date or '',m.status,m.rejection_reason or ''])
    from flask import Response
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename={report_type}_employees_report.csv'})

@app.get('/reports.csv')
@req
def report_csv():
    if not can('view_reports'): abort(403)
    import csv,io
    bs=bids(); q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True) if bs else Movement.query.filter(False)
    status=request.args.get('status','').strip(); mt=request.args.get('movement_type','').strip()
    if status in STATUSES: q=q.filter(Movement.status==status)
    if mt in active_movement_types(): q=q.filter(Movement.movement_type==mt)
    rows=q.order_by(Movement.created_at.desc()).all()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['MovementID','JobCode','EmployeeName','Branch','MovementType','LeaveType','From','To','PermissionDate','Status','RejectionReason','CreatedAt'])
    for m in rows: w.writerow([m.id,m.employee.job_code or '',m.employee.full_name,m.employee.branch.name,m.movement_type,m.leave_type or '',m.from_date or '',m.to_date or '',m.permission_date or '',m.status,m.rejection_reason or '',m.created_at])
    from flask import Response
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=movements_report.csv'})

def purge_old_records_once():
    # Permanently disabled: deployments/restarts must never delete application data.
    return False

def ensure_v25_schema():
    db.create_all()
    # القوائم الأساسية الافتراضية: تُضاف مرة واحدة فقط، ولا تُعتبر بيانات موظفين أو محافظات.
    default_lookups = [
        ('movement','إجازة'), ('movement','انتداب'), ('movement','إذن'),
        ('leave','سنوية'), ('leave','عارضة'), ('leave','مصيف'), ('leave','وضع'),
    ]
    for kind, name in default_lookups:
        if not Lookup.query.filter_by(kind=kind, name=name).first():
            db.session.add(Lookup(kind=kind, name=name, is_active=True))
    db.session.commit()
    # db.create_all does not add columns to an existing Movement table.
    from sqlalchemy import inspect, text
    insp=inspect(db.engine)
    cols={c['name'] for c in insp.get_columns('movement')}
    additions={
      'is_active':'BOOLEAN NOT NULL DEFAULT TRUE',
      'deleted_by':'INTEGER',
      'deleted_at':'TIMESTAMP',
      'rejection_reason':'TEXT',
      'assignment_state':"VARCHAR(30) NOT NULL DEFAULT 'ساري'",
      'closed_by':'INTEGER',
      'closed_at':'TIMESTAMP',
      'closure_reason':'TEXT',
      'last_assignment_notice_at':'TIMESTAMP'
    }
    for name, typ in additions.items():
        if name not in cols:
            db.session.execute(text(f'ALTER TABLE movement ADD COLUMN {name} {typ}'))
    ucols={c['name'] for c in insp.get_columns('user')}
    if 'job_title' not in ucols:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN job_title VARCHAR(200)'))
    if 'job_code' not in ucols:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN job_code VARCHAR(100)'))
    if 'email' not in ucols:
        db.session.execute(text('ALTER TABLE "user" ADD COLUMN email VARCHAR(254)'))
    ecols_existing={c['name'] for c in insp.get_columns('employee')}
    if 'user_id' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN user_id INTEGER'))
    if 'email' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN email VARCHAR(254)'))
    if 'deleted_at' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN deleted_at TIMESTAMP'))
    if 'deleted_by' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN deleted_by INTEGER'))
    mcols={c['name'] for c in insp.get_columns('movement')}
    if 'approver_id' not in mcols:
        db.session.execute(text('ALTER TABLE movement ADD COLUMN approver_id INTEGER'))
    ApprovalDelegation.__table__.create(bind=db.engine, checkfirst=True)
    SupervisorEntry.__table__.create(bind=db.engine, checkfirst=True)
    RoleAccount.__table__.create(bind=db.engine, checkfirst=True)
    EntryAssignment.__table__.create(bind=db.engine, checkfirst=True)
    EntryAssignmentBranch.__table__.create(bind=db.engine, checkfirst=True)
    # Backfill unambiguous old links: entry -> supervisor when one supervisor owns the entry's governorate.
    for eu in User.query.filter_by(is_active=True).all():
        if 'المدخل الأول' not in actual_roles(eu) or SupervisorEntry.query.filter_by(entry_id=eu.id).first():
            continue
        gids_e={b.governorate_id for b in Branch.query.filter(Branch.id.in_(user_branch_ids(eu))).all()}
        if len(gids_e)==1:
            sup=supervisor_for_governorate(next(iter(gids_e)))
            if sup: db.session.add(SupervisorEntry(supervisor_id=sup.id,entry_id=eu.id))
    db.session.commit()
    # Link existing first-level accounts to their employee record when an unambiguous match exists.
    for eu in User.query.filter_by(is_active=True).all():
        if 'المدخل الأول' not in actual_roles(eu):
            continue
        if Employee.query.filter_by(user_id=eu.id).first():
            continue
        branch_ids=list(user_branch_ids(eu))
        q=Employee.query.filter(Employee.full_name==eu.full_name)
        if eu.job_code:
            q=q.filter(Employee.job_code==eu.job_code)
        if branch_ids:
            q=q.filter(Employee.branch_id.in_(branch_ids))
        matches=q.order_by(Employee.id.asc()).all()
        if len(matches)==1:
            matches[0].user_id=eu.id
    db.session.commit()
    ecols={c['name'] for c in insp.get_columns('employee')}
    # Existing employee_code values are retained for legacy history; new registrations no longer populate this field.
    if 'employee_code' in ecols and db.engine.dialect.name=='postgresql':
        db.session.execute(text('ALTER TABLE employee ALTER COLUMN employee_code DROP NOT NULL'))
    db.session.commit()

with app.app_context():
    ensure_v25_schema()
    admin_name=os.getenv('ADMIN_USERNAME','admin'); admin_pass=os.getenv('ADMIN_PASSWORD','CHANGE_INITIAL_ADMIN_PASSWORD'); admin_email=os.getenv('ADMIN_EMAIL','').strip()
    u=User.query.filter_by(username=admin_name).first()
    if not u:
        u=User(username=admin_name,full_name='مسؤول التطبيق',email=(admin_email if valid_email(admin_email) else None),password_hash=generate_password_hash(admin_pass)); db.session.add(u); db.session.flush(); db.session.add(UserRole(user_id=u.id,role='مسؤول التطبيق')); db.session.commit()
    else:
        if admin_email and valid_email(admin_email): u.email=admin_email
        if not u.job_title: u.job_title='مسؤول التطبيق'
        if not u.job_code: u.job_code='ADMIN'
        db.session.commit()
    # تنظيف دور/ارتباطات مشرف سوهاج من حساب مسؤول التطبيق: تنفيذ لمرة واحدة فقط.
    # بعد وضع علامة الترحيل في Lookup لن يعاد حذف أي أدوار أو ارتباطات مستقبلية عند كل تشغيل.
    cleanup_key='migration:admin-supervisor-scope-cleanup-v34.45'
    cleanup_done=Lookup.query.filter_by(kind='system_migration',name=cleanup_key).first()
    if not cleanup_done:
        UserRole.query.filter_by(user_id=u.id,role='مشرف محافظة').delete()
        UserGovernorate.query.filter_by(user_id=u.id).delete()
        UserBranch.query.filter_by(user_id=u.id).delete()
        RoleAccount.query.filter_by(user_id=u.id,role='مشرف محافظة').delete()
        if not UserRole.query.filter_by(user_id=u.id,role='مسؤول التطبيق').first():
            db.session.add(UserRole(user_id=u.id,role='مسؤول التطبيق'))
        db.session.add(Lookup(kind='system_migration',name=cleanup_key,is_active=True))
        db.session.flush()
    sync_role_accounts(u)
    for _u in User.query.filter_by(is_active=True).all(): sync_role_accounts(_u)
    db.session.commit()
    # Destructive legacy cleanup is intentionally never run at startup.

if __name__=='__main__': app.run(host='0.0.0.0',port=8000)
