import os, secrets, re, json, io, urllib.request, urllib.error
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, has_request_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook, load_workbook
import fitz

app=Flask(__name__)
APP_VERSION='v35.79'
DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///local.db')
if DATABASE_URL.startswith('postgres://'): DATABASE_URL=DATABASE_URL.replace('postgres://','postgresql+psycopg2://',1)
elif DATABASE_URL.startswith('postgresql://'): DATABASE_URL=DATABASE_URL.replace('postgresql://','postgresql+psycopg2://',1)
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
    id=db.Column(db.Integer,primary_key=True); employee_code=db.Column(db.String(100),unique=True,nullable=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL'),unique=True,nullable=True); email=db.Column(db.String(254),unique=True,nullable=True); full_name=db.Column(db.String(250),nullable=False); branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT'),nullable=False); job_title=db.Column(db.String(200)); job_code=db.Column(db.String(100)); hire_date=db.Column(db.Date); company_phone=db.Column(db.String(80)); personal_phone=db.Column(db.String(80)); is_active=db.Column(db.Boolean,default=True,nullable=False); resignation_date=db.Column(db.Date); rehire_date=db.Column(db.Date); resignation_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); deleted_at=db.Column(db.DateTime); deleted_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); branch=db.relationship('Branch')
class Movement(db.Model):
    id=db.Column(db.Integer,primary_key=True); employee_id=db.Column(db.Integer,db.ForeignKey('employee.id',ondelete='RESTRICT'),nullable=False); movement_type=db.Column(db.String(30),nullable=False); leave_type=db.Column(db.String(100)); destination_branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT')); from_date=db.Column(db.Date); to_date=db.Column(db.Date); permission_date=db.Column(db.Date); status=db.Column(db.String(30),default='مسودة',nullable=False); notes=db.Column(db.Text); rejection_reason=db.Column(db.Text); is_active=db.Column(db.Boolean,default=True,nullable=False); deleted_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); deleted_at=db.Column(db.DateTime); created_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); modified_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); modified_at=db.Column(db.DateTime); reviewed_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); reviewed_at=db.Column(db.DateTime); approved_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); approved_at=db.Column(db.DateTime); approver_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); employee=db.relationship('Employee'); approver=db.relationship('User',foreign_keys=[approver_id]); destination=db.relationship('Branch',foreign_keys=[destination_branch_id]); assignment_state=db.Column(db.String(30),default='ساري',nullable=False); mission_state=db.Column(db.String(30),default='تحت التحرير',nullable=False); closed_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); closed_at=db.Column(db.DateTime); closure_reason=db.Column(db.Text); last_assignment_notice_at=db.Column(db.DateTime)
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
    if not m.to_date: return 'انتداب مفتوح'
    today=date.today()
    if m.to_date < today: return 'انتهت المدة'
    if m.to_date <= today + timedelta(days=ASSIGNMENT_ALERT_DAYS): return 'قرب الانتهاء'
    return 'ساري'

def current_assignment_for_employee(employee_id, on_date=None):
    on_date = on_date or date.today()
    moves=(Movement.query.filter_by(employee_id=employee_id,is_active=True,movement_type='انتداب')
           .filter(Movement.assignment_state!='مغلق')
           .order_by(Movement.id.desc()).all())
    for m in moves:
        if not m.from_date or m.from_date > on_date:
            continue
        if m.to_date is None or on_date <= m.to_date:
            return m
    return None

def effective_branch_id_for_employee(employee_id, on_date=None):
    m=current_assignment_for_employee(employee_id,on_date)
    return m.destination_branch_id if m and m.destination_branch_id else None

def employee_is_effectively_in_branch(employee, branch_id, on_date=None):
    assigned=effective_branch_id_for_employee(employee.id,on_date)
    return assigned == branch_id if assigned else employee.branch_id == branch_id

def employee_scope_ok(employee, on_date=None):
    if not employee or not employee.is_active: return False
    today=on_date or date.today()
    return branch_ok(employee.branch_id) or (effective_branch_id_for_employee(employee.id,today) in set(bids()))

def employees_effectively_in_branches(branch_ids, on_date=None):
    """Return employees physically in the requested branches without an N+1 query.

    The old implementation executed a movement query for every active employee.
    On the home-page employee search this could become very expensive and, on a
    busy database, surface as a generic Internal Server Error/worker timeout.
    Build the set of employees with a current open assignment in one query, then
    fetch the employees once.
    """
    ids={int(x) for x in (branch_ids or set()) if x is not None}
    if not ids:
        return []
    today=on_date or date.today()

    assigned_employee_ids={
        row[0] for row in (
            db.session.query(Movement.employee_id)
            .filter(
                Movement.is_active==True,
                Movement.movement_type=='انتداب',
                Movement.assignment_state!='مغلق',
                Movement.from_date!=None,
                Movement.from_date<=today,
                db.or_(Movement.to_date==None, Movement.to_date>=today),
                Movement.destination_branch_id.in_(ids)
            )
            .all()
        )
    }

    q=Employee.query.filter(
        Employee.is_active==True,
        db.or_(Employee.branch_id.in_(ids), Employee.id.in_(assigned_employee_ids))
    ).order_by(Employee.full_name.asc())
    return q.all()

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
    return {'me':u,'roles':roles(),'real_roles':real_roles,'active_role':active_role,'csrf':csrf_token(),'user_roles':user_roles,'user_permissions':user_permissions,'can':can,'has_role':has_role,'PERMISSIONS':PERMISSIONS,'user_gov_ids':user_gov_ids,'user_branch_ids':user_branch_ids,'assignment_state':assignment_state,'current_assignment_for_employee':current_assignment_for_employee,'assignment_supervisor':assignment_supervisor,'supervisor_for_entry':supervisor_for_entry,'entries_for_supervisor':entries_for_supervisor,'branch_entry':branch_entry,'auto_approver_for_employee':auto_approver_for_employee,'can_manage_employee':can_manage_employee,'ASSIGNMENT_STATES':ASSIGNMENT_STATES,'ASSIGNMENT_ALERT_DAYS':ASSIGNMENT_ALERT_DAYS}

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
        elif start:
            if x.movement_type=='انتداب' and x.assignment_state!='مغلق' and x.from_date and x.to_date is None:
                if end is None or end >= x.from_date:
                    return 'يوجد انتداب مفتوح للموظف؛ أغلقه أو عدّل مدته قبل تسجيل حركة متعارضة.'
            if x.from_date and x.to_date and (end is None or start<=x.to_date) and (end is None or end>=x.from_date): return 'فترة الحركة تتعارض مع حركة أخرى للموظف.'
            if x.movement_type=='إذن' and x.permission_date and ((end is None and x.permission_date>=start) or (end is not None and start<=x.permission_date<=end)): return 'فترة الحركة تتعارض مع إذن للموظف.'
    return None

def validate_movement_fields(mt, leave_type, dest, fd, td, pd):
    if mt not in active_movement_types(): return 'نوع الحركة غير صحيح.'
    if mt=='إجازة':
        if not leave_type or leave_type not in active_leave_types(): return 'نوع الإجازة غير صحيح أو غير محدد.'
        if not fd or not td: return 'حدد تاريخ البداية والنهاية.'
    elif mt=='انتداب':
        if not dest or not branch_ok(dest): return 'فرع الانتداب غير مسموح.'
        if not fd: return 'حدد تاريخ بداية الانتداب.'
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
    if 'مشرف محافظة' in rs:
        assigned=[x.governorate_id for x in UserGovernorate.query.filter_by(user_id=u.id).join(Governorate).filter(Governorate.is_active==True)]
        # حساب مسؤول التطبيق قد يحمل دور مشرف موازيًا؛ عند عدم وجود نطاق مسند له
        # نستخدم كل المحافظات بدل أن تظهر له لوحة مشرف فارغة.
        if assigned: return assigned
        if 'مسؤول التطبيق' in actual_roles(u):
            return [g.id for g in Governorate.query.filter_by(is_active=True)]
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
    """عرض الحالات التشغيلية المطلوبة فقط: إجازة، انتداب ساري، انتداب مفتوح، إذن اليوم."""
    if not branch_ids:
        return []

    employees=employees_effectively_in_branches(branch_ids,today)
    rows=[]
    for e in employees:
        moves=(Movement.query.filter_by(employee_id=e.id,is_active=True)
               .order_by(Movement.created_at.desc(),Movement.id.desc()).all())

        # الأولوية في لوحة الحالة: الإجازة، ثم الانتداب المحدد، ثم المفتوح، ثم إذن اليوم.
        leave=next((m for m in moves if m.movement_type=='إجازة' and m.from_date and m.to_date and m.from_date<=today<=m.to_date),None)
        assignment=next((m for m in moves if m.movement_type=='انتداب' and m.assignment_state!='مغلق'
                         and m.from_date and m.from_date<=today and m.to_date is not None and today<=m.to_date),None)
        open_assignment=next((m for m in moves if m.movement_type=='انتداب' and m.assignment_state!='مغلق'
                              and m.from_date and m.from_date<=today and m.to_date is None),None)
        permission=next((m for m in moves if m.movement_type=='إذن' and m.permission_date==today),None)

        current=None
        state=None
        place=''
        until=None
        detail=''
        display_branch=e.branch

        if leave:
            current=leave
            state='إجازة'
            place=leave.leave_type or 'إجازة'
            until=leave.to_date
            detail='من {} إلى {}'.format(leave.from_date.strftime('%d/%m/%Y'),leave.to_date.strftime('%d/%m/%Y'))
        elif assignment:
            current=assignment
            state='انتداب'
            place=assignment.destination.name if assignment.destination else 'جهة الانتداب غير محددة'
            until=assignment.to_date
            detail='من {} إلى {}'.format(assignment.from_date.strftime('%d/%m/%Y'),assignment.to_date.strftime('%d/%m/%Y'))
            display_branch=assignment.destination or e.branch
        elif open_assignment:
            current=open_assignment
            state='انتداب مفتوح'
            place=open_assignment.destination.name if open_assignment.destination else 'جهة الانتداب غير محددة'
            until=None
            detail='من {} — مفتوح'.format(open_assignment.from_date.strftime('%d/%m/%Y'))
            display_branch=open_assignment.destination or e.branch
        elif permission:
            current=permission
            state='إذن'
            place=e.branch.name if e.branch else '—'
            until=permission.permission_date
            detail='بتاريخ {}'.format(permission.permission_date.strftime('%d/%m/%Y'))

        # لا نعرض المتواجدين عاديًا؛ هذه اللوحة مخصصة للحالات الأربع فقط.
        if not current:
            continue

        remaining=(until-today).days if until else None
        rows.append({
            'employee':e,'state':state,'place':place,'until':until,'detail':detail,
            'remaining':remaining,'movement':current,
            'ending_notice':bool(until and until <= today + timedelta(days=1)),
            'from_date':current.from_date if current and current.movement_type in ('إجازة','انتداب') else current.permission_date,
            'to_date':current.to_date if current and current.movement_type in ('إجازة','انتداب') else None,
            'display_branch':display_branch
        })

    def status_rank(r):
        if r['state']=='إجازة': return 0
        if r['state']=='انتداب': return 1
        if r['state']=='انتداب مفتوح': return 2
        return 3

    rows.sort(key=lambda r:(status_rank(r), r['until'] or date.max, r['employee'].full_name))
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
    # بحث حركات الموظفين من الصفحة الرئيسية: بالفرع أو بالاسم أو بهما معًا.
    movement_governorate_id=request.args.get('movement_governorate_id','').strip()
    movement_branch_id=request.args.get('movement_branch_id','').strip()
    movement_name_query=(request.args.get('movement_name') or '').strip()
    movement_employee_id=request.args.get('employee_id','').strip()
    movement_employee=None
    movement_employee_matches=[]
    movement_employee_moves=[]
    movement_employee_last={}
    search_gov_id=int(movement_governorate_id) if movement_governorate_id.isdigit() else None
    allowed_gov_ids=set(gids())
    if search_gov_id and search_gov_id not in allowed_gov_ids: search_gov_id=None
    search_branch_id=int(movement_branch_id) if movement_branch_id.isdigit() else None
    if search_gov_id and search_branch_id:
        sb=db.session.get(Branch,search_branch_id)
        if not sb or sb.governorate_id!=search_gov_id or not branch_ok(search_branch_id): search_branch_id=None
    elif not search_gov_id:
        search_branch_id=None
    # البحث داخل المحافظة: يشمل فرع التعيين أو الفرع الحالي أثناء الانتداب.
    # عند اختيار فرع، تكون النتيجة موظفي هذا الفرع فقط (تعيينًا أو وجودًا فعليًا).
    search_gov_branch_ids={b.id for b in Branch.query.filter_by(governorate_id=search_gov_id,is_active=True).all()} if search_gov_id else set()
    permitted_search_branch_ids={bid for bid in search_gov_branch_ids if branch_ok(bid)}
    if search_gov_id:
        target_branch_ids={search_branch_id} if search_branch_id else permitted_search_branch_ids
        candidates=employees_effectively_in_branches(target_branch_ids,today)
        # الموظف الذي فرع تعيينه داخل النطاق يجب أن يظهر حتى لو كان منتدبًا خارجه.
        if not search_branch_id:
            home_candidates=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(permitted_search_branch_ids)).all() if permitted_search_branch_ids else []
            by_id={e.id:e for e in candidates}
            by_id.update({e.id:e for e in home_candidates})
            candidates=list(by_id.values())
        if movement_name_query:
            nq=movement_name_query.casefold()
            candidates=[e for e in candidates if nq in (e.full_name or '').casefold() or nq in (e.job_code or '').casefold()]
        movement_employee_matches=sorted(candidates,key=lambda e:e.full_name)[:50]
    if movement_employee_id.isdigit():
        candidate=db.session.get(Employee,int(movement_employee_id))
        if candidate and candidate.is_active and search_gov_id:
            eff_branch=effective_branch_id_for_employee(candidate.id,today) or candidate.branch_id
            home_ok=candidate.branch_id in permitted_search_branch_ids
            current_ok=eff_branch in permitted_search_branch_ids
            branch_ok_for_search=(eff_branch==search_branch_id or candidate.branch_id==search_branch_id) if search_branch_id else (home_ok or current_ok)
            if employee_scope_ok(candidate,today) and branch_ok_for_search:
                movement_employee=candidate
    elif len(movement_employee_matches)==1:
        movement_employee=movement_employee_matches[0]
    if movement_employee:
        movement_employee_moves=(Movement.query.filter_by(employee_id=movement_employee.id,is_active=True)
                                 .order_by(Movement.id.desc()).all())
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
    entry_directory_branch_ids=set()
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
                entry_directory_branch_ids.update(b.id for b in scoped)
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

    # فروع لوحة «المدخلون الأوائل» المستخدمة في فلتر البحث بالفرع.
    entry_directory_branches=(Branch.query.filter(Branch.id.in_(entry_directory_branch_ids),Branch.is_active==True)
                              .order_by(Branch.name.asc()).all() if entry_directory_branch_ids else [])

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

    # قوائم الصفحة الرئيسية لا تعرض إلا المحافظات الواقعة ضمن نطاق الدور الحالي.
    home_movement_gov_ids=set(gids())
    home_movement_governorates=(Governorate.query.filter(Governorate.id.in_(home_movement_gov_ids),Governorate.is_active==True)
                                .order_by(Governorate.name.asc()).all() if home_movement_gov_ids else [])
    home_movement_branches=(Branch.query.filter(Branch.governorate_id.in_(home_movement_gov_ids),Branch.is_active==True)
                            .order_by(Branch.name.asc()).all() if home_movement_gov_ids else [])

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
        entry_directory_branches=entry_directory_branches,
        entry_supervisors=entry_supervisors,
        today=today,
        tomorrow=tomorrow,
        is_admin=has_role('مسؤول التطبيق'),
        is_manager_support=is_manager_support,
        manager_governorates=Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all() if is_manager_support else [],
        selected_manager_gov=selected_manager_gov,
        movement_search_governorates=home_movement_governorates,
        movement_search_branches=(Branch.query.filter(Branch.governorate_id==search_gov_id,Branch.id.in_(set(bids())),Branch.is_active==True).order_by(Branch.name.asc()).all() if search_gov_id else []),
        home_movement_governorates=home_movement_governorates,
        home_movement_branches=home_movement_branches,
        movement_search_employees=Employee.query.filter_by(is_active=True).order_by(Employee.full_name.asc()).all(),
        movement_employee=movement_employee,
        movement_employee_moves=movement_employee_moves,
        movement_employee_last=movement_employee_last,
        movement_employee_matches=movement_employee_matches,
        movement_governorate_id=movement_governorate_id,
        movement_branch_id=movement_branch_id,
        movement_name_query=movement_name_query,
        movement_employee_id=(int(movement_employee_id) if movement_employee_id.isdigit() else None),
        movement_types=MOVEMENT_TYPES,
        leave_types=LEAVE_TYPES,
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
    if is_admin or is_manager_support:
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
        admin_view=(is_admin or is_manager_support),
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


# ---------- Excel import helpers ----------
def _excel_key(value):
    s='' if value is None else str(value).strip()
    s=s.replace('\u200f','').replace('\u200e','')
    s=s.replace('أ','ا').replace('إ','ا').replace('آ','ا')
    s=s.replace('ة','ه').replace('ى','ي')
    s=re.sub(r'\s+',' ',s)
    return s.lower()

def _excel_text(value):
    if value is None: return ''
    if isinstance(value, float) and value.is_integer(): return str(int(value))
    return str(value).strip()

def _excel_date(value):
    if value is None or value=='': return None
    if isinstance(value, datetime): return value.date()
    if isinstance(value, date): return value
    txt=_excel_text(value)
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%Y/%m/%d','%d.%m.%Y','%m/%d/%Y','%m-%d-%Y'):
        try: return datetime.strptime(txt,fmt).date()
        except ValueError: pass
    return None

def _header_map(ws):
    headers={}
    for idx,cell in enumerate(ws[1],1):
        k=_excel_key(cell.value)
        if k and k not in headers: headers[k]=idx
    return headers

def _excel_headers(ws):
    return [_excel_text(c.value) for c in ws[1]]

def _cell_by_index(row, index):
    try:
        idx=int(index)
        if idx < 1 or idx > len(row): return None
        return row[idx-1].value
    except (TypeError,ValueError):
        return None

BRANCH_IMPORT_HEADERS={
    'governorate':('المحافظة','اسم المحافظة','المحافظه','governorate','governorate name','governorate_name'),
    'name':('اسم الفرع','الفرع','branch','branch name','branch_name'),
    'code':('كود الفرع','كود الفرع/الفرع','كود','branch code','branch_code','code'),
}
EMP_IMPORT_HEADERS={
    'governorate':('المحافظة','اسم المحافظة','المحافظه','governorate','governorate name','governorate_name'),
    'branch':('الفرع','اسم الفرع','branch','branch name','branch_name'),
    'name':('اسم الموظف','الموظف','اسم الموظف بالكامل','اسم الموظف كامل','full name','employee name','name'),
    'email':('البريد الإلكتروني','البريد الالكتروني','البريد','email','e-mail'),
    'job_title':('الوظيفة','المسمى الوظيفي','المسمى الوظيفى','الوظيفه','job title','job_title','title'),
    'job_code':('الكود الوظيفي','كود الوظيفة','كود شئون العاملين','كود شؤون العاملين','كود شئون العاملين للموظف','كود العامل','employee code','employee_code','job code','job_code','code'),
    'hire_date':('تاريخ التعيين','تاريخ التعيين بالعمل','تاريخ المباشرة','hire date','date of hire','hire_date'),
    'company_phone':('هاتف الشركة','تليفون الشركة','هاتف العمل','تليفون العمل','company phone','company_phone','work phone'),
    'personal_phone':('الهاتف الشخصي','تليفون شخصي','الموبايل','رقم الموبايل','رقم الهاتف','personal phone','personal_phone','mobile'),
}

def _import_spec(kind):
    return BRANCH_IMPORT_HEADERS if kind=='branches' else EMP_IMPORT_HEADERS

def _field_labels(kind):
    if kind=='branches':
        return {'governorate':'المحافظة','name':'اسم الفرع','code':'كود الفرع'}
    return {'governorate':'المحافظة','branch':'الفرع','name':'اسم الموظف','email':'البريد الإلكتروني','job_title':'الوظيفة','job_code':'الكود الوظيفي','hire_date':'تاريخ التعيين','company_phone':'هاتف الشركة','personal_phone':'الهاتف الشخصي'}

def _auto_map_headers(headers, spec):
    """Return target field -> source column index. Exact/normalized aliases first, then fuzzy tokens."""
    mapping={}
    used=set()
    normalized=[_excel_key(h) for h in headers]
    for field,names in spec.items():
        aliases=[_excel_key(n) for n in names]
        # exact alias match
        for i,h in enumerate(normalized,1):
            if i in used or not h: continue
            if h in aliases:
                mapping[field]=i; used.add(i); break
        if field in mapping: continue
        # relaxed matching for common Arabic/English header variations
        for i,h in enumerate(normalized,1):
            if i in used or not h: continue
            for a in aliases:
                if len(a)>=4 and (a in h or h in a):
                    mapping[field]=i; used.add(i); break
            if field in mapping: break
    return mapping

def _excel_import_permissions(kind):
    if kind not in ('branches','employees'): abort(404)
    if kind=='branches' and not (can('manage_structure') and has_role('مسؤول التطبيق','مشرف محافظة')): abort(403)
    if kind=='employees' and not can('manage_employees'): abort(403)

def _excel_scope_governorates():
    return {g.id for g in Governorate.query.filter_by(is_active=True).all()} if 'مسؤول التطبيق' in roles() else set(gids())

def _excel_import_page(kind, **ctx):
    _excel_import_permissions(kind)
    return render_template('excel_import.html',kind=kind,**ctx)

@app.get('/excel-import/<kind>')
@req
def excel_import_page(kind):
    return _excel_import_page(kind)

@app.get('/excel-import/<kind>/template')
@req
def excel_import_template(kind):
    _excel_import_permissions(kind)
    wb=Workbook(); ws=wb.active; ws.title='بيانات'
    if kind=='branches':
        headers=['المحافظة','اسم الفرع','كود الفرع']
        ws.append(headers); ws.append(['مثال: سوهاج','مثال: أم دومه','255'])
    else:
        headers=['المحافظة','الفرع','اسم الموظف','البريد الإلكتروني','الوظيفة','الكود الوظيفي','تاريخ التعيين','هاتف الشركة','الهاتف الشخصي']
        ws.append(headers); ws.append(['مثال: سوهاج','مثال: أم دومه','أحمد محمد','name@example.com','موظف','1001','2026-01-01','093xxxxxxx','01xxxxxxxxx'])
    for c in ws[1]: c.font=c.font.copy(bold=True)
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        letter=col[0].column_letter; ws.column_dimensions[letter].width=max(16,min(32,max(len(_excel_text(c.value)) for c in col)+2))
    data=io.BytesIO(); wb.save(data); data.seek(0)
    from flask import send_file
    return send_file(data,as_attachment=True,download_name=f'{kind}-template.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def _pending_excel_dir():
    d=os.path.join(os.getenv('TMPDIR','/tmp'),'employee_movements_excel_imports')
    os.makedirs(d,exist_ok=True)
    return d

def _pending_excel_path(token):
    return os.path.join(_pending_excel_dir(),f'{token}.xlsx')

def _pending_excel_review_path(token):
    return os.path.join(_pending_excel_dir(),f'{token}.json')

def _save_pending_excel(f):
    token=secrets.token_urlsafe(24)
    path=_pending_excel_path(token)
    f.save(path)
    return token,path

def _remove_pending_excel(token):
    if not token: return
    for path in (_pending_excel_path(token), _pending_excel_review_path(token)):
        try: os.remove(path)
        except OSError: pass

def _get_pending_excel():
    token=session.get('excel_import_token')
    if not token: return None,None
    path=_pending_excel_path(token)
    if not os.path.isfile(path):
        session.pop('excel_import_token',None); return None,None
    return token,path

def _render_mapping(kind, token, path, warning=None):
    wb=load_workbook(path,read_only=True,data_only=True)
    ws=wb.active
    headers=_excel_headers(ws)
    preview=[]
    for row in ws.iter_rows(min_row=2,max_row=6,values_only=True):
        vals=[_excel_text(v) for v in row]
        if any(vals): preview.append(vals[:len(headers)])
    wb.close()
    spec=_import_spec(kind)
    mapping=_auto_map_headers(headers,spec)
    labels=_field_labels(kind)
    return _excel_import_page(kind, mapping_step=True, token=token, headers=headers, preview=preview, fields=labels, suggested=mapping, warning=warning)

@app.post('/excel-import/<kind>/preview')
@req
def excel_import_preview(kind):
    _excel_import_permissions(kind)
    f=request.files.get('file')
    if not f or not f.filename.lower().endswith(('.xlsx','.xlsm','.xltx')):
        flash('اختر ملف Excel بصيغة .xlsx أو .xlsm أو .xltx.')
        return redirect(url_for('excel_import_page',kind=kind))
    try:
        old=session.pop('excel_import_token',None); _remove_pending_excel(old)
        token,path=_save_pending_excel(f)
        wb=load_workbook(path,read_only=True,data_only=True)
        ws=wb.active
        headers=_excel_headers(ws)
        wb.close()
        if not headers or not any(headers):
            _remove_pending_excel(token); flash('ملف Excel لا يحتوي على صف عناوين صالح.'); return redirect(url_for('excel_import_page',kind=kind))
        session['excel_import_token']=token
        return _render_mapping(kind,token,path)
    except Exception as ex:
        flash('تعذر قراءة ملف Excel: '+str(ex))
        return redirect(url_for('excel_import_page',kind=kind))

def _mapped_value(row, mapping, field):
    return _excel_text(_cell_by_index(row, mapping.get(field)))

@app.post('/excel-import/<kind>/confirm')
@req
def excel_import_confirm(kind):
    _excel_import_permissions(kind)
    token,path=_get_pending_excel()
    if not token or not path:
        flash('انتهت جلسة مطابقة ملف Excel. ارفع الملف مرة أخرى.')
        return redirect(url_for('excel_import_page',kind=kind))
    spec=_import_spec(kind); fields=_field_labels(kind)
    mapping={}
    for field in fields:
        raw=request.form.get(f'map_{field}','').strip()
        if raw:
            try: mapping[field]=int(raw)
            except ValueError: pass
    missing=[fields[k] for k in spec if k not in mapping]
    if missing:
        return _render_mapping(kind,token,path,warning='يجب مطابقة الأعمدة التالية: '+ '، '.join(missing))
    if len(set(mapping.values())) != len(mapping):
        return _render_mapping(kind,token,path,warning='لا يمكن استخدام نفس عمود Excel لأكثر من حقل. راجع المطابقة.')
    try:
        wb=load_workbook(path,read_only=True,data_only=True); ws=wb.active
        headers=_excel_headers(ws)
        if any(i<1 or i>len(headers) for i in mapping.values()):
            wb.close(); return _render_mapping(kind,token,path,warning='اختيار أحد الأعمدة غير صالح. أعد المطابقة.')
        allowed_gids=_excel_scope_governorates(); errors=[]
        govs={_excel_key(g.name):g for g in Governorate.query.filter(Governorate.is_active==True,Governorate.id.in_(allowed_gids)).all()}
        branches_by_gov={}
        for b in Branch.query.filter(Branch.is_active==True,Branch.governorate_id.in_(allowed_gids)).all():
            branches_by_gov.setdefault(b.governorate_id,{})[_excel_key(b.name)]=b
        actions=[]
        if kind=='branches':
            for rno,row in enumerate(ws.iter_rows(min_row=2,values_only=False),2):
                vals={k:_mapped_value(row,mapping,k) for k in spec}
                if not any(vals.values()): continue
                g=govs.get(_excel_key(vals['governorate']))
                if not g: errors.append(f'صف {rno}: المحافظة غير موجودة أو خارج نطاقك: {vals["governorate"]}'); continue
                if not vals['name'] or not vals['code']: errors.append(f'صف {rno}: اسم الفرع وكوده مطلوبان.'); continue
                existing=branches_by_gov.setdefault(g.id,{})
                b=existing.get(_excel_key(vals['name'])) or Branch.query.filter_by(governorate_id=g.id,code=vals['code']).first()
                if b:
                    changes={}
                    if vals['name'] and vals['name']!=b.name: changes['name']={'old':b.name,'new':vals['name']}
                    if vals['code'] and vals['code']!=b.code:
                        dup=Branch.query.filter(Branch.governorate_id==g.id,Branch.code==vals['code'],Branch.id!=b.id).first()
                        if dup: errors.append(f'صف {rno}: كود الفرع {vals["code"]} مستخدم بالفعل في فرع آخر.'); continue
                        changes['code']={'old':b.code or '—','new':vals['code']}
                    if changes: actions.append({'type':'branch','id':b.id,'row':rno,'name':b.name,'governorate':g.name,'changes':changes})
                else:
                    dup=Branch.query.filter_by(governorate_id=g.id,code=vals['code']).first()
                    if dup: errors.append(f'صف {rno}: كود الفرع {vals["code"]} مستخدم بالفعل.'); continue
                    if _excel_key(vals['name']) in existing or any(a.get('type')=='new_branch' and a.get('governorate_id')==g.id and _excel_key(a.get('values',{}).get('name'))==_excel_key(vals['name']) for a in actions):
                        errors.append(f'صف {rno}: الفرع مكرر داخل ملف Excel.'); continue
                    actions.append({'type':'new_branch','row':rno,'values':vals,'governorate_id':g.id,'governorate':g.name})
        else:
            managed_branch_ids=set(bids())
            branch_cache={}
            for b in Branch.query.filter(Branch.is_active==True,Branch.governorate_id.in_(allowed_gids),Branch.id.in_(managed_branch_ids)).all():
                branch_cache[(_excel_key(b.governorate.name),_excel_key(b.name))]=b
            emails={_excel_key(e.email):e for e in Employee.query.filter(Employee.email.isnot(None)).all()}
            job_codes={_excel_key(e.job_code):e for e in Employee.query.filter(Employee.job_code.isnot(None)).all()}
            for rno,row in enumerate(ws.iter_rows(min_row=2,values_only=False),2):
                vals={k:_mapped_value(row,mapping,k) for k in spec}
                if not any(vals.values()): continue
                g=govs.get(_excel_key(vals['governorate']))
                if not g: errors.append(f'صف {rno}: المحافظة غير موجودة أو خارج نطاقك: {vals["governorate"]}'); continue
                b=branch_cache.get((_excel_key(vals['governorate']),_excel_key(vals['branch'])))
                if not b: errors.append(f'صف {rno}: الفرع غير موجود أو خارج نطاقك: {vals["branch"]}'); continue
                required=['name','email','job_title','job_code','hire_date','company_phone','personal_phone']
                if any(not vals[x] for x in required): errors.append(f'صف {rno}: جميع بيانات الموظف مطلوبة.'); continue
                if not valid_email(vals['email']): errors.append(f'صف {rno}: البريد الإلكتروني غير صحيح.'); continue
                hd=_excel_date(_cell_by_index(row,mapping.get('hire_date')))
                if not hd: errors.append(f'صف {rno}: تاريخ التعيين غير صحيح.'); continue
                ck=_excel_key(vals['job_code']); ek=_excel_key(vals['email'])
                e=job_codes.get(ck) or emails.get(ek)
                if e:
                    # If email points to another employee while the job code points to this one, flag it.
                    if ck and ck in job_codes and ek and ek in emails and job_codes[ck].id!=emails[ek].id:
                        errors.append(f'صف {rno}: الكود الوظيفي والبريد الإلكتروني يعودان لموظفين مختلفين.'); continue
                    changes={}
                    candidate={'branch_id':b.id,'branch':b.name,'full_name':vals['name'],'email':vals['email'],'job_title':vals['job_title'],'job_code':vals['job_code'],'hire_date':hd.isoformat(),'company_phone':vals['company_phone'],'personal_phone':vals['personal_phone']}
                    current={'branch_id':e.branch_id,'branch':e.branch.name if e.branch else '—','full_name':e.full_name,'email':e.email or '','job_title':e.job_title or '','job_code':e.job_code or '','hire_date':e.hire_date.isoformat() if e.hire_date else '','company_phone':e.company_phone or '','personal_phone':e.personal_phone or ''}
                    for f,label in [('branch_id','الفرع'),('full_name','اسم الموظف'),('email','البريد الإلكتروني'),('job_title','الوظيفة'),('job_code','الكود الوظيفي'),('hire_date','تاريخ التعيين'),('company_phone','هاتف الشركة'),('personal_phone','الهاتف الشخصي')]:
                        if str(current.get(f,'')) != str(candidate.get(f,'')):
                            changes[f]={'label':label,'old':current.get(f,'—'),'new':candidate.get(f,'—')}
                    if changes: actions.append({'type':'employee','id':e.id,'row':rno,'name':e.full_name,'changes':changes})
                else:
                    if ck in job_codes or (ek and ek in emails):
                        errors.append(f'صف {rno}: يوجد تكرار داخل ملف Excel للكود الوظيفي أو البريد الإلكتروني.'); continue
                    actions.append({'type':'new_employee','row':rno,'values':vals,'hire_date':hd.isoformat(),'branch_id':b.id,'branch':b.name,'governorate':g.name})
                    job_codes[ck]=None; emails[ek]=None
        wb.close()
        review_path=_pending_excel_review_path(token)
        with open(review_path,'w',encoding='utf-8') as fh: json.dump({'kind':kind,'mapping':mapping,'actions':actions,'errors':errors},fh,ensure_ascii=False)
        session['excel_review_token']=token
        return render_template('excel_import.html',kind=kind,review_step=True,actions=actions,errors=errors,fields=fields)
    except Exception as ex:
        try: wb.close()
        except Exception: pass
        _remove_pending_excel(token); session.pop('excel_import_token',None)
        flash('تعذر تحليل ملف Excel: '+str(ex))
        return redirect(url_for('excel_import_page',kind=kind))

@app.post('/excel-import/<kind>/apply')
@req
def excel_import_apply(kind):
    _excel_import_permissions(kind)
    token=session.get('excel_review_token'); path=_pending_excel_path(token) if token else None; review_path=_pending_excel_review_path(token) if token else None
    if not token or not path or not os.path.isfile(path) or not review_path or not os.path.isfile(review_path):
        flash('انتهت جلسة مراجعة ملف Excel. ارفع الملف مرة أخرى.'); return redirect(url_for('excel_import_page',kind=kind))
    try:
        with open(review_path,'r',encoding='utf-8') as fh: review=json.load(fh)
        actions=review.get('actions',[]); selected=set(request.form.getlist('change'))
        added=updated=skipped=0; errors=list(review.get('errors',[]))
        if kind=='branches':
            for a in actions:
                if a['type']=='new_branch':
                    v=a['values']; b=Branch(governorate_id=a['governorate_id'],name=v['name'],code=v['code']); db.session.add(b); db.session.flush(); added+=1
                elif a['type']=='branch':
                    b=db.session.get(Branch,a['id']);
                    if not b: continue
                    changed=False
                    for f in ('name','code'):
                        key=f"{a['type']}:{a['id']}:{f}"
                        if key in selected:
                            setattr(b,f,a['changes'][f]['new']); changed=True
                    if changed: updated+=1
        else:
            for a in actions:
                if a['type']=='new_employee':
                    v=a['values']; e=Employee(employee_code=None,email=v['email'],full_name=v['name'],branch_id=a['branch_id'],job_title=v['job_title'],job_code=v['job_code'],hire_date=datetime.fromisoformat(a['hire_date']).date(),company_phone=v['company_phone'],personal_phone=v['personal_phone']); db.session.add(e); db.session.flush(); added+=1
                elif a['type']=='employee':
                    e=db.session.get(Employee,a['id']);
                    if not e: continue
                    changed=False
                    for f in a['changes']:
                        key=f"employee:{a['id']}:{f}"
                        if key not in selected: continue
                        new=a['changes'][f]['new']
                        if f=='branch_id': setattr(e,f,int(new))
                        elif f=='hire_date': setattr(e,f,datetime.fromisoformat(new).date())
                        else: setattr(e,f,new)
                        changed=True
                    if changed: updated+=1
        db.session.commit(); log('IMPORT','Branch' if kind=='branches' else 'Employee',0,f'Excel: إضافة {added}، تحديث {updated}، تخطي دون تغييرات {skipped}'); db.session.commit()
        _remove_pending_excel(token); session.pop('excel_import_token',None); session.pop('excel_review_token',None)
        return render_template('excel_import.html',kind=kind,import_done=True,added=added,updated=updated,skipped=skipped,errors=errors)
    except Exception as ex:
        db.session.rollback(); _remove_pending_excel(token); session.pop('excel_import_token',None); session.pop('excel_review_token',None)
        flash('تعذر تطبيق تغييرات Excel: '+str(ex)); return redirect(url_for('excel_import_page',kind=kind))

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
                if existing.resignation_date is not None:
                    flash('الموظف مسجل كمستقيل. أعد تفعيله أولًا من «الموظفون المستقيلون» بتاريخ إعادة التعيين، ثم حدّث بياناته.')
                    return redirect(url_for('resigned_employees'))
                # الموظف غير ظاهر في القائمة لأنه معطّل إداريًا. لا ننشئ سجلًا ثانيًا.
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
    rows=[e for e in query.order_by(Employee.full_name).all() if (e.branch_id in allowed_search_branch_ids or effective_branch_id_for_employee(e.id) in allowed_search_branch_ids)]
    if branch_filter.isdigit() and int(branch_filter) in allowed_search_branch_ids:
        rows=[e for e in rows if employee_is_effectively_in_branch(e,int(branch_filter))]
    govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if supervisor_search_all else (Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all() if gids() else [])
    allowed_search_gov_ids={g.id for g in govs}
    if gov_filter.isdigit() and int(gov_filter) in allowed_search_gov_ids:
        branches=Branch.query.filter(Branch.governorate_id==int(gov_filter),Branch.is_active==True,Branch.id.in_(search_branch_ids)).order_by(Branch.name).all()
        if not (branch_filter.isdigit() and int(branch_filter) in [b.id for b in branches]): branch_filter=''
        query=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_([b.id for b in branches]))
        if q:
            like=f'%{q}%'; query=query.filter(db.or_(Employee.full_name.ilike(like),Employee.job_code.ilike(like),Employee.job_title.ilike(like)))
        rows=[e for e in query.order_by(Employee.full_name).all() if employee_is_effectively_in_branch(e,int(branches[0].id))] if len(branches)==1 else [e for e in query.order_by(Employee.full_name).all() if any(employee_is_effectively_in_branch(e,b.id) for b in branches)]
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

@app.post('/employees/<int:i>/resign')
@req
def employee_resign(i):
    e=db.session.get(Employee,i)
    if not e or not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if not e.is_active:
        flash('الموظف موجود بالفعل ضمن الموظفين المستقيلين.')
        return redirect('/employees')
    raw_date=(request.form.get('resignation_date') or '').strip()
    resignation_date=parse_date(raw_date)
    if not resignation_date:
        flash('يجب تحديد تاريخ الاستقالة.')
        return redirect('/employees')
    if resignation_date > date.today():
        flash('تاريخ الاستقالة لا يمكن أن يكون في المستقبل.')
        return redirect('/employees')
    e.is_active=False
    e.resignation_date=resignation_date
    e.rehire_date=None
    e.resignation_by=me().id if me() else None
    # الاحتفاظ بـ deleted_at داخليًا للتوافق مع السجلات القديمة ومنع ظهور الموظف في القوائم النشطة.
    e.deleted_at=datetime.utcnow()
    e.deleted_by=me().id if me() else None
    # إنهاء أي انتداب مفتوح مع الاحتفاظ بالحركة كاملة في التاريخ.
    open_moves=Movement.query.filter_by(employee_id=e.id,is_active=True,movement_type='انتداب',assignment_state='ساري').all()
    for m in open_moves:
        m.assignment_state='مغلق'
        m.closed_by=me().id if me() else None
        m.closed_at=datetime.utcnow()
        m.closure_reason='استقالة الموظف'
    assignment=organizational_entry_for_employee(e)
    if assignment:
        assignment.is_active=False
    # إزالة ارتباطات المدخل الأول التنظيمية حتى لا يبقى الموظف المستقيل مرتبطًا بفروع.
    if e.user_id:
        linked_user=db.session.get(User,e.user_id)
        if linked_user:
            UserRole.query.filter_by(user_id=linked_user.id,role='المدخل الأول').delete()
            UserBranch.query.filter_by(user_id=linked_user.id).delete()
            SupervisorEntry.query.filter_by(entry_id=linked_user.id).delete()
            if not actual_roles(linked_user):
                linked_user.is_active=False
    log('RESIGN','Employee',i,f'استقالة الموظف: {e.full_name} بتاريخ {resignation_date.isoformat()}')
    db.session.commit()
    flash(f'تم تسجيل استقالة {e.full_name} بتاريخ {resignation_date.strftime("%Y-%m-%d")}. أزيل من قوائم الفرع ونُقل إلى الموظفين المستقيلين مع الاحتفاظ بكل تاريخه.')
    return redirect(url_for('employees'))

@app.post('/employees/<int:i>/delete')
@req
def ed(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if not e: abort(404)
    # حذف منطقي إداري استثنائي؛ مسار دورة حياة الموظف الطبيعي هو «استقالة».
    e.is_active=False
    e.deleted_at=datetime.utcnow()
    e.deleted_by=me().id if me() else None
    assignment=organizational_entry_for_employee(e)
    if assignment: assignment.is_active=False
    log('DELETE','Employee',i,f'حذف منطقي إداري للموظف: {e.full_name}')
    db.session.commit()
    flash('تم إخفاء الموظف إداريًا. لا يُستخدم هذا المسار لتسجيل الاستقالة؛ استخدم «استقالة».')
    return redirect(url_for('employees'))

@app.get('/employees/resigned')
@req
def resigned_employees():
    if not can('manage_employees'): abort(403)
    # الموظفون المستقيلون يُعرضون من نطاق الفروع السابق، مع إبقاء السجل محفوظًا.
    bs=bids()
    q=Employee.query.filter((Employee.resignation_date.isnot(None)) | (Employee.deleted_at.isnot(None)))
    if bs:
        q=q.filter(Employee.branch_id.in_(bs))
    rows=q.order_by(Employee.resignation_date.desc().nullslast(),Employee.deleted_at.desc().nullslast(),Employee.full_name).all()
    return render_template('employee_resigned.html',rows=rows)

@app.get('/employees/resigned')
@req
def deleted_employees_legacy():
    return redirect(url_for('resigned_employees'))

@app.post('/employees/<int:i>/reactivate')
@req
def employee_reactivate(i):
    e=db.session.get(Employee,i)
    if not e or (e.resignation_date is None and e.deleted_at is None): abort(404)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    raw_date=(request.form.get('rehire_date') or '').strip()
    rehire_date=parse_date(raw_date)
    if not rehire_date:
        flash('يجب تحديد تاريخ إعادة التعيين.')
        return redirect(url_for('resigned_employees'))
    if e.resignation_date and rehire_date < e.resignation_date:
        flash('تاريخ إعادة التعيين يجب أن يكون في أو بعد تاريخ الاستقالة.')
        return redirect(url_for('resigned_employees'))
    e.is_active=True
    e.rehire_date=rehire_date
    e.deleted_at=None
    e.deleted_by=None
    e.resignation_by=None
    log('REACTIVATE','Employee',i,f'إعادة تعيين الموظف: {e.full_name} بتاريخ {rehire_date.isoformat()}')
    db.session.commit()
    flash(f'تمت إعادة تفعيل {e.full_name} بتاريخ {rehire_date.strftime("%Y-%m-%d")}. أصبح الموظف متاحًا للفرع مرة أخرى.')
    return redirect(url_for('card',i=e.id))
@app.get('/employee/<int:i>')
@req
def card(i):
    e=db.session.get(Employee,i)
    if not e: abort(404)
    if not e.is_active and not (can('manage_employees') and can_manage_employee(e)):
        abort(403)
    ms=Movement.query.filter_by(employee_id=i,is_active=True).order_by(Movement.from_date.desc().nullslast(),Movement.permission_date.desc().nullslast(),Movement.id.desc()).all(); last={k:next((m for m in ms if m.movement_type==k),None) for k in MOVEMENT_TYPES}; current_assignment=current_assignment_for_employee(e.id); current_branch=(current_assignment.destination if current_assignment and current_assignment.destination else e.branch); return render_template('employee.html',e=e,ms=ms,last=last,current_assignment=current_assignment,current_branch=current_branch)

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

def assistant_search_normalize(text):
    """تطبيع النص العربي للبحث والفهم فقط دون تغيير القيمة الأصلية المخزنة."""
    import unicodedata
    text = unicodedata.normalize('NFKC', str(text or ''))
    # إزالة التشكيل والتطويل وعلامات الوقف الزائدة.
    text = re.sub(r'[\u064B-\u065F\u0670\u0640]', '', text)
    # توحيد صور الهمزة والألف، والألف المقصورة/الياء، والتاء المربوطة/الهاء
    # حتى تنجح المطابقة المرنة مثل: إجازة/اجازه، منى/مني، هدى/هدي.
    text = text.translate(str.maketrans({
        'أ':'ا', 'إ':'ا', 'آ':'ا', 'ٱ':'ا',
        'ى':'ي', 'ئ':'ي', 'ؤ':'و',
        'ة':'ه',
    }))
    text = re.sub(r'[\s\u200f\u200e]+', ' ', text).strip().lower()
    return text

def assistant_normalize(text):
    """تطبيع عام للنص، مع الاحتفاظ بالقيمة الأصلية لعرضها كما هي."""
    trans=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹','01234567890123456789')
    return (text or '').translate(trans).strip()

def assistant_find_employee(value):
    value=(value or '').strip()
    if not value: return None, []
    rows=assistant_scope_employee_query()
    nv=assistant_search_normalize(value)
    exact=[e for e in rows if assistant_search_normalize(e.full_name)==nv or (e.job_code and assistant_search_normalize(e.job_code)==nv)]
    if len(exact)==1: return exact[0], exact
    parts=[x for x in re.split(r'\s+',nv) if len(x)>=2]
    matches=[e for e in rows if nv in assistant_search_normalize(e.full_name) or (e.job_code and nv in assistant_search_normalize(e.job_code))]
    if not matches and parts:
        matches=[e for e in rows if all(part in assistant_search_normalize(e.full_name) for part in parts)]
    return (matches[0] if len(matches)==1 else None), matches

def assistant_find_branch(value, governorate_id=None):
    value=(value or '').strip()
    q=Branch.query.filter(Branch.is_active==True)
    if governorate_id: q=q.filter(Branch.governorate_id==governorate_id)
    allowed=set(bids())
    rows=q.filter(Branch.id.in_(allowed)).order_by(Branch.name).all() if allowed else []
    nv=assistant_search_normalize(value)
    exact=[b for b in rows if assistant_search_normalize(b.name)==nv or (b.code and assistant_search_normalize(b.code)==nv)]
    if len(exact)==1: return exact[0], exact
    matches=[b for b in rows if nv in assistant_search_normalize(b.name) or (b.code and nv in assistant_search_normalize(b.code))]
    return (matches[0] if len(matches)==1 else None), matches

def assistant_parse_date(text):
    m=re.search(r'(20\d{2})[-/](\d{1,2})[-/](\d{1,2})', text or '')
    if not m: return None
    return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'

def assistant_live_context_for_prompt(text, local_a=None):
    """Build a small live DB snapshot for semantic understanding; refreshed per request."""
    parts=[]
    try:
        emp_id=(local_a or {}).get('employee_id')
        if emp_id:
            e=db.session.get(Employee, emp_id)
            if e:
                cb=current_assignment_for_employee(e.id)
                parts.append(f"موظف محدد: {e.full_name} | كود الموظف: {e.job_code or ''} | الوظيفة: {e.job_title or ''} | فرع التعيين: {e.branch.name if e.branch else ''} | الفرع الحالي: {cb.destination.name if cb and cb.destination else (e.branch.name if e.branch else '')}")
        br_id=(local_a or {}).get('branch_id')
        if br_id:
            b=db.session.get(Branch, br_id)
            if b:
                emps=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
                parts.append(f"فرع محدد: {b.name} | المحافظة: {b.governorate.name if b.governorate else ''} | عدد الموظفين المسجلين على الفرع: {len(emps)} | الأسماء: {', '.join(e.full_name for e in emps[:80])}")
        # For a direct employee-name query, expose only matching live records rather than the whole DB.
        if not parts:
            nv=assistant_search_normalize(text)
            if nv:
                matches=[e for e in assistant_scope_employee_query() if nv in assistant_search_normalize(e.full_name) or (e.job_code and nv in assistant_search_normalize(e.job_code))][:12]
                if matches:
                    parts.append('مطابقة موظفين مباشرة: '+ ' | '.join(f"{e.id}:{e.full_name} (فرع {e.branch.name if e.branch else ''})" for e in matches))
    except Exception:
        pass
    return '\n'.join(parts)

def assistant_llm_parse(text, chat=None, live_context=''):
    """Semantic Arabic intent/field extraction via OpenAI Responses API."""
    api_key=os.getenv('OPENAI_API_KEY','').strip()
    if not api_key:
        return None
    model=os.getenv('OPENAI_MODEL','gpt-5.6-luna').strip() or 'gpt-5.6-luna'
    history=[]
    for m in (chat or [])[-10:]:
        if m.get('role') in ('user','assistant') and m.get('text'):
            history.append({'role':m['role'],'content':m['text'][:2000]})
    history.append({'role':'user','content':text[:4000]})
    schema={
      'type':'object','additionalProperties':False,
      'properties':{
        'intent':{'type':'string','enum':['employee_add','employee_status','employee_info','employee_movements','branch_status','branch_info','branch_entry','governorate_employees','governorate_assignments_today','movement_people_today','employee_topic','register_movement','topic_options','navigate','help']},
        'topic':{'type':['string','null'],'enum':['leave','assignment','permission','entry','employee','branch','reports','admin','users','delegation','replacement','audit',None]},
        'employee_name':{'type':['string','null']},
        'employee_id':{'type':['integer','null']},
        'branch_name':{'type':['string','null']},
        'branch_id':{'type':['integer','null']},
        'governorate_id':{'type':['integer','null']},
        'governorate_name':{'type':['string','null']},
        'candidate_ids':{'type':'array','items':{'type':'integer'}},
        'movement_type':{'type':['string','null'],'enum':['إجازة','انتداب','إذن',None]},
        'leave_type':{'type':['string','null']},
        'destination_name':{'type':['string','null']},
        'from_date':{'type':['string','null']},
        'to_date':{'type':['string','null']},
        'permission_date':{'type':['string','null']},
        'open_assignment':{'type':'boolean'},
        'navigate_url':{'type':['string','null']},
        'reply':{'type':['string','null']},
        'employee_field':{'type':['string','null'],'enum':['status','job_title','job_code','employee_code','branch','governorate','hire_date','company_phone','personal_phone','phone','last_leave','last_assignment','last_permission','movements','basic',None]}
      },
      'required':['intent','topic','employee_name','employee_id','branch_name','branch_id','governorate_id','governorate_name','candidate_ids','movement_type','leave_type','destination_name','from_date','to_date','permission_date','open_assignment','navigate_url','reply','employee_field']
    }
    govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name.asc()).all()
    branches=Branch.query.filter_by(is_active=True).order_by(Branch.name.asc()).all()
    role_text='، '.join(roles(me()))
    gov_catalog=' | '.join(f'{g.id}:{g.name}' for g in govs)
    branch_catalog=' | '.join(f'{b.id}:{b.name} (محافظة {b.governorate.name if b.governorate else ""})' for b in branches[:500])
    system=f"""أنت العقل الحواري لمساعد إداري داخل نظام إدارة حركات الموظفين. لا تعتمد على كلمات أو جمل محفوظة ولا تقارن النص بقائمة أوامر. افهم المعنى والسياق والهدف حتى لو كانت الصياغة عامية أو مختصرة أو بها أخطاء. أنت لا تنفذ بنفسك؛ تستخرج المقصود والكيانات، ثم ينفذ التطبيق بعد التحقق من الصلاحيات والبيانات.

الدور الحالي للمستخدم: {role_text}.
بيانات حية مرتبطة بطلب المستخدم (تُجلب من قاعدة البيانات عند كل طلب ولا تُعامل كذاكرة ثابتة): {live_context or 'لا توجد مطابقة مباشرة بعد'}.
المحافظات المتاحة في التطبيق: {gov_catalog}
الفروع المتاحة: {branch_catalog}

يمكنك فهم أي سؤال عن بيانات الموظفين، الفروع، المحافظات، المدخلين الأوائل، الحركات، الإجازات، الانتدابات، الانتدابات المفتوحة، الأذونات، التقارير، المستخدمين، الصلاحيات، التفويض، الاستبدال، سجل العمليات، أو أي وظيفة موجودة في النظام. إذا كان الطلب عامًا أو كان مجرد كلمة/اسم/موضوع، لا تعتبره help: استنتج الموضوع الأنسب من المعنى والسياق وأعد topic_options أو intent مناسبًا. إذا قال المستخدم موضوعًا بعد أن كان الحديث عن موظف أو فرع، اربطه بالكيان الأخير في سياق المحادثة ما لم يوجد تعارض. مثال: بعد عرض بيانات موظف ثم قال المستخدم 'إجازة' أو 'تسجيل إجازة'، افهم أنه يريد إجراءً متعلقًا بهذا الموظف واسأل فقط عن البيانات الناقصة. لا تستخدم help إلا إذا تعذر حتى تحديد موضوع عام أو كيان يمكن البناء عليه. إذا كان ناقصًا، اطلب المعلومة الناقصة بدل قول 'لم أفهم'. لا تخترع أسماء أو أرقامًا أو تواريخ. إذا كانت هناك عدة احتمالات، أعد candidate_ids إن أمكن أو اتركها فارغة ليحل التطبيق الالتباس. لا تحصر نفسك في أمثلة أو صيغ أزرار التطبيق. استخدم intent المناسب من المخطط فقط كتصنيف تقني، وليس كقائمة كلمات مسموحة."""
    payload={'model':model,'input':[{'role':'system','content':system}]+history,
             'text':{'format':{'type':'json_schema','name':'assistant_intent','strict':True,'schema':schema}},
             'max_output_tokens':700}
    req=urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Authorization':'Bearer '+api_key,'Content-Type':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            data=json.loads(r.read().decode('utf-8'))
        chunks=[]
        for item in data.get('output',[]):
            for c in item.get('content',[]) if isinstance(item,dict) else []:
                if c.get('type')=='output_text' and c.get('text'):
                    chunks.append(c['text'])
        raw=''.join(chunks).strip()
        return json.loads(raw) if raw else None
    except Exception:
        return None

def assistant_is_greeting(text):
    n=assistant_search_normalize(text)
    greetings=(
        'السلام عليكم','السلام عليكم ورحمة الله وبركاته','وعليكم السلام',
        'صباح الخير','مساء الخير','اهلا','اهلاً','مرحبا','مرحباً','هاي','هلا','السلام عليكم ورحمة الله وبركاته'
    )
    return any(n==assistant_search_normalize(g) or n.startswith(assistant_search_normalize(g)+' ') for g in greetings)

def assistant_greeting_reply(text):
    n=assistant_search_normalize(text)
    if 'صباح الخير' in n:
        return 'صباح النور ☀️ أهلاً بك. أنا معك، ويمكنك سؤالي عن أي موظف أو فرع أو حركة أو تنفيذ أي إجراء متاح لك.'
    if 'مساء الخير' in n:
        return 'مساء النور 🌙 أهلاً بك. أنا معك، ويمكنك سؤالي عن أي موظف أو فرع أو حركة أو تنفيذ أي إجراء متاح لك.'
    if 'السلام عليكم' in n:
        return 'وعليكم السلام ورحمة الله وبركاته 🌷 أهلاً بك. كيف أساعدك؟'
    return 'أهلاً بك 🌷 كيف أساعدك؟'

def assistant_employee_field(text):
    n=assistant_search_normalize(text)
    if any(x in n for x in ('الحاله','حالته','حالته الان','حاله الموظف','متواجد','موجود','في اجازه','منتدب')): return 'status'
    if any(x in n for x in ('الوظيفه','وظيفته','المسمى الوظيفي','المسمى الوظيفى')): return 'job_title'
    if any(x in n for x in ('الكود الوظيفي','الكود الوظيفى','كود الموظف','كود شئون العاملين','كود شؤون العاملين','كود شئون')): return 'job_code'
    if any(x in n for x in ('فرع التعيين','فرعه','فرع الموظف','الفرع الحالي','فين فرعه','اين فرعه','اين يعمل','بيشتغل فين')): return 'branch'
    if any(x in n for x in ('المحافظه','محافظته','تابع لاي محافظه','تابع لاى محافظه')): return 'governorate'
    if any(x in n for x in ('تاريخ التعيين','اتعين امتى','تاريخ تعيينه')): return 'hire_date'
    if any(x in n for x in ('هاتف الشركه','تليفون الشركه','هاتف العمل','رقم العمل')): return 'company_phone'
    if any(x in n for x in ('رقم الهاتف','رقم التليفون','رقم الموبايل','التليفون','الهاتف')): return 'phone'
    if any(x in n for x in ('الهاتف الشخصي','تليفونه الشخصي','رقم موبايله','رقم هاتفه')): return 'personal_phone'
    if any(x in n for x in ('اخر اجازه','اخر اجازة','آخر اجازه','آخر إجازة','اجازته الاخيره','اجازته')): return 'last_leave'
    if any(x in n for x in ('اخر انتداب','آخر انتداب','انتدابه الاخير','اخر ماموريه','آخر مأمورية')): return 'last_assignment'
    if any(x in n for x in ('اخر اذن','آخر إذن','اذنه الاخير')): return 'last_permission'
    if any(x in n for x in ('حركاته','سجل حركاته','سجل حركات','تاريخ حركاته','كل حركاته')): return 'movements'
    if any(x in n for x in ('بياناته','بيانات الموظف','بطاقته','بطاقة الموظف','معلوماته','بيانات')): return 'basic'
    return None

def assistant_employee_from_mixed_phrase(text):
    cleaned=assistant_normalize(text)
    # أزل عبارات السؤال والبيان مع الإبقاء على اسم الموظف، مثل:
    # "ما وظيفة كيرلس" / "رقم الهاتف كيرلس" / "بيانات كيرلس".
    patterns=(
        r'\b(?:ما|ماذا|هل|عايز|اريد|أريد|اعرض|عرض|بيانات|بياناته|بطاقة|بطاقته|حالة|حالته|الموظف|موظفة|موظف)\b',
        r'\b(?:الوظيفة|وظيفته|المسمى الوظيفي|المسمى الوظيفى|رقم الهاتف|رقم التليفون|رقم الموبايل|الهاتف|التليفون|هاتف العمل|هاتف الشركة|الهاتف الشخصي|الكود الوظيفي|كود شئون العاملين|فرع التعيين|الفرع الحالي|المحافظة|تاريخ التعيين|آخر إجازة|اخر اجازه|آخر انتداب|اخر انتداب|آخر إذن|اخر اذن|حركاته|سجل حركاته|سجل الحركات|بيانات الموظف|معلوماته)\b',
        r'\b(?:إجازة|اجازة|الإجازة|الاجازه|انتداب|الانتداب|مأمورية|مأموريه|إذن|اذن|الأذن|الاذن)\b',
        r'\b(?:آخر|اخر|الاخير|الأخير|تفاصيل|تفصيل|سجل|حركات|حركه|حركة)\b',
        r'\b(?:في|فى|عن|من|لـ|ل|به|له)\b'
    )
    for pat in patterns: cleaned=re.sub(pat,' ',cleaned,flags=re.I)
    cleaned=re.sub(r'[؟?،,؛;:]+',' ',cleaned); cleaned=re.sub(r'\s+',' ',cleaned).strip()
    return assistant_find_employee(cleaned) if cleaned else (None,[])

def assistant_parse(text):
    t=assistant_normalize(text)
    if assistant_is_greeting(t):
        return {'intent':'greeting','reply':assistant_greeting_reply(t)}
    # فهم لغوي مرن: نطبع الصيغ الشائعة ونفسر المقصود حتى لو لم يستخدم المستخدم
    # نفس تسمية الزر داخل التطبيق.
    low=t.lower()
    # تطبيع إضافي خاص بفهم النوايا: يسمح بتطابق الهمزات، ى/ي، ة/ه،
    # والتشكيل دون تغيير النص الأصلي المستخدم في استخراج الأسماء والتواريخ.
    intent_norm=assistant_search_normalize(t)
    compact=re.sub(r'[\s_\-]+','',low)
    def has_any(*words):
        # المطابقة على النص الأصلي + النص الموحّد حتى تعمل مثلاً: إجازة/اجازة/اجازه
        # وكذلك منى/مني وهكذا.
        return any((w in t or w in low or assistant_search_normalize(w) in intent_norm) for w in words)
    # عبارات موضوعية مباشرة: أي صياغة تدل على الإجازة/الانتداب/الإذن/المدخل الأول.
    leave_words=('إجازة','اجازة','اجازات','الإجازات','الاجازات','عطلة','عطلات')
    assign_words=('انتداب','انتدابات','مأمورية','مأموريات')
    perm_words=('إذن','اذن','أذونات','اذونات')
    entry_words=('مدخل أول','مدخل الاول','مدخل الأول','المدخل الأول','المدخل الاول','مدخلين أوائل','المدخلين الأوائل')
    action_words=('سجل','تسجيل','سجّل','ادخل','إدخال','أدخل','اضف','أضف','إضافة','اعمل','عمل','نفذ','تنفيذ','عين','تعيين')
    query_words=('حالة','اعرض','عرض','استعلم','استعلام','اسم','من هو','مين','موظفين','الموظفون','الموظفين','بيانات','سجل')
    employee_words=('موظف','الموظف','الموظفين','الموظفون','موظفة','موظفات')
    employee_add_words=('جديد','جديدة','إضافة','اضافة','أضف','اضف','إدخال','ادخال','تعيين')
    # v35.46 — استعلامات الانتداب الحالية حسب المحافظة/التاريخ.
    # مثال: «مين منتدب النهارده فى محافظة سوهاج» يجب أن يفهم كاستعلام
    # عن الانتدابات السارية اليوم داخل المحافظة، وليس كموضوع «انتداب» عام.
    today_words=('النهارده','اليوم','دلوقتي','حاليا','حاليًا','حاليه','الحاليه','الان','الآن')
    if has_any('منتدب','منتدبين','منتدبة','منتدبات','انتداب') and has_any('مين','من','اسماء','أسماء','موظفين','الموظفين') and has_any(*today_words) and has_any('محافظة','المحافظه','المحافظة','في','فى','داخل'):
        gm=re.search(r'(?:محافظة|المحافظه|المحافظة)\s+([^؟?،,؛\n]+)', t, re.I)
        if gm:
            place=gm.group(1).strip()
        else:
            gm=re.search(r'(?:في|فى|داخل)\s+(?:محافظة\s+)?([^؟?،,؛\n]+)', t, re.I)
            place=gm.group(1).strip() if gm else ''
        govs=[g for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if place and assistant_search_normalize(place) in assistant_search_normalize(g.name)]
        if len(govs)==1:
            return {'intent':'governorate_assignments_today','governorate_id':govs[0].id,'governorate_name':govs[0].name}
        if not govs and place:
            # بعض الصياغات تكون «فى سوهاج» بدون كلمة محافظة.
            govs=[g for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if assistant_search_normalize(place) == assistant_search_normalize(g.name)]
            if len(govs)==1:
                return {'intent':'governorate_assignments_today','governorate_id':govs[0].id,'governorate_name':govs[0].name}

    # v35.48 — استعلامات الحركة حسب المكان واليوم بصياغة طبيعية.
    # أمثلة: «مين إجازة في الإسكندرية»، «مين انتداب في سوهاج»،
    # «مين إجازة اليوم في طما»، «مين عنده إذن اليوم في طما».
    # وجود «مين» + نوع حركة + مكان يعني بحثًا في البيانات، وليس فتح خيارات الموضوع.
    movement_query_words = has_any('مين','من','اسماء','أسماء','موظفين','الموظفين','الموظفون')
    movement_kind = None
    if has_any(*leave_words): movement_kind='إجازة'
    elif has_any(*assign_words) or has_any('منتدب','منتدبين','منتدبة','منتدبات'): movement_kind='انتداب'
    elif has_any(*perm_words): movement_kind='إذن'
    if movement_query_words and movement_kind and has_any('في','فى','داخل','بمحافظة','بفرع','محافظة','فرع'):
        pm=re.search(r'(?:في|فى|داخل|بمحافظة|بفرع|محافظة|فرع)\s+(?:محافظة\s+|فرع\s+)?(.+?)(?:\s+(?:اليوم|النهارده|دلوقتي|حاليًا|حاليا|الان|الآن))?\s*$', t, re.I)
        place=pm.group(1).strip() if pm else ''
        place=re.sub(r'\s+(?:اليوم|النهارده|دلوقتي|حاليًا|حاليا|الان|الآن)\s*$', '', place, flags=re.I).strip(' ؟?,،؛;:')
        # «في محافظة سوهاج» يجب أن تذهب للمحافظة، بينما «في طما» يمكن أن تكون فرعًا.
        explicit_gov=bool(re.search(r'(?:بمحافظة|محافظة)\s+', t, re.I))
        explicit_branch=bool(re.search(r'(?:بفرع|فرع)\s+', t, re.I))
        # الأولوية للمحافظة عند التطابق التام: إذا كان هناك محافظة باسم «سوهاج»
        # وفرع باسم «سوهاج»، فعبارة «في سوهاج» تعني المحافظة ما لم يقل المستخدم صراحة «فرع سوهاج».
        govs=[]
        if not explicit_branch:
            govs=[g for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                  if assistant_search_normalize(place)==assistant_search_normalize(g.name)]
            if not govs:
                govs=[g for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                      if assistant_search_normalize(place) in assistant_search_normalize(g.name)]
        if len(govs)==1 and not explicit_branch:
            return {'intent':'movement_people_today','movement_type':movement_kind,'governorate_id':govs[0].id,'governorate_name':govs[0].name,'place_type':'governorate','place_name':govs[0].name}
        br,bmatches=assistant_find_branch(place) if not explicit_gov else (None,[])
        if br and not explicit_gov:
            return {'intent':'movement_people_today','movement_type':movement_kind,'branch_id':br.id,'branch_name':br.name,'place_type':'branch','place_name':br.name}

    # استعلام الحركة بدون تحديد مكان: «مين انتداب؟»، «مين إجازة؟»، «مين عنده إذن؟»
    # يُنفذ كبحث عام داخل نطاق صلاحيات المستخدم بدل فتح قائمة الخيارات أو إرجاع «لم أجد».
    if movement_query_words and movement_kind and not has_any('في','فى','داخل','بمحافظة','بفرع','محافظة','فرع'):
        return {'intent':'movement_people_today','movement_type':movement_kind,'place_type':'all','place_name':'كل النطاق'}

    # استعلامات عامة بصياغة طبيعية: "اسماء موظفين"، "الموظفين في جهينه".
    if has_any('موظفين','الموظفين','الموظفون','اسماء موظفين','أسماء موظفين','اسماء الموظفين','أسماء الموظفين'):
        pm=re.search(r'(?:في|فى|بـ|ب|داخل)\s+(?:فرع\s+)?([^؟?،,؛\n]+)', t, re.I)
        if pm:
            place=pm.group(1).strip()
            br,bmatches=assistant_find_branch(place)
            if br:
                return {'intent':'branch_status','branch_id':br.id,'branch_name':br.name,'candidate_ids':[b.id for b in bmatches[:10]]}
            govs=[g for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if assistant_search_normalize(place) in assistant_search_normalize(g.name)]
            if len(govs)==1:
                return {'intent':'governorate_employees','governorate_id':govs[0].id,'governorate_name':govs[0].name}
        return {'intent':'employee_topic'}

    # طلبات مثل: موظف جديد / إضافة موظف / أريد إدخال موظف جديد
    # تُفهم كطلب إدارة موظف، وليس كاستعلام عن موظف موجود.
    if has_any(*employee_words) and has_any(*employee_add_words) and can('manage_employees'):
        return {'intent':'employee_add'}
    if has_any(*employee_words) and has_any('جديد','جديدة') and not has_any('حالة','سجل','بيانات','فرع'):
        if can('manage_employees'):
            return {'intent':'employee_add'}
        return {'intent':'employee_topic'}
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
    mixed_emp,mixed_matches=assistant_employee_from_mixed_phrase(t)
    if mixed_emp or mixed_matches:
        field=assistant_employee_field(t)
        if field=='status':
            return {'intent':'employee_status','employee_id':mixed_emp.id if mixed_emp else None,'employee_name':t,'candidate_ids':[e.id for e in mixed_matches[:10]],'employee_field':field}
        return {'intent':'employee_info','employee_id':mixed_emp.id if mixed_emp else None,'employee_name':t,'candidate_ids':[e.id for e in mixed_matches[:10]],'employee_field':field or 'basic'}

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
    # المطابقة النهائية للموضوع تعتمد على النص الموحّد، لذلك لا تفشل
    # صيغ مثل: اجازه / اجازه / إجازة، أو إذن / اذن.
    topic_norm=assistant_search_normalize(t).strip()
    if topic_norm in ('اجازه','الاجازه','اجازات','الاجازات','عطله','عطلات'):
        return {'intent':'topic_options','topic':'leave'}
    if topic_norm in ('انتداب','الانتداب','مأموريه','المأموريه','ماموريه','الماموريه'):
        return {'intent':'topic_options','topic':'assignment'}
    if topic_norm in ('اذن','الاذن','اذونات','الاذونات'):
        return {'intent':'topic_options','topic':'permission'}
    if low.strip() in ('مدخل اول','مدخل أول','المدخل الاول','المدخل الأول','مدخل أولاً','المدخل الاول'):
        return {'intent':'topic_options','topic':'entry'}
    if low.strip() in ('موظف','الموظف','موظفين','الموظفين','الموظفون','موظفة','موظفات'):
        return {'intent':'topic_options','topic':'employee'}
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

    # الإدخال الحر: لا نفترض أن المستخدم كتب "سؤالاً". أي نص قد يكون اسم موظف،
    # اسم فرع، اسم محافظة، أو موضوعاً مختصراً. نبحث في بيانات النظام أولاً.
    emp, ematches = assistant_find_employee(t)
    if emp or ematches:
        return {'intent':'employee_info','employee_id':emp.id if emp else None,
                'employee_name':t,'candidate_ids':[e.id for e in ematches[:10]],'employee_field':assistant_employee_field(t) or 'basic'}
    br, bmatches = assistant_find_branch(t)
    if br or bmatches:
        return {'intent':'branch_status','branch_id':br.id if br else None,
                'branch_name':t,'candidate_ids':[b.id for b in bmatches[:10]]}
    gov_matches=[g for g in Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
                 if assistant_search_normalize(t) in assistant_search_normalize(g.name)]
    if gov_matches:
        if len(gov_matches)==1:
            return {'intent':'governorate_employees','governorate_id':gov_matches[0].id,
                    'governorate_name':gov_matches[0].name}
        return {'intent':'employee_topic','candidate_ids':[g.id for g in gov_matches[:10]]}

    # موضوع مختصر بدون فعل: نعرض ما يمكن عمله في هذا الموضوع، لا رسالة مساعدة عامة.
    if has_any(*leave_words): return {'intent':'topic_options','topic':'leave'}
    if has_any(*assign_words): return {'intent':'topic_options','topic':'assignment'}
    if has_any(*perm_words): return {'intent':'topic_options','topic':'permission'}
    if has_any(*entry_words): return {'intent':'topic_options','topic':'entry'}
    if has_any('موظف','موظفين','موظفون','اسماء','أسماء'): return {'intent':'employee_topic'}
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
    if topic=='employee':
        items=[
            {'label':'إضافة موظف جديد','prompt':'إضافة موظف جديد','icon':'➕','kind':'action','url':'/employees'},
            {'label':'تعديل بيانات موظف','prompt':'تعديل بيانات موظف','icon':'✏️','kind':'action','url':'/employees/edit-data'},
            {'label':'البحث عن موظف','prompt':'ابحث عن موظف','icon':'🔎','kind':'query','url':'/employees'},
            {'label':'الموظفون المستقيلون','prompt':'اعرض الموظفين المستقيلين','icon':'♻️','kind':'query','url':'/employees/resigned'},
        ]
        if not can('manage_employees'):
            items=[x for x in items if x['kind']=='query']
        return {'title':'خيارات الموظفين','answer':'ما الذي تريد فعله بخصوص الموظفين؟','topic_items':items}
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
        (((Movement.movement_type=='إجازة') & (Movement.from_date<=today) & (Movement.to_date>=today)) | ((Movement.movement_type=='انتداب') & (Movement.assignment_state!='مغلق') & (Movement.from_date<=today) & ((Movement.to_date==None) | (Movement.to_date>=today)))) |
        ((Movement.movement_type=='إذن') & (Movement.permission_date==today))
    ).order_by(Movement.id.desc()).all()
    if not active: return 'متواجد في الفرع'
    m=active[0]
    if m.movement_type=='إجازة': return f'إجازة — {m.leave_type or ""} — حتى {m.to_date}'
    if m.movement_type=='انتداب': return f'انتداب مفتوح — {m.destination.name if m.destination else "غير محدد"}' if m.to_date is None else f'انتداب — {m.destination.name if m.destination else "غير محدد"} — حتى {m.to_date}'
    return 'إذن اليوم'

def assistant_render_read(a):
    intent=a.get('intent')
    if intent=='movement_people_today':
        mt=a.get('movement_type') or 'إجازة'
        gid=a.get('governorate_id')
        bid=a.get('branch_id')
        gov=db.session.get(Governorate,gid) if gid else None
        branch=db.session.get(Branch,bid) if bid else None
        allowed_gids=set(gids())
        if gov and (not gov.is_active or (allowed_gids and gov.id not in allowed_gids)):
            return {'title':'نتيجة البحث','error':'المحافظة غير متاحة ضمن نطاق صلاحياتك.'}
        if branch and (not branch.is_active or not branch_ok(branch.id)):
            return {'title':'نتيجة البحث','error':'الفرع غير متاح ضمن نطاق صلاحياتك.'}
        if not gov and not branch:
            return {'title':'نتيجة البحث','error':'لم أجد محافظة أو فرعًا مطابقًا.'}

        today=date.today()
        if branch:
            target_branch_ids={branch.id}
            location_label=f'فرع {branch.name}'
        elif gov:
            bs=Branch.query.filter_by(governorate_id=gov.id,is_active=True).order_by(Branch.name).all()
            bs=[b for b in bs if branch_ok(b.id)]
            target_branch_ids={b.id for b in bs}
            location_label=f'محافظة {gov.name}'
        else:
            # بحث عام داخل كل الفروع المتاحة للمستخدم.
            target_branch_ids={b.id for b in Branch.query.filter_by(is_active=True).all() if branch_ok(b.id)}
            location_label='النطاق المتاح لك'

        rows=[]
        if mt=='إجازة':
            if target_branch_ids:
                moves=(Movement.query.join(Employee,Movement.employee_id==Employee.id)
                       .filter(Employee.is_active==True,Employee.branch_id.in_(target_branch_ids),
                               Movement.is_active==True,Movement.movement_type=='إجازة',
                               Movement.from_date<=today,Movement.to_date>=today)
                       .order_by(Employee.full_name,Movement.id.desc()).all())
                seen=set()
                for m in moves:
                    if m.employee_id in seen: continue
                    seen.add(m.employee_id); rows.append((m.employee,m,None))
        elif mt=='إذن':
            if target_branch_ids:
                moves=(Movement.query.join(Employee,Movement.employee_id==Employee.id)
                       .filter(Employee.is_active==True,Employee.branch_id.in_(target_branch_ids),
                               Movement.is_active==True,Movement.movement_type=='إذن',
                               Movement.permission_date==today)
                       .order_by(Employee.full_name,Movement.id.desc()).all())
                seen=set()
                for m in moves:
                    if m.employee_id in seen: continue
                    seen.add(m.employee_id); rows.append((m.employee,None,None))
        else:  # انتداب: «في المكان» تعني أن الوجهة الحالية داخل المكان.
            if target_branch_ids:
                moves=(Movement.query.join(Employee,Movement.employee_id==Employee.id)
                       .filter(Employee.is_active==True,Movement.is_active==True,
                               Movement.movement_type=='انتداب',Movement.assignment_state!='مغلق',
                               Movement.from_date<=today,
                               ((Movement.to_date==None)|(Movement.to_date>=today)),
                               Movement.destination_branch_id.in_(target_branch_ids))
                       .order_by(Employee.full_name,Movement.id.desc()).all())
                seen=set()
                for m in moves:
                    if m.employee_id in seen: continue
                    seen.add(m.employee_id); rows.append((m,m.employee.branch,m.destination))

        if not rows:
            labels={'إجازة':'في إجازة','انتداب':'منتدبين','إذن':'عندهم إذن'}
            return {'title':f'{labels[mt]} اليوم — {location_label}',
                    'answer':f'لا يوجد موظفون {labels[mt]} اليوم في {location_label}.'}

        lines=[]
        for i,(m,origin,dest) in enumerate(rows,1):
            e=m.employee
            if mt=='إجازة':
                detail=f'{m.leave_type or "إجازة"} — حتى {m.to_date}'
            elif mt=='إذن':
                detail=f'إذن اليوم — {m.permission_date}'
            else:
                direction=f'{origin.name if origin else "غير محدد"} → {dest.name if dest else "غير محدد"}'
                detail=f'{direction} — ' + ('مفتوح' if m.to_date is None else f'حتى {m.to_date}')
            branch_name=e.branch.name if e.branch else 'غير محدد'
            lines.append(f'{i}. {e.full_name} — {detail} — فرع التعيين: {branch_name}')
        labels={'إجازة':'الموظفون في إجازة','انتداب':'الموظفون المنتدبون','إذن':'الموظفون لديهم إذن'}
        return {'title':f'{labels[mt]} اليوم — {location_label}',
                'answer':f'{labels[mt]} اليوم في {location_label}: {len(rows)}\n\n'+'\n'.join(lines)}

    if intent=='governorate_assignments_today':
        gid=a.get('governorate_id')
        gov=db.session.get(Governorate,gid) if gid else None
        allowed_gids=set(gids())
        if not gov or not gov.is_active or (allowed_gids and gov.id not in allowed_gids):
            return {'title':'انتدابات اليوم','error':'لا توجد محافظة مطابقة أو ليست ضمن نطاق صلاحياتك.'}
        branches=Branch.query.filter_by(governorate_id=gov.id,is_active=True).order_by(Branch.name).all()
        branches=[b for b in branches if branch_ok(b.id)]
        branch_ids={b.id for b in branches}
        rows=[]
        # الانتداب الحالي إلى فرع داخل المحافظة.
        for e in Employee.query.filter(Employee.is_active==True).order_by(Employee.full_name).all():
            m=current_assignment_for_employee(e.id, date.today())
            if not m or not m.destination_branch_id or m.destination_branch_id not in branch_ids:
                continue
            dest=db.session.get(Branch,m.destination_branch_id)
            origin=e.branch
            rows.append((e,m,origin,dest))
        if not rows:
            return {'title':f'منتدبو اليوم في محافظة {gov.name}','answer':f'لا يوجد موظفون منتدبون حاليًا إلى فروع محافظة {gov.name} اليوم.'}
        lines=[]
        for i,(e,m,origin,dest) in enumerate(rows,1):
            period='مفتوح' if m.to_date is None else f'حتى {m.to_date}'
            direction=f'{origin.name if origin else "غير محدد"} → {dest.name if dest else "غير محدد"}'
            lines.append(f'{i}. {e.full_name} — {direction} — من {m.from_date or "غير محدد"} — {period}')
        return {'title':f'منتدبو اليوم في محافظة {gov.name}','answer':f'عدد المنتدبين إلى فروع المحافظة اليوم: {len(rows)}\n\n'+'\n'.join(lines)}
    if intent=='governorate_employees':
        gid=a.get('governorate_id')
        gov=db.session.get(Governorate,gid) if gid else None
        allowed_gids=set(gids())
        if not gov or not gov.is_active or (allowed_gids and gov.id not in allowed_gids):
            return {'title':'موظفو المحافظة','error':'لا توجد محافظة مطابقة أو ليست ضمن نطاق صلاحياتك.'}
        branches=Branch.query.filter_by(governorate_id=gov.id,is_active=True).order_by(Branch.name).all()
        branches=[b for b in branches if branch_ok(b.id)]
        employees=Employee.query.filter(Employee.is_active==True, Employee.branch_id.in_([b.id for b in branches])).order_by(Employee.full_name).all() if branches else []
        if not employees:
            return {'title':f'أسماء الموظفين في {gov.name}','answer':f'لا يوجد موظفون نشطون مسجلون حاليًا في محافظة {gov.name}.'}
        lines=[f'{i}. {e.full_name} — {e.branch.name if e.branch else "غير محدد"}' for i,e in enumerate(employees,1)]
        return {'title':f'أسماء الموظفين في {gov.name}','answer':f'عدد الموظفين النشطين: {len(employees)}\n\n'+'\n'.join(lines)}
    if intent=='employee_status':
        e=db.session.get(Employee,a.get('employee_id')) if a.get('employee_id') else None
        if not e or not e.is_active or not branch_ok(e.branch_id):
            return {'title':'نتيجة البحث','error':'لم أجد موظفًا واحدًا مطابقًا.','choices':[db.session.get(Employee,i) for i in a.get('candidate_ids',[]) if db.session.get(Employee,i)]}
        cur=current_assignment_for_employee(e.id); display_branch=cur.destination if cur and cur.destination else e.branch; state=assistant_status_for_employee(e); return {'title':'حالة الموظف','answer':f'الموظف: {e.full_name}\nالفرع الحالي: {display_branch.name if display_branch else "—"}\nفرع التعيين: {e.branch.name if e.branch else "—"}\nالمحافظة: {display_branch.governorate.name if display_branch and display_branch.governorate else "—"}\nالحالة الآن: {state}'}
    if intent in ('branch_status','branch_info'):
        b=db.session.get(Branch,a.get('branch_id')) if a.get('branch_id') else None
        if not b or not branch_ok(b.id):
            return {'title':'نتيجة البحث','error':'لم أجد فرعًا واحدًا مطابقًا.','choices':[db.session.get(Branch,i) for i in a.get('candidate_ids',[]) if db.session.get(Branch,i)]}
        employees=employees_effectively_in_branches([b.id])
        entry_links=EntryAssignmentBranch.query.join(EntryAssignment).filter(EntryAssignmentBranch.branch_id==b.id,EntryAssignment.is_active==True).all()
        entry_names=[]
        supervisors=[]
        for link in entry_links:
            if link.assignment and link.assignment.employee and link.assignment.employee.is_active:
                entry_names.append(link.assignment.employee.full_name)
            if link.assignment and link.assignment.supervisor and link.assignment.supervisor.is_active:
                supervisors.append(link.assignment.supervisor.full_name)

        # الموظفون المنتدبون فعليًا إلى هذا الفرع: فرع التعيين مختلف،
        # والانتداب الحالي يجعل الفرع الحالي هو هذا الفرع.
        inbound=[]
        for e in employees:
            cur=current_assignment_for_employee(e.id)
            if cur and cur.destination_branch_id==b.id and e.branch_id!=b.id:
                inbound.append((e,cur))

        on_duty=sum(1 for e in employees if assistant_status_for_employee(e)=='على رأس العمل')
        leave_count=sum(1 for e in employees if 'إجازة' in assistant_status_for_employee(e))
        assignment_count=sum(1 for e in employees if 'انتداب' in assistant_status_for_employee(e))
        permission_count=sum(1 for e in employees if assistant_status_for_employee(e)=='إذن اليوم')

        def esc(v):
            from markupsafe import escape
            return str(escape(v if v is not None else ''))
        cards=[
            f'<div class="branch-data-card"><b>اسم الفرع</b><strong>{esc(b.name)}</strong></div>',
            f'<div class="branch-data-card"><b>كود الفرع</b><strong>{esc(b.code or "غير محدد")}</strong></div>',
            f'<div class="branch-data-card"><b>المحافظة</b><strong>{esc(b.governorate.name)}</strong></div>',
            f'<div class="branch-data-card"><b>الموظفون حاليًا</b><strong>{len(employees)}</strong></div>',
            f'<div class="branch-data-card"><b>على رأس العمل</b><strong>{on_duty}</strong></div>',
            f'<div class="branch-data-card"><b>إجازة</b><strong>{leave_count}</strong></div>',
            f'<div class="branch-data-card"><b>انتداب</b><strong>{assignment_count}</strong></div>',
            f'<div class="branch-data-card"><b>إذن اليوم</b><strong>{permission_count}</strong></div>'
        ]
        management=(
            f'<div class="branch-management-row">'
            f'<div class="branch-management-item"><span>المدخل الأول المسؤول</span><b>{esc(", ".join(dict.fromkeys(entry_names)) if entry_names else "غير محدد")}</b></div>'
            f'<div class="branch-management-item"><span>المشرف</span><b>{esc(", ".join(dict.fromkeys(supervisors)) if supervisors else "غير محدد")}</b></div>'
            f'</div>'
        )

        current_cards=[]
        for e in employees:
            cur=current_assignment_for_employee(e.id)
            status=assistant_status_for_employee(e)
            current_cards.append(
                f'<div class="branch-employee-card">'
                f'<div class="branch-employee-name">{esc(e.full_name)}</div>'
                f'<div class="branch-employee-meta"><span>{esc(status)}</span><span>فرع التعيين: {esc(e.branch.name if e.branch else "غير محدد")}</span></div>'
                f'</div>'
            )
        employees_html=''.join(current_cards) if current_cards else '<div class="branch-empty">لا يوجد موظفون حاليًا في هذا الفرع.</div>'

        inbound_cards=[]
        for e,m in inbound:
            period=('مفتوح' if m.to_date is None else f'حتى {m.to_date}')
            inbound_cards.append(
                f'<div class="branch-inbound-card">'
                f'<div class="branch-employee-name">{esc(e.full_name)}</div>'
                f'<div class="branch-inbound-meta"><span>انتداب إلى {esc(b.name)}</span><span>من {esc(m.from_date or "غير محدد")}</span><span>{esc(period)}</span></div>'
                f'<div class="branch-inbound-origin">فرع التعيين: {esc(e.branch.name if e.branch else "غير محدد")}</div>'
                f'</div>'
            )
        inbound_html=''.join(inbound_cards) if inbound_cards else '<div class="branch-empty">لا يوجد موظفون منتدبون حاليًا إلى هذا الفرع.</div>'

        answer=(
            '<div class="branch-data-layout">'
            '<div class="branch-data-section"><div class="branch-section-title">بيانات الفرع</div><div class="branch-data-grid">'+''.join(cards)+'</div></div>'
            '<div class="branch-data-section">'+management+'</div>'
            '<div class="branch-data-section"><div class="branch-section-title">الموظفون الموجودون في الفرع الآن</div><div class="branch-employee-grid">'+employees_html+'</div></div>'
            '<div class="branch-data-section branch-inbound-section"><div class="branch-section-title">المنتدبون إلى الفرع الآن</div><div class="branch-employee-grid">'+inbound_html+'</div></div>'
            '</div>'
        )
        return {'title':f'بيانات فرع {b.name}','answer':answer}
    if intent=='employee_info':
        e=db.session.get(Employee,a.get('employee_id')) if a.get('employee_id') else None
        if not e or not e.is_active or not branch_ok(e.branch_id):
            return {'title':'نتيجة البحث','error':'لم أجد موظفًا واحدًا مطابقًا.','choices':[db.session.get(Employee,i) for i in a.get('candidate_ids',[]) if db.session.get(Employee,i)]}
        cur=current_assignment_for_employee(e.id); cb=cur.destination if cur and cur.destination else e.branch
        ms=Movement.query.filter_by(employee_id=e.id,is_active=True).order_by(Movement.id.desc()).all()
        def latest(kind): return next((m for m in ms if m.movement_type==kind),None)
        leave=latest('إجازة'); assignment=latest('انتداب'); permission=latest('إذن')
        field=a.get('employee_field') or 'basic'
        def movement_text(m):
            if not m: return 'لا توجد بيانات'
            if m.movement_type=='إذن': return str(m.permission_date or 'لا توجد بيانات')
            detail=m.leave_type or (m.destination.name if m.destination else '') or ''
            if m.movement_type=='إجازة': return f'{detail} — من {m.from_date or "—"} إلى {m.to_date or "—"}'
            return f'{detail} — من {m.from_date or "—"} إلى {m.to_date or "مفتوح"}'
        if field=='job_title': return {'title':f'وظيفة {e.full_name}','answer':f'{e.full_name} — الوظيفة: {e.job_title or "لا توجد بيانات"}'}
        if field=='job_code': return {'title':f'الكود الوظيفي — {e.full_name}','answer':f'{e.full_name} — الكود الوظيفي: {e.job_code or "لا توجد بيانات"}'}
        if field=='employee_code': return {'title':f'كود الموظف — {e.full_name}','answer':f'{e.full_name} — كود الموظف: {e.job_code or "لا توجد بيانات"}'}
        if field=='branch': return {'title':f'فرع {e.full_name}','answer':f'{e.full_name} — فرع التعيين: {e.branch.name if e.branch else "لا توجد بيانات"} — الفرع الحالي: {cb.name if cb else "لا توجد بيانات"}'}
        if field=='governorate': return {'title':f'محافظة {e.full_name}','answer':f'{e.full_name} — المحافظة الحالية: {cb.governorate.name if cb and cb.governorate else "لا توجد بيانات"}'}
        if field=='hire_date': return {'title':f'تاريخ تعيين {e.full_name}','answer':f'{e.full_name} — تاريخ التعيين: {e.hire_date or "لا توجد بيانات"}'}
        if field=='phone': return {'title':f'رقم الهاتف — {e.full_name}','answer':f'{e.full_name} — هاتف الشركة: {e.company_phone or "لا توجد بيانات"} — الهاتف الشخصي: {e.personal_phone or "لا توجد بيانات"}'}
        if field=='company_phone': return {'title':f'هاتف العمل — {e.full_name}','answer':f'{e.full_name} — هاتف الشركة: {e.company_phone or "لا توجد بيانات"}'}
        if field=='personal_phone': return {'title':f'الهاتف الشخصي — {e.full_name}','answer':f'{e.full_name} — الهاتف الشخصي: {e.personal_phone or "لا توجد بيانات"}'}
        if field=='last_leave': return {'title':f'آخر إجازة — {e.full_name}','answer':f'{e.full_name} — آخر إجازة: {movement_text(leave)}'}
        if field=='last_assignment': return {'title':f'آخر انتداب — {e.full_name}','answer':f'{e.full_name} — آخر انتداب: {movement_text(assignment)}'}
        if field=='last_permission': return {'title':f'آخر إذن — {e.full_name}','answer':f'{e.full_name} — آخر إذن: {movement_text(permission)}'}
        if field=='movements':
            return {'title':f'حركات {e.full_name}','answer':'\n'.join([f'{m.movement_type} — {movement_text(m)} — {m.status}' for m in ms[:20]]) if ms else f'{e.full_name}: لا توجد حركات مسجلة.'}
        lines=[f'الموظف: {e.full_name}',f'الحالة الآن: {assistant_status_for_employee(e)}',f'كود الموظف: {e.job_code or "لا توجد بيانات"}',f'الوظيفة: {e.job_title or "لا توجد بيانات"}',f'المحافظة: {cb.governorate.name if cb and cb.governorate else "لا توجد بيانات"}',f'فرع التعيين: {e.branch.name if e.branch else "لا توجد بيانات"}',f'الفرع الحالي: {cb.name if cb else "لا توجد بيانات"}',f'تاريخ التعيين: {e.hire_date or "لا توجد بيانات"}',f'آخر إجازة: {movement_text(leave)}',f'آخر انتداب: {movement_text(assignment)}',f'آخر إذن: {movement_text(permission)}']
        return {'title':f'بطاقة الموظف — {e.full_name}','answer':'\n'.join(lines),'actions':[
            {'label':'الوظيفة','url':'#','prompt':f'ما وظيفة {e.full_name}؟'},
            {'label':'آخر إجازة','url':'#','prompt':f'ما آخر إجازة لـ {e.full_name}؟'},
            {'label':'آخر انتداب','url':'#','prompt':f'ما آخر انتداب لـ {e.full_name}؟'},
            {'label':'آخر إذن','url':'#','prompt':f'ما آخر إذن لـ {e.full_name}؟'},
            {'label':'سجل الحركات','url':'#','prompt':f'اعرض سجل حركات {e.full_name}'}
        ]}
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
    # لا تعرض أمثلة محفوظة عند تعذر التصنيف؛ اترك المساعد يطلب التوضيح بصورة طبيعية.
    return {'title':'المساعد الذكي','answer':'ما زلت أحتاج إلى تحديد المقصود من طلبك.'}

@app.route('/assistant', methods=['GET','POST'])
@req
def assistant():
    result=None; prompt=''
    chat=session.get('assistant_chat', [])
    if request.method=='POST':
        prompt=(request.form.get('prompt') or '').strip()
        prior_chat=list(chat)
        if prompt:
            chat.append({'role':'user','text':prompt})
        if not prompt:
            result={'title':'المساعد الذكي','error':'اكتب طلبك أولًا.'}
        else:
            # ابدأ ببيانات التطبيق الحية أولاً. هذا يجعل الاستفسارات الشائعة فورية ولا تنتظر نموذجًا خارجيًا.
            local_a=assistant_parse(prompt)
            live_ctx=assistant_live_context_for_prompt(prompt, local_a)
            needs_semantic = local_a.get('intent') in ('help','topic_options','employee_topic')
            llm_a=assistant_llm_parse(prompt, prior_chat, live_ctx) if needs_semantic else None
            # استخدم الفهم الدلالي فقط عندما تكون الصياغة غير محددة محليًا؛ أما طلبات البيانات المباشرة
            # فتعتمد على قاعدة البيانات الحالية حتى لا تتأخر بسبب الشبكة.
            if llm_a:
                a=llm_a
                # إذا أعاد النموذج تصنيفاً عاماً جداً (help) بينما يستطيع التطبيق
                # التعرف على النص مباشرة من بياناته، نستخدم التعرف المحلي الدقيق بدلاً
                # من مطالبة المستخدم بإعادة صياغة كلامه. هذا ليس قاموس كلمات؛ بل بحث فعلي
                # في كيانات قاعدة البيانات.
                if (a.get('intent') in ('help','topic_options','employee_topic') and local_a.get('intent') in ('employee_info','employee_status','employee_movements')):
                    a=local_a
                elif a.get('intent')=='help' and local_a.get('intent') not in ('help',):
                    a=local_a
                # حل أسماء/كيانات المستخدم على الخادم بعد الفهم الدلالي، دون فرض كلمات محددة.
                if not a.get('employee_id') and a.get('employee_name'):
                    ee,mm=assistant_find_employee(a.get('employee_name'))
                    if ee: a['employee_id']=ee.id
                    elif mm: a['candidate_ids']=[e.id for e in mm[:10]]
                if not a.get('branch_id') and a.get('branch_name'):
                    bb,mm=assistant_find_branch(a.get('branch_name'))
                    if bb: a['branch_id']=bb.id
                    elif mm: a['candidate_ids']=[b.id for b in mm[:10]]
                if not a.get('governorate_id') and a.get('governorate_name'):
                    gg=[g for g in Governorate.query.filter_by(is_active=True).all() if a.get('governorate_name','').strip().lower() in (g.name or '').lower()]
                    if len(gg)==1: a['governorate_id']=gg[0].id
            else:
                a=local_a
            field=assistant_employee_field(prompt)
            if field:
                a['employee_field']=field
            if not a.get('employee_id') and session.get('assistant_context_employee_id') and field:
                ce=db.session.get(Employee,session.get('assistant_context_employee_id'))
                if ce and ce.is_active and branch_ok(ce.branch_id):
                    a['employee_id']=ce.id
                    if a.get('intent') in ('help','topic_options','employee_topic'):
                        a['intent']='employee_status' if field=='status' else ('employee_movements' if field=='movements' else 'employee_info')
            # سياق الموظف الأخير: إذا ذكر المستخدم إجراءً جديدًا مباشرة بعد عرض موظف،
            # نستخدم الموظف الأخير تلقائيًا ما لم يحدد موظفًا آخر.
            if not a.get('employee_id') and session.get('assistant_context_employee_id'):
                if a.get('intent')=='register_movement' or a.get('topic') in ('leave','assignment','permission'):
                    ce=db.session.get(Employee, session.get('assistant_context_employee_id'))
                    if ce and ce.is_active and branch_ok(ce.branch_id):
                        a['employee_id']=ce.id
            if a.get('intent')=='greeting':
                result={'title':'المساعد الذكي','answer':a.get('reply') or assistant_greeting_reply(prompt)}
            elif a.get('intent')=='topic_options':
                result=assistant_topic_options(a.get('topic'))
                # لا تستخدم رسالة خيارات عامة إذا أعاد النموذج ردًا طبيعيًا أكثر تحديدًا.
                if a.get('reply') and not result.get('answer'):
                    result['answer']=a.get('reply')
            elif a.get('intent')=='employee_topic':
                # موضوع عام مثل اسم موظف/الموظفين: اعرض ما فهمه النظام فقط، دون أمثلة ثابتة.
                result=assistant_topic_options('employee')
            elif a.get('intent')=='employee_add':
                if not can('manage_employees'):
                    result={'title':'إضافة موظف جديد','error':'لا تملك صلاحية إضافة موظف جديد.'}
                else:
                    result={'title':'إضافة موظف جديد','answer':'بالتأكيد. يمكنك إضافة موظف جديد. سأفتح لك شاشة الإضافة مباشرة لتسجيل البيانات المطلوبة: المحافظة، الفرع، الاسم، البريد الإلكتروني، الوظيفة، الكود الوظيفي، تاريخ التعيين، هاتف الشركة والهاتف الشخصي.','actions':[{'label':'بدء إضافة موظف جديد','url':'/employees'}]}
            elif a.get('intent')=='navigate':
                nav=a.get('navigate_url') or ''
                topic_map={'reports':'/reports/leaves','admin':'/structure','users':'/users','delegation':'/delegations','replacement':'/replacement','audit':'/audit'}
                if not nav: nav=topic_map.get(a.get('topic'),'')
                allowed={'/employees':'manage_employees','/employees/edit-data':'manage_employees','/employees/resigned':'manage_employees','/structure':'manage_structure','/governorates':'manage_structure','/branches':'manage_structure','/replacement':'manage_structure','/users':'manage_users','/delegations':'manage_users','/review':'review_movements','/movements':'manage_movements','/audit':'view_audit','/lookups':'view_audit','/reports/leaves':'view_reports','/reports/assignments':'view_reports','/reports/permissions':'view_reports','/reports/assignments/print-missions':'view_reports'}
                if nav not in allowed:
                    result={'title':'المساعد الذكي','answer':a.get('reply') or 'وضح لي الوظيفة أو التقرير الذي تريده.'}
                elif not can(allowed[nav]):
                    result={'title':'الصلاحيات','error':'هذا الإجراء غير متاح ضمن صلاحيات دورك الحالي.'}
                else:
                    result={'title':'المساعد الذكي','answer':a.get('reply') or 'سأفتح لك الوظيفة المطلوبة.','actions':[{'label':'فتح','url':nav}]}
            elif a.get('intent')=='help':
                # help هنا يعني أن النموذج لم يجد عملية آمنة محددة؛ استخدم رده الطبيعي إن وُجد،
                # ولا تعُد إلى قائمة أمثلة محفوظة.
                result={'title':'المساعد الذكي','answer':a.get('reply') or 'ما الذي تريد معرفته أو تنفيذه بخصوص البيانات الظاهرة أمامنا؟'}
            elif a.get('intent')=='register_movement':
                if not can('manage_movements'):
                    result={'title':'تسجيل حركة','error':'لا تملك صلاحية تسجيل الحركات.'}
                elif not a.get('employee_id'):
                    result={'title':'تحديد الموظف','error':'لم أستطع تحديد موظف واحد. اكتب الاسم بشكل أوضح.','choices':[db.session.get(Employee,i) for i in a.get('candidate_ids',[]) if db.session.get(Employee,i)]}
                else:
                    e=db.session.get(Employee,a['employee_id']); dest=db.session.get(Branch,a.get('destination_branch_id')) if a.get('destination_branch_id') else None
                    mt=a.get('movement_type')
                    if mt=='إجازة' and not a.get('leave_type'):
                        result={'title':'نوع الإجازة','answer':'ما نوع الإجازة التي تريد تسجيلها؟'}
                    elif mt in ('إجازة','انتداب') and not a.get('from_date'):
                        result={'title':'تاريخ البداية','answer':'ما تاريخ بداية الحركة؟'}
                    elif mt=='انتداب' and not a.get('open_assignment') and not a.get('to_date'):
                        result={'title':'تاريخ نهاية الانتداب','answer':'هل الانتداب مفتوح بدون تاريخ نهاية، أم له تاريخ نهاية؟'}
                    elif mt=='إجازة' and not a.get('to_date'):
                        result={'title':'تاريخ النهاية','answer':'ما تاريخ نهاية الإجازة؟'}
                    elif mt=='إذن' and not a.get('permission_date'):
                        result={'title':'تاريخ الإذن','answer':'ما تاريخ الإذن؟'}
                    elif mt=='انتداب' and not a.get('destination_name') and not a.get('destination_branch_id'):
                        result={'title':'فرع الانتداب','answer':'إلى أي فرع سيكون الانتداب؟'}
                    elif mt=='انتداب' and a.get('destination_name') and not a.get('destination_branch_id'):
                        dest,matches_dest=assistant_find_branch(a.get('destination_name'))
                        if not dest:
                            result={'title':'تحديد فرع الانتداب','error':'لم أجد فرعًا مطابقًا.','choices':matches_dest[:10]}
                        else:
                            a['destination_branch_id']=dest.id
                    if result is None:
                        dest=db.session.get(Branch,a.get('destination_branch_id')) if a.get('destination_branch_id') else dest
                        err=validate_movement_fields(a.get('movement_type'),a.get('leave_type'),dest.id if dest else None,a.get('from_date'),None if a.get('open_assignment') else a.get('to_date'),a.get('permission_date'))
                        if err: result={'title':'مراجعة الحركة','error':err}
                        elif not e or not branch_ok(e.branch_id): result={'title':'تسجيل حركة','error':'الموظف خارج نطاق صلاحياتك.'}
                        elif a.get('movement_type')=='انتداب' and (not dest or not branch_ok(dest.id)): result={'title':'تسجيل انتداب','error':'فرع الانتداب غير موجود أو خارج نطاق صلاحياتك.'}
                        elif movement_overlaps(e.id,a['movement_type'],a.get('from_date'),None if a.get('open_assignment') else a.get('to_date'),a.get('permission_date')): result={'title':'تعارض في الحركة','error':movement_overlaps(e.id,a['movement_type'],a.get('from_date'),None if a.get('open_assignment') else a.get('to_date'),a.get('permission_date'))}
                        else:
                            session['assistant_pending']=a
                            dest_text=f' إلى {dest.governorate.name} — {dest.name}' if dest else ''
                            period=(f" من {a.get('from_date')} — انتداب مفتوح" if a.get('movement_type')=='انتداب' and not a.get('to_date') and a.get('from_date') else (f" من {a.get('from_date')} إلى {a.get('to_date')}" if a.get('from_date') else (f" بتاريخ {a.get('permission_date')}" if a.get('permission_date') else '')))
                            result={'title':'تأكيد تسجيل الحركة','preview':f"{a['movement_type']} للموظف {e.full_name}{dest_text}{period}"}
            else:
                if a.get('intent')=='branch_entry':
                    result=assistant_render_branch_entry(a)
                else:
                    result=assistant_render_read(a)
                if a.get('employee_id') and db.session.get(Employee,a.get('employee_id')):
                    session['assistant_context_employee_id']=a.get('employee_id')
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
            {'label':'الموظفون المستقيلون','prompt':'اعرض الموظفين المستقيلين','icon':'♻️','kind':'query','url':'/employees/resigned'},
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
    err=validate_movement_fields(a.get('movement_type'),a.get('leave_type'),dest.id if dest else None,a.get('from_date'),None if a.get('open_assignment') else a.get('to_date'),a.get('permission_date'))
    if err: flash(err); return redirect(back)
    if a.get('movement_type')=='انتداب' and (not dest or not branch_ok(dest.id)): flash('فرع الانتداب غير مسموح.'); return redirect(back)
    overlap=movement_overlaps(e.id,a['movement_type'],a.get('from_date'),None if a.get('open_assignment') else a.get('to_date'),a.get('permission_date'))
    if overlap: flash(overlap); return redirect(back)
    m=Movement(employee_id=e.id,movement_type=a['movement_type'],leave_type=a.get('leave_type'),destination_branch_id=dest.id if dest else None,from_date=parse_date(a.get('from_date')),to_date=parse_date(a.get('to_date')),permission_date=parse_date(a.get('permission_date')),notes=None,created_by=me().id,status='مدخلة',assignment_state='ساري',approver_id=None)
    db.session.add(m); db.session.flush(); record_movement_history(m,None,'مدخلة','AI_ASSISTANT_ADD','تسجيل الحركة من المساعد الذكي — لا تحتاج لاعتماد'); log('AI_ASSISTANT_ADD','Movement',m.id,f'{m.movement_type} — {e.full_name}'); db.session.commit(); flash('تم تسجيل الحركة بنجاح من خلال المساعد الذكي.'); return redirect(back)

@app.get('/api/movement-employees')
@req
def movement_employees_api():
    """Return movement employee suggestions after governorate selection.

    The governorate is mandatory for the lookup. A branch filters the list;
    otherwise q searches by employee name or job code. Results are deliberately
    small so the autocomplete stays fast and does not trigger the old server
    error caused by loading a large employee list at once.
    """
    gid=request.args.get('governorate_id','').strip()
    bid=request.args.get('branch_id','').strip()
    q=request.args.get('q','').strip()
    if not gid.isdigit():
        return {'results': [], 'branches': []}
    gid=int(gid)
    # بحث بطاقة الموظف من الصفحة الرئيسية: اختيار المحافظة متاح لكل المستخدمين.
    # لا نحصر قائمة المحافظات/الفروع هنا في محافظة المشرف؛ هذا البحث العام مستقل
    # عن نطاق الإدارة المختار في بقية الصفحة.
    if not db.session.get(Governorate, gid) or not db.session.get(Governorate, gid).is_active:
        return {'results': [], 'branches': []}
    branch_rows=(Branch.query.filter(Branch.governorate_id==gid, Branch.is_active==True)
                 .order_by(Branch.name.asc()).all())
    branch_ids=[b.id for b in branch_rows]
    if bid.isdigit():
        bid_int=int(bid)
        if bid_int not in branch_ids:
            return {'results': [], 'branches': [{'id':b.id,'name':b.name} for b in branch_rows]}
        branch_ids=[bid_int]
    if q and len(q)<1:
        q=''
    if not q and not bid.isdigit():
        return {'results': [], 'branches': [{'id':b.id,'name':b.name} for b in branch_rows]}

    filters=[Employee.is_active==True, Employee.branch_id.in_(branch_ids)]
    if q:
        like=f'%{q}%'
        filters.append(db.or_(Employee.full_name.ilike(like), Employee.job_code.ilike(like)))
    rows=(Employee.query.filter(*filters).order_by(Employee.full_name.asc()).limit(20).all())
    return {
        'results':[{'id':e.id,'name':e.full_name,'code':e.job_code or '',
                    'branch':e.branch.name if e.branch else ''} for e in rows],
        'branches':[{'id':b.id,'name':b.name} for b in branch_rows]
    }

@app.route('/movements',methods=['GET','POST'])
@req
def movements():
    bs=bids()
    if request.method=='POST' and (not can_manage_movement() or not can('manage_movements')): abort(403)
    emps=[]  # loaded on demand after governorate/branch selection
    allowed_gids=set(gids())
    govs=(Governorate.query.filter(Governorate.id.in_(allowed_gids),Governorate.is_active==True)
          .order_by(Governorate.name.asc()).all()) if allowed_gids else []
    scoped_branches=(Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True)
                     .order_by(Branch.name.asc()).all()) if bs else []
    if request.method=='POST':
        f=request.form; eid=int(f.get('employee_id','0')) if f.get('employee_id','').isdigit() else 0; e=db.session.get(Employee,eid)
        if not e or not branch_ok(e.branch_id): abort(403)
        mt=f.get('movement_type'); fd=f.get('from_date'); td=f.get('to_date'); pd=f.get('permission_date'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id','').isdigit() else None; status='مدخلة'; approver_id=None
        if mt=='انتداب' and f.get('open_assignment')=='1': td=None
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,fd,td,pd)
        if err: flash(err); return redirect('/movements')
        overlap=movement_overlaps(e.id,mt,fd,td,pd)
        if overlap: flash(overlap); return redirect('/movements')
        m=Movement(employee_id=e.id,movement_type=mt,leave_type=f.get('leave_type') or None,destination_branch_id=dest,from_date=parse_date(fd),to_date=parse_date(td),permission_date=parse_date(pd),notes=None,created_by=me().id,status=status,assignment_state=('ساري' if mt=='انتداب' else 'ساري'),approver_id=None); db.session.add(m); db.session.commit(); record_movement_history(m,None,status,'ADD','تسجيل الحركة — لا تحتاج لاعتماد'); log('ADD','Movement',m.id,status); db.session.commit(); flash('تم تسجيل الحركة وأصبحت ظاهرة مباشرة في متابعة الموظفين.')
    rows=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True).order_by(Movement.created_at.desc()).all() if bs else []
    selected_employee_id=request.args.get('employee_id', type=int)
    return render_template('movements.html',rows=rows,emps=emps,bs=scoped_branches,govs=govs,leave_types=active_leave_types(),movement_types=active_movement_types(),statuses=STATUSES,selected_employee_id=selected_employee_id,approvers={})
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
        fd=f.get('from_date'); td=f.get('to_date'); pd=f.get('permission_date')
        if mt=='انتداب' and f.get('open_assignment')=='1': td=None
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,fd,td,pd)
        if err: flash(err); return redirect(url_for('movement_edit',i=i))
        overlap=movement_overlaps(m.employee_id,mt,fd,td,pd,i)
        if overlap: flash(overlap); return redirect(url_for('movement_edit',i=i))
        old_status=m.status
        m.movement_type=mt; m.leave_type=f.get('leave_type') or None; m.destination_branch_id=dest; m.from_date=parse_date(fd); m.to_date=parse_date(td); m.permission_date=parse_date(pd); m.assignment_state=('ساري' if mt=='انتداب' else 'ساري'); m.approver_id=None; m.notes=None; m.modified_by=me().id; m.modified_at=datetime.utcnow(); m.status='مدخلة'; m.rejection_reason=None; record_movement_history(m,old_status,'مدخلة','EDIT','تعديل بيانات الحركة — لا تحتاج لاعتماد'); log('EDIT','Movement',i,'تعديل الحركة'); db.session.commit(); flash('تم تعديل الحركة وحفظها مباشرة.'); return redirect('/movements')
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

@app.post('/movements/<int:i>/close-assignment')
@req
def close_assignment(i):
    m=db.session.get(Movement,i)
    if not m or m.movement_type!='انتداب' or not m.is_active or not branch_ok(m.employee.branch_id): abort(403)
    if not can('manage_movements') or not can_manage_movement(m): abort(403)
    if m.assignment_state=='مغلق':
        flash('الانتداب مغلق بالفعل.')
        return redirect('/movements')
    close_date=parse_date(request.form.get('close_date') or '') or date.today()
    if m.from_date and close_date < m.from_date:
        flash('تاريخ الإغلاق لا يجوز أن يسبق بداية الانتداب.')
        return redirect('/movements')
    m.assignment_state='مغلق'; m.to_date=close_date; m.closed_by=me().id; m.closed_at=datetime.utcnow(); m.closure_reason=(request.form.get('reason') or 'إغلاق الانتداب وعودة الموظف لفرعه الأصلي').strip(); m.modified_by=me().id; m.modified_at=datetime.utcnow()
    record_movement_history(m,m.status,m.status,'CLOSE_ASSIGNMENT',m.closure_reason); log('CLOSE_ASSIGNMENT','Movement',m.id,m.closure_reason); db.session.commit()
    flash('تم إنهاء الانتداب، وعاد الموظف لفرعه الأصلي.')
    return redirect('/movements')


def mission_state_label(m):
    return getattr(m, 'mission_state', None) or ('مغلقة' if m.status == 'معتمدة' else 'تحت التحرير')

def mission_template_pdf(m, employee, branch, destination, creator=None):
    """Generate the mission PDF by using the supplied sample PDF itself as the immutable template.

    Only the variable data regions are redacted/reinserted.  The template's original geometry,
    borders, labels, title, colors and embedded font remain untouched.
    """
    template=os.path.join(app.root_path,'static','mission','mission_template.pdf')
    font=os.path.join(app.root_path,'static','mission','mission-original.ttf')
    doc=fitz.open(template)
    page=doc[0]

    # The sample is 595.32 x 841.92 pt. These rectangles are the actual variable cells
    # measured from the supplied PDF, not approximate HTML coordinates.
    variable_regions = [
        fitz.Rect(497.5, 74.0, 553.8, 88.8),   # mission number + state, one continuous string
        fitz.Rect(458.0, 89.5, 553.8, 106.2),  # current user / job (print metadata)
        fitz.Rect(31.0, 80.0, 115.0, 94.0),    # print date + time
        fitz.Rect(62.0, 94.0, 84.5, 109.5),    # page number
        fitz.Rect(346.6, 158.7, 482.9, 177.2),  # employee name cell
        fitz.Rect(156.8, 158.7, 274.4, 177.2),  # basic branch cell
        fitz.Rect(57.1, 158.7, 88.5, 177.2),    # employee code cell
        fitz.Rect(346.5, 188.8, 482.9, 207.2),  # mission destination cell
        fitz.Rect(299.9, 253.9, 360.2, 272.6),  # to-date cell
        fitz.Rect(428.8, 253.9, 483.1, 272.6),  # from-date cell
        fitz.Rect(100.0, 281.5, 180.0, 298.5),  # approval title
        fitz.Rect(100.0, 300.0, 180.0, 317.0),  # approval destination
    ]
    for rect in variable_regions:
        page.add_redact_annot(rect, fill=(1,1,1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # The sample embeds the exact font used by the original form.  It is extracted into
    # static/mission/mission-original.ttf during release creation so variable text uses the
    # same font family, metrics, weight and color as the source PDF.
    if not os.path.exists(font):
        # Keep a safe fallback for local development; the release always contains the exact font.
        font=os.path.join(app.root_path,'static','mission','NotoNaskhArabic-Regular.ttf')

    now=datetime.now()
    def put(rect, text, size=9.9603748, align='right', direction='rtl'):
        text='' if text is None else str(text)
        safe=(text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'))
        html=(f'<div style="font-family:missionorig;font-size:{size:.6f}pt;'
              f'line-height:1;white-space:nowrap;text-align:{align};direction:{direction};">{safe}</div>')
        css=f'@font-face{{font-family:missionorig;src:url({font})}}'
        page.insert_htmlbox(rect, html, css=css)

    # Upper-right: one single text run so the state can never split into two words/boxes.
    status='مغلقة' if mission_state_label(m)=='مغلقة' else 'تحت التحرير'
    put(fitz.Rect(498.0, 74.2, 552.8, 87.9), f'{m.id} {status}', 8.0403004, 'right', 'rtl')

    creator_name=(creator.full_name if creator else '')
    creator_job=(creator.job_title if creator and creator.job_title else '')
    if creator_name:
        put(fitz.Rect(462.5, 90.2, 552.8, 98.2), f'- {creator_name}', 6.0002327, 'right', 'rtl')
    if creator_job:
        put(fitz.Rect(462.5, 97.3, 552.8, 106.0), creator_job, 6.0002327, 'right', 'rtl')

    # Keep the source's exact size/color/positions for the small print metadata.
    put(fitz.Rect(32.0, 82.0, 77.8, 93.0), now.strftime('%Y/%m/%d'), 8.0403004, 'left', 'ltr')
    put(fitz.Rect(80.5, 82.0, 115.0, 93.0), now.strftime('%H:%M:%S'), 8.0403004, 'left', 'ltr')
    put(fitz.Rect(62.0, 96.5, 84.5, 107.5), r'1 \ 1', 8.0403004, 'center', 'ltr')

    # Employee information stays completely inside the original cells.
    employee_name=employee.full_name if employee else ''
    gov_name=branch.governorate.name if branch and branch.governorate else ''
    branch_name=branch.name if branch else ''
    destination_gov=destination.governorate.name if destination and destination.governorate else ''
    destination_name=destination.name if destination else ''

    put(fitz.Rect(347.0, 159.1, 482.7, 176.9), employee_name, 9.9603748, 'right', 'rtl')
    # Requested order: governorate first, then branch. The employee code remains in its own cell.
    basic_branch=f'{gov_name} - {branch_name}' if gov_name and branch_name else (gov_name or branch_name)
    put(fitz.Rect(157.0, 159.1, 274.2, 176.9), basic_branch, 9.9603748, 'right', 'rtl')
    put(fitz.Rect(57.2, 159.1, 88.4, 176.9), employee.job_code if employee and employee.job_code else '', 9.9603748, 'center', 'ltr')

    # Requested order for mission destination: governorate first, then branch.
    mission_dest=f'{destination_gov} - {destination_name}' if destination_gov and destination_name else (destination_gov or destination_name)
    put(fitz.Rect(346.8, 189.2, 482.7, 206.9), mission_dest, 9.9603748, 'right', 'rtl')

    # Dates occupy the exact original cells.  The PDF route refuses to print a mission
    # without an end date (see mission_pdf below).
    put(fitz.Rect(300.1, 254.6, 359.9, 271.9), m.to_date.strftime('%Y/%m/%d') if m.to_date else '', 9.9603748, 'center', 'ltr')
    put(fitz.Rect(429.1, 254.6, 482.8, 271.9), m.from_date.strftime('%Y/%m/%d') if m.from_date else '', 9.9603748, 'center', 'ltr')

    # Approval title is fixed text from the sample; only the destination data changes.
    put(fitz.Rect(116.8, 284.6, 172.2, 296.0), 'اعتماد مدير فرع', 9.9603748, 'center', 'rtl')
    put(fitz.Rect(107.9, 303.0, 170.1, 314.5), mission_dest, 9.9603748, 'center', 'rtl')

    out=io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    out.seek(0)
    return out.getvalue()

@app.get('/reports/assignments/mission-edit/<int:movement_id>')
@req
def mission_edit(movement_id):
    m=db.session.get(Movement,movement_id)
    if not m or not m.is_active or m.movement_type!='انتداب' or not branch_ok(m.employee.branch_id): abort(403)
    if not can('view_reports') or not can_manage_movement(m): abort(403)
    if mission_state_label(m)!='تحت التحرير':
        flash('المأمورية مغلقة. استخدم «إعادة الفتح» أولًا ثم عد للتعديل.')
        return redirect('/reports/assignments/print-missions')
    bs=bids(); branches=Branch.query.filter(Branch.is_active==True,Branch.id.in_(bs)).order_by(Branch.name.asc()).all() if bs else []
    return render_template('mission_edit.html',m=m,branches=branches)

@app.post('/reports/assignments/mission-edit/<int:movement_id>')
@req
def mission_edit_save(movement_id):
    m=db.session.get(Movement,movement_id)
    if not m or not m.is_active or m.movement_type!='انتداب' or not branch_ok(m.employee.branch_id): abort(403)
    if not can('manage_movements') or not can_manage_movement(m): abort(403)
    if mission_state_label(m)!='تحت التحرير':
        flash('لا يمكن تعديل المأمورية وهي مغلقة. أعد فتحها أولًا.')
        return redirect('/reports/assignments/print-missions')
    dest_id=request.form.get('destination_branch_id','').strip()
    destination=db.session.get(Branch,int(dest_id)) if dest_id.isdigit() else None
    fd=parse_date(request.form.get('from_date',''))
    td=parse_date(request.form.get('to_date',''))
    if not destination or destination.id not in set(b.id for b in Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all()):
        flash('اختر جهة مأمورية صحيحة ضمن نطاقك.'); return redirect(url_for('mission_edit',movement_id=movement_id))
    if not fd or not td or td < fd:
        flash('يجب إدخال تاريخ بداية ونهاية صحيحين.'); return redirect(url_for('mission_edit',movement_id=movement_id))
    overlap=movement_overlaps(m.employee_id,'انتداب',fd,td,None,m.id)
    if overlap:
        flash(overlap); return redirect(url_for('mission_edit',movement_id=movement_id))
    old=(m.destination_branch_id,m.from_date,m.to_date)
    m.destination_branch_id=destination.id; m.from_date=fd; m.to_date=td; m.modified_by=me().id; m.modified_at=datetime.utcnow()
    record_movement_history(m,m.status,m.status,'MISSION_EDIT',f'تعديل بيانات المأمورية: جهة={destination.name}، من={fd}، إلى={td}')
    log('MISSION_EDIT','Movement',m.id,f'{old} -> {(destination.id,fd,td)}')
    db.session.commit(); flash('تم تعديل المأمورية وهي ما زالت تحت التحرير.'); return redirect('/reports/assignments/print-missions')

@app.post('/reports/assignments/mission-close/<int:movement_id>')
@req
def mission_close(movement_id):
    m=db.session.get(Movement,movement_id)
    if not m or not m.is_active or m.movement_type!='انتداب' or not branch_ok(m.employee.branch_id): abort(403)
    if not can('manage_movements') or not can_manage_movement(m): abort(403)
    if mission_state_label(m)=='مغلقة':
        flash('المأمورية مغلقة بالفعل.'); return redirect('/reports/assignments/print-missions')
    if not m.to_date:
        flash('لا يمكن إغلاق المأمورية قبل تسجيل «إلى تاريخ».')
        return redirect(url_for('mission_edit', movement_id=m.id))
    m.mission_state='مغلقة'; m.modified_by=me().id; m.modified_at=datetime.utcnow()
    record_movement_history(m,m.status,m.status,'MISSION_CLOSE','إغلاق المأمورية بعد مراجعة بياناتها')
    log('MISSION_CLOSE','Movement',m.id,'إغلاق المأمورية')
    db.session.commit(); flash('تم إغلاق المأمورية.'); return redirect('/reports/assignments/print-missions')

@app.post('/reports/assignments/mission-reopen/<int:movement_id>')
@req
def mission_reopen(movement_id):
    m=db.session.get(Movement,movement_id)
    if not m or not m.is_active or m.movement_type!='انتداب' or not branch_ok(m.employee.branch_id): abort(403)
    if not can('manage_movements') or not can_manage_movement(m): abort(403)
    if mission_state_label(m)!='مغلقة':
        flash('المأمورية بالفعل تحت التحرير.'); return redirect('/reports/assignments/print-missions')
    m.mission_state='تحت التحرير'; m.modified_by=me().id; m.modified_at=datetime.utcnow()
    record_movement_history(m,m.status,m.status,'MISSION_REOPEN','إعادة فتح المأمورية للتعديل')
    log('MISSION_REOPEN','Movement',m.id,'إعادة فتح المأمورية')
    db.session.commit(); flash('تمت إعادة فتح المأمورية وعادت إلى «تحت التحرير».'); return redirect(url_for('mission_edit',movement_id=m.id))

@app.get('/reports/assignments/mission-pdf/<int:movement_id>')
@req
def mission_pdf(movement_id):
    m=db.session.get(Movement,movement_id)
    if not m or not m.is_active or m.movement_type!='انتداب' or not branch_ok(m.employee.branch_id): abort(403)
    if not can('view_reports') or not can_manage_movement(m): abort(403)
    if not m.to_date:
        if mission_state_label(m)=='تحت التحرير':
            flash('تاريخ «إلى» غير مسجل. أدخله أولًا قبل طباعة المأمورية.')
            return redirect(url_for('mission_edit', movement_id=m.id))
        flash('تاريخ «إلى» غير مسجل في مأمورية مغلقة. أعد فتحها أولًا ثم أدخل التاريخ قبل الطباعة.')
        return redirect('/reports/assignments/print-missions')
    employee=db.session.get(Employee,m.employee_id); branch=db.session.get(Branch,employee.branch_id) if employee else None; destination=m.destination; creator=db.session.get(User,m.created_by) if m.created_by else None
    data=mission_template_pdf(m,employee,branch,destination,creator)
    from flask import Response
    return Response(data,mimetype='application/pdf',headers={'Content-Disposition':f'inline; filename=mission-{m.id}.pdf'})

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
    # التفويض الإداري يتم حصراً بين مشرفي المحافظات: مشرف أصلي ← مشرف بديل.
    # مسؤول التطبيق يدير العملية تقنياً فقط ولا يكون طرفاً في التفويض.
    if 'مشرف محافظة' not in roles(sup) or 'مشرف محافظة' not in roles(delegate):
        flash('التفويض يكون بين مشرف محافظة ومشرف محافظة فقط.'); return redirect('/delegations')
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
    # الصفحة المرئية تعرض النموذج مع زر PDF المطابق للعينة الأصلية.
    m=db.session.get(Movement,movement_id)
    if not m: abort(404)
    if not can_manage_movement(m) or m.movement_type!='انتداب': abort(403)
    employee=db.session.get(Employee,m.employee_id); branch=db.session.get(Branch,employee.branch_id) if employee else None
    return render_template('mission_print.html',movement=m,employee=employee,branch=branch,destination=m.destination,mission_state=mission_state_label(m),printed_at=datetime.now())

@app.get('/reports-missions')
@req
def reports_missions():
    if not (can('view_reports') or can('manage_movements')): abort(403)
    return render_template('reports_missions.html')

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
      'last_assignment_notice_at':'TIMESTAMP',
      'mission_state':"VARCHAR(30) NOT NULL DEFAULT 'تحت التحرير'"
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
    if 'resignation_date' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN resignation_date DATE'))
    if 'rehire_date' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN rehire_date DATE'))
    if 'resignation_by' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN resignation_by INTEGER'))
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
    # المأموريات القديمة المعتمدة تعتبر مغلقة، بينما باقي المأموريات تبدأ تحت التحرير.
    db.session.execute(text("UPDATE movement SET mission_state='مغلقة' WHERE movement_type='انتداب' AND status='معتمدة' AND (mission_state IS NULL OR mission_state='تحت التحرير')"))
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
    # v35.64 — استعادة الدور الموازي «مشرف محافظة» لحساب مسؤول التطبيق.
    # هذا الدور منفصل عن واجهة مسؤول التطبيق ويمكن اختياره من «الدور الحالي».
    # إذا لم توجد له محافظات مسندة يدويًا، يعمل كنطاق مشرف موازي على جميع المحافظات،
    # حتى يستطيع الحساب استخدام وظائف المشرف دون تغيير كلمة المرور أو إنشاء حساب دخول آخر.
    restore_key='migration:admin-parallel-supervisor-role-v35.64'
    restore_done=Lookup.query.filter_by(kind='system_migration',name=restore_key).first()
    if not restore_done:
        if not UserRole.query.filter_by(user_id=u.id,role='مشرف محافظة').first():
            db.session.add(UserRole(user_id=u.id,role='مشرف محافظة'))
        db.session.flush()
        sync_role_accounts(u)
        db.session.add(Lookup(kind='system_migration',name=restore_key,is_active=True))
        db.session.commit()
    # Destructive legacy cleanup is intentionally never run at startup.

if __name__=='__main__': app.run(host='0.0.0.0',port=8000)
