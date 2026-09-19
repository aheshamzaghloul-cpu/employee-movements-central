import os, secrets
from datetime import datetime, date, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, has_request_context
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
APP_VERSION='v34.9.6-CLEAN-DATA'
DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///local.db')
if DATABASE_URL.startswith('postgres://'): DATABASE_URL=DATABASE_URL.replace('postgres://','postgresql+psycopg://',1)
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY') or 'dev-only-change-me',SQLALCHEMY_DATABASE_URI=DATABASE_URL,SQLALCHEMY_TRACK_MODIFICATIONS=False,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1',MAX_CONTENT_LENGTH=2*1024*1024)
db=SQLAlchemy(app)
ROLES=['مسؤول التطبيق','مشرف محافظة','المدخل الأول']
MOVEMENT_TYPES=['إجازة','انتداب','إذن']
LEAVE_TYPES=['سنوية','عارضة','مصيف','وضع']
STATUSES=['مدخلة','تحت المراجعة','معتمدة','مرفوضة']
ASSIGNMENT_ALERT_DAYS=1
ASSIGNMENT_STATES=['ساري','قرب الانتهاء','انتهت المدة']

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False); full_name=db.Column(db.String(200),nullable=False); job_title=db.Column(db.String(200)); job_code=db.Column(db.String(100)); password_hash=db.Column(db.Text,nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False); must_change_password=db.Column(db.Boolean,default=True,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); last_login=db.Column(db.DateTime)
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
 'مشرف محافظة':{'manage_users','manage_employees','review_movements','view_reports','cancel_approval'},
 'المدخل الأول':{'manage_employees','manage_movements','view_reports'}
}
class UserPermission(db.Model):
    __table_args__=(UniqueConstraint('user_id','permission',name='uq_user_permission'),)
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False); permission=db.Column(db.String(60),nullable=False)
class UserRole(db.Model):
    __table_args__=(UniqueConstraint('user_id','role',name='uq_user_role'),)
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='CASCADE'),nullable=False); role=db.Column(db.String(40),nullable=False)
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
    id=db.Column(db.Integer,primary_key=True); employee_code=db.Column(db.String(100),unique=True,nullable=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL'),unique=True,nullable=True); full_name=db.Column(db.String(250),nullable=False); branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT'),nullable=False); job_title=db.Column(db.String(200)); job_code=db.Column(db.String(100)); hire_date=db.Column(db.Date); company_phone=db.Column(db.String(80)); personal_phone=db.Column(db.String(80)); is_active=db.Column(db.Boolean,default=True,nullable=False); branch=db.relationship('Branch')
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
        if u.id in suids and 'مشرف محافظة' in roles(u) and can_for_user(u,'review_movements'):
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
    return {'me':u,'roles':roles(),'real_roles':real_roles,'active_role':active_role,'csrf':csrf_token(),'user_roles':user_roles,'user_permissions':user_permissions,'can':can,'PERMISSIONS':PERMISSIONS,'user_gov_ids':user_gov_ids,'user_branch_ids':user_branch_ids,'assignment_state':assignment_state,'assignment_supervisor':assignment_supervisor,'supervisor_for_entry':supervisor_for_entry,'entries_for_supervisor':entries_for_supervisor,'branch_entry':branch_entry,'auto_approver_for_employee':auto_approver_for_employee,'can_manage_employee':can_manage_employee,'ASSIGNMENT_STATES':ASSIGNMENT_STATES,'ASSIGNMENT_ALERT_DAYS':ASSIGNMENT_ALERT_DAYS}

@app.after_request
def security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options','nosniff')
    resp.headers.setdefault('X-Frame-Options','DENY')
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
    return [x.governorate_id for x in UserGovernorate.query.filter_by(user_id=u.id).join(Governorate).filter(Governorate.is_active==True)]
def bids():
    u=me()
    if not u: return []
    rs=roles(u)
    if 'مسؤول التطبيق' in rs: return [b.id for b in Branch.query.filter_by(is_active=True)]
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
        else: u.password_hash=generate_password_hash(new); u.must_change_password=False; log('PASSWORD_CHANGE','User',u.id); db.session.commit(); flash('تم تغيير كلمة المرور بنجاح.'); return redirect('/')
    return render_template('change_password.html')
@app.get('/')
@req
def home():
    bs=set(bids())
    today=date.today()
    tomorrow=today + timedelta(days=1)
    pending=[]
    ending=[]

    # Governorates visible to the current effective role.
    visible_govs=(Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True)
                  .order_by(Governorate.name.asc()).all() if gids() else [])

    # First-level users and their assigned branches, grouped for the expandable home tree.
    entry_rows=[]
    entry_users=User.query.join(UserRole,UserRole.user_id==User.id).filter(
        User.is_active==True, UserRole.role=='المدخل الأول'
    ).order_by(User.full_name.asc()).all()
    for u in entry_users:
        scoped=[b for b in Branch.query.join(UserBranch,UserBranch.branch_id==Branch.id).filter(
            UserBranch.user_id==u.id, Branch.is_active==True
        ).order_by(Branch.name.asc()).all() if b.id in bs]
        if not scoped:
            continue
        branch_groups=[]
        for b in scoped:
            emps=Employee.query.filter(Employee.branch_id==b.id,Employee.is_active==True).order_by(Employee.full_name.asc()).all()
            branch_groups.append({'branch':b,'employees':emps})
        gov_ids_for_entry={x['branch'].governorate_id for x in branch_groups}
        gov_names=[gobj.name for gobj in Governorate.query.filter(Governorate.id.in_(gov_ids_for_entry),Governorate.is_active==True).order_by(Governorate.name.asc()).all()] if gov_ids_for_entry else []
        entry_rows.append({'user':u,'branches':branch_groups,'governorates':gov_names,'employee_link':Employee.query.filter_by(user_id=u.id).first()})

    if bs:
        base=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True)
        if can('review_movements') and (has_role('مسؤول التطبيق') or has_role('مشرف محافظة')):
            pending=(base.filter(Movement.status=='تحت المراجعة')
                     .filter((Movement.approver_id==me().id) if 'مسؤول التطبيق' not in roles() else True)
                     .order_by(Movement.id.desc()).limit(20).all())
        ending=(base.filter(
                    Movement.movement_type.in_(['إجازة','انتداب']),
                    Movement.to_date!=None,
                    Movement.to_date>=today,
                    Movement.to_date<=tomorrow
                ).order_by(Movement.to_date.asc(),Movement.id.desc()).limit(30).all())

    return render_template(
        'home.html',
        g=len(visible_govs),
        b=len(bs),
        e=(Employee.query.filter(Employee.branch_id.in_(bs),Employee.is_active==True).count() if bs else 0),
        visible_govs=visible_govs,
        entry_rows=entry_rows,
        pending=pending,
        ending=ending,
        today=today,
        tomorrow=tomorrow,
        is_admin=has_role('مسؤول التطبيق')
    )

@app.get('/api/entry-ids/<int:gid>')
@req
def entry_ids_for_governorate(gid):
    if not gid: return set()
    bids_g={b.id for b in Branch.query.filter_by(governorate_id=gid,is_active=True).all()}
    if not bids_g: return set()
    return {x.user_id for x in UserBranch.query.filter(UserBranch.branch_id.in_(bids_g)).all()}

def branch_entry(b):
    links=UserBranch.query.filter_by(branch_id=b.id).all()
    for link in links:
        u=db.session.get(User,link.user_id)
        if u and u.is_active and 'المدخل الأول' in actual_roles(u): return u
    return None

@app.get('/structure')
@req
def structure():
    # الإدارة متاحة لمسؤول التطبيق ولمشرف المحافظة فقط.
    # المدخل الأول لا يملك صلاحية دخول الإدارة.
    if not (has_role('مسؤول التطبيق') or has_role('مشرف محافظة')): abort(403)
    is_admin=has_role('مسؤول التطبيق')

    # مسؤول التطبيق يختار المحافظة من قائمة منسدلة، والمشرف يرى محافظاته فقط.
    selected_gov=request.args.get('governorate_id','').strip()
    if is_admin:
        all_govs=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all()
        if selected_gov.isdigit() and any(g.id==int(selected_gov) for g in all_govs):
            govs=[db.session.get(Governorate,int(selected_gov))]
        else:
            govs=all_govs
            selected_gov=''
    else:
        govs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all() if gids() else []
        selected_gov=''

    tree=[]
    for g in govs:
        bs=Branch.query.filter_by(governorate_id=g.id,is_active=True).order_by(Branch.name).all()
        supervisors=[]
        suids=[x.user_id for x in UserGovernorate.query.filter_by(governorate_id=g.id).all()]
        for u in User.query.filter(User.id.in_(suids),User.is_active==True).order_by(User.full_name).all() if suids else []:
            if 'مشرف محافظة' not in roles(u): continue
            supervisors.append(u)
        entries=[]
        # Explicit hierarchy: supervisor -> first-level user -> branches -> employees.
        for u in User.query.filter_by(is_active=True).order_by(User.full_name).all():
            if 'المدخل الأول' not in actual_roles(u): continue
            ubids={x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()}
            scoped=[b for b in bs if b.id in ubids]
            for b in scoped:
                b.employee_items=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
            sup_link=SupervisorEntry.query.filter_by(entry_id=u.id).order_by(SupervisorEntry.id.asc()).first()
            sup=sup_link.supervisor if sup_link else None
            if not sup and len({b.governorate_id for b in scoped})==1: sup=supervisor_for_governorate(g.id)
            entries.append((u,scoped,sup,Employee.query.filter_by(user_id=u.id).first()))
        counts={b.id:Employee.query.filter_by(branch_id=b.id,is_active=True).count() for b in bs}
        for b in bs:
            if not hasattr(b,'employee_items'):
                b.employee_items=Employee.query.filter_by(branch_id=b.id,is_active=True).order_by(Employee.full_name).all()
        tree.append((g,bs,supervisors,entries,counts))
    govs_all=Governorate.query.filter_by(is_active=True).order_by(Governorate.name).all() if is_admin else govs
    return render_template(
        'structure.html',
        tree=tree,
        is_admin=is_admin,
        govs_all=govs_all,
        selected_governorate=selected_gov
    )

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
        return redirect('/structure')
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
                if eu and 'المدخل الأول' in actual_roles(eu) and g.id == g.id:
                    db.session.add(UserBranch(user_id=eu.id,branch_id=x.id))
                    employee=Employee.query.filter_by(user_id=eu.id).first()
                    if not employee:
                        db.session.add(Employee(user_id=eu.id,employee_code=None,full_name=eu.full_name,branch_id=x.id,job_title=eu.job_title,job_code=eu.job_code,is_active=True))
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
        username=request.form.get('username','').strip(); full=request.form.get('full_name','').strip(); job_title=request.form.get('job_title','').strip(); job_code=request.form.get('job_code','').strip(); password=request.form.get('password','')
        if not selected_roles or any(not allowed_create_user(r) for r in selected_roles): abort(403)
        if not username or not full or not job_title or not job_code or not valid_password(password) or User.query.filter_by(username=username).first(): flash('جميع بيانات الحساب مطلوبة، واسم المستخدم فريد وكلمة المرور 8 أحرف على الأقل.')
        else:
            nu=User(username=username,full_name=full,job_title=job_title,job_code=job_code,password_hash=generate_password_hash(password)); db.session.add(nu); db.session.flush()
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
                    db.session.rollback(); flash('يجب إسناد فرع واحد على الأقل للمدخل الأول.'); return redirect('/users')
                for bid in chosen: db.session.add(UserBranch(user_id=nu.id,branch_id=bid))
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
                # The first-level user is also an employee. Create/link the employee record automatically.
                if 'المدخل الأول' in selected_roles and chosen:
                    employee=Employee.query.filter_by(user_id=nu.id).first()
                    if not employee:
                        employee=Employee(user_id=nu.id,employee_code=None,full_name=nu.full_name,branch_id=next(iter(chosen)),job_title=nu.job_title,job_code=nu.job_code,is_active=True)
                        db.session.add(employee)
                    else:
                        employee.full_name=nu.full_name; employee.job_title=nu.job_title; employee.job_code=nu.job_code
            log('ADD','User',nu.id,username); db.session.commit(); flash('تم إنشاء الحساب وربطه تلقائيًا بالهيكل.')
    gs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).all() if 'مسؤول التطبيق' not in roles(u) else Governorate.query.filter_by(is_active=True).all()
    bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all() if 'مسؤول التطبيق' not in roles(u) else Branch.query.filter_by(is_active=True).all()
    role_default_permissions={r:sorted(ROLE_DEFAULT_PERMISSIONS.get(r,set())) for r in ROLES}
    return render_template('users.html',rows=visible,gs=gs,bs=bs,role_default_permissions=role_default_permissions)
@app.route('/users/<int:i>/edit',methods=['GET','POST'])
@req
def user_edit(i):
    target=db.session.get(User,i)
    if not target or not can('manage_users') or not allowed_target_user(target) and i!=me().id: abort(403)
    if 'مسؤول التطبيق' not in roles() and 'المدخل الأول' not in roles(target): abort(403)
    u=target
    if request.method=='POST':
        u.full_name=request.form.get('full_name','').strip() or u.full_name
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
                    db.session.rollback(); flash('يجب إسناد فرع واحد على الأقل للمدخل الأول.'); return redirect(url_for('user_edit',i=i))
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
                if linked_emp:
                    linked_emp.full_name=u.full_name; linked_emp.job_title=u.job_title; linked_emp.job_code=u.job_code
                    if linked_emp.branch_id not in chosen:
                        linked_emp.branch_id=next(iter(chosen))
                elif chosen:
                    db.session.add(Employee(user_id=i,employee_code=None,full_name=u.full_name,branch_id=next(iter(chosen)),job_title=u.job_title,job_code=u.job_code,is_active=True))
        else:
            # Supervisor may only edit first-level users in his governorate(s).
            selected_perm_set={x for x in request.form.getlist('permissions') if x in GRANTABLE_BY_SUPERVISOR}
            UserPermission.query.filter_by(user_id=i).delete()
            for perm in selected_perm_set: db.session.add(UserPermission(user_id=i,permission=perm))
            chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & set(bids())
            if not chosen: flash('يجب إسناد فرع واحد على الأقل.'); return redirect(url_for('user_edit',i=i))
            UserBranch.query.filter_by(user_id=i).delete()
            for bid in chosen: db.session.add(UserBranch(user_id=i,branch_id=bid))
            SupervisorEntry.query.filter_by(entry_id=i).delete()
            chosen_gids={db.session.get(Branch,bid).governorate_id for bid in chosen if db.session.get(Branch,bid)}
            sup=me() if 'مشرف محافظة' in actual_roles(me()) else None
            if sup and sup.is_active and chosen_gids & user_gov_ids(sup):
                db.session.add(SupervisorEntry(supervisor_id=sup.id,entry_id=i))
            linked_emp=Employee.query.filter_by(user_id=i).first()
            if linked_emp:
                linked_emp.full_name=u.full_name; linked_emp.job_title=u.job_title; linked_emp.job_code=u.job_code
                if linked_emp.branch_id not in chosen: linked_emp.branch_id=next(iter(chosen))
            else:
                db.session.add(Employee(user_id=i,employee_code=None,full_name=u.full_name,branch_id=next(iter(chosen)),job_title=u.job_title,job_code=u.job_code,is_active=True))
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
    return render_template('user_edit.html',u=u,selected_roles=roles(u),selected_permissions=user_permissions(u),gs=gs,bs=bs,entry_supervisor=entry_supervisor,supervisor_choices=supervisor_choices)
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
    else: u.password_hash=generate_password_hash(p); u.must_change_password=True; log('PASSWORD_RESET','User',i); db.session.commit(); flash('تمت إعادة التعيين.')
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
        if linked_emp.branch_id not in chosen: linked_emp.branch_id=next(iter(chosen))
        linked_emp.full_name=u.full_name; linked_emp.job_title=u.job_title; linked_emp.job_code=u.job_code
    else:
        db.session.add(Employee(user_id=i,employee_code=None,full_name=u.full_name,branch_id=next(iter(chosen)),job_title=u.job_title,job_code=u.job_code,is_active=True))
    log('ASSIGN','User',i,'فروع'); db.session.commit(); return redirect('/structure')


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
        name=request.form.get('full_name','').strip(); job_title=request.form.get('job_title','').strip(); job_code=request.form.get('job_code','').strip(); hire_date=request.form.get('hire_date','').strip(); company_phone=request.form.get('company_phone','').strip(); personal_phone=request.form.get('personal_phone','').strip()
        if not branch_obj or branch_obj.governorate_id!=submitted_gid: flash('يجب اختيار محافظة وفرع صحيحين.')
        elif not all([name,job_title,job_code,hire_date,company_phone,personal_phone]): flash('جميع بيانات الموظف مطلوبة.')
        elif not parse_date(hire_date): flash('تاريخ التعيين مطلوب وبصيغة صحيحة.')
        else:
            e=Employee(employee_code=None,full_name=name,branch_id=bid,job_title=job_title,job_code=job_code,hire_date=parse_date(hire_date),company_phone=company_phone,personal_phone=personal_phone); db.session.add(e); db.session.commit(); log('ADD','Employee',e.id,e.full_name); db.session.commit(); flash('تمت إضافة الموظف بنجاح. يمكنك الآن تسجيل أول حركة له.'); return redirect(url_for('card',i=e.id))
    branches=Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True).order_by(Branch.name).all() if bs else []
    q=request.args.get('q','').strip()
    branch_filter=request.args.get('branch_id','').strip()
    query=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)) if bs else Employee.query.filter(False)
    if q:
        like=f'%{q}%'; query=query.filter(db.or_(Employee.full_name.ilike(like),Employee.job_code.ilike(like),Employee.job_title.ilike(like)))
    if branch_filter.isdigit() and int(branch_filter) in bs: query=query.filter(Employee.branch_id==int(branch_filter))
    rows=query.order_by(Employee.full_name).all()
    gov_filter=request.args.get('governorate_id','').strip()
    govs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all() if gids() else []
    if gov_filter.isdigit() and int(gov_filter) in gids():
        branches=Branch.query.filter(Branch.governorate_id==int(gov_filter),Branch.is_active==True,Branch.id.in_(bs)).order_by(Branch.name).all()
        if not (branch_filter.isdigit() and int(branch_filter) in [b.id for b in branches]): branch_filter=''
        query=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_([b.id for b in branches]))
        if q:
            like=f'%{q}%'; query=query.filter(db.or_(Employee.full_name.ilike(like),Employee.job_code.ilike(like),Employee.job_title.ilike(like)))
        rows=query.order_by(Employee.full_name).all()
    return render_template('employees.html',rows=rows,bs=branches,q=q,branch_filter=branch_filter,govs=govs,gov_filter=gov_filter)
@app.route('/employees/<int:i>/edit',methods=['GET','POST'])
@req
def employee_edit(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if request.method=='POST':
        bid=int(request.form['branch_id'])
        if not branch_ok(bid): abort(403)
        submitted_gid=int(request.form.get('governorate_id','0')) if request.form.get('governorate_id','').isdigit() else 0
        branch_obj=db.session.get(Branch,bid)
        if not branch_obj or branch_obj.governorate_id!=submitted_gid: flash('يجب اختيار فرع تابع للمحافظة المحددة.'); return redirect(url_for('employee_edit',i=i))
        name=request.form.get('full_name','').strip(); job_title=request.form.get('job_title','').strip(); job_code=request.form.get('job_code','').strip(); hire_date=request.form.get('hire_date','').strip(); company_phone=request.form.get('company_phone','').strip(); personal_phone=request.form.get('personal_phone','').strip()
        if not all([name,job_title,job_code,hire_date,company_phone,personal_phone]): flash('جميع بيانات الموظف مطلوبة.'); return redirect(url_for('employee_edit',i=i))
        if not parse_date(hire_date): flash('تاريخ التعيين مطلوب وبصيغة صحيحة.'); return redirect(url_for('employee_edit',i=i))
        e.full_name=name; e.branch_id=bid; e.job_title=job_title; e.job_code=job_code; e.hire_date=parse_date(hire_date); e.company_phone=company_phone; e.personal_phone=personal_phone; log('EDIT','Employee',i,e.full_name); db.session.commit(); flash('تم تعديل الموظف.'); return redirect(url_for('employees'))
    return render_template('employee_edit.html',e=e,bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all(),govs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).order_by(Governorate.name).all())
@app.post('/employees/<int:i>/toggle')
@req
def et(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    e.is_active=not e.is_active; log('TOGGLE','Employee',i); db.session.commit(); return redirect('/employees')
@app.post('/employees/<int:i>/delete')
@req
def ed(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e) or not can('manage_employees'): abort(403)
    if Movement.query.filter_by(employee_id=i).count(): flash('لا يمكن حذف موظف له حركات تاريخية؛ استخدم التعطيل.')
    else: db.session.delete(e); log('DELETE','Employee',i); db.session.commit(); flash('تم حذف الموظف.')
    return redirect('/employees')
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

@app.route('/movements',methods=['GET','POST'])
@req
def movements():
    bs=bids()
    if request.method=='POST' and (not can_manage_movement() or not can('manage_movements')): abort(403)
    emps=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)).order_by(Employee.full_name).all() if bs else []
    if request.method=='POST':
        f=request.form; eid=int(f.get('employee_id','0')) if f.get('employee_id','').isdigit() else 0; e=db.session.get(Employee,eid)
        if not e or not branch_ok(e.branch_id): abort(403)
        mt=f.get('movement_type'); fd=f.get('from_date'); td=f.get('to_date'); pd=f.get('permission_date'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id','').isdigit() else None; status='تحت المراجعة'; approver=auto_approver_for_employee(e, me()); approver_id=approver.id if approver else None
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,fd,td,pd)
        if err: flash(err); return redirect('/movements')
        overlap=movement_overlaps(e.id,mt,fd,td,pd)
        if overlap: flash(overlap); return redirect('/movements')
        if not approver_id:
            flash('لا يوجد معتمد محدد تلقائيًا لهذه المحافظة. يجب إسناد مشرف محافظة مخول بالمراجعة أولًا.')
            return redirect('/movements')
        status='تحت المراجعة'
        m=Movement(employee_id=e.id,movement_type=mt,leave_type=f.get('leave_type') or None,destination_branch_id=dest,from_date=parse_date(fd),to_date=parse_date(td),permission_date=parse_date(pd),notes=None,created_by=me().id,status=status,assignment_state='ساري',approver_id=approver_id); db.session.add(m); db.session.commit(); record_movement_history(m,None,status,'ADD','إنشاء الحركة'); log('ADD','Movement',m.id,status); db.session.commit(); flash('تم حفظ الحركة.')
    rows=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.is_active==True).order_by(Movement.created_at.desc()).all() if bs else []
    selected_employee_id=request.args.get('employee_id', type=int)
    return render_template('movements.html',rows=rows,emps=emps,bs=Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True).all() if bs else [],leave_types=active_leave_types(),movement_types=active_movement_types(),statuses=STATUSES,selected_employee_id=selected_employee_id,approvers={e.id:approvers_for_employee(e) for e in emps})
@app.route('/movements/<int:i>/edit',methods=['GET','POST'])
@req
def movement_edit(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    # بعد إلغاء الاعتماد فقط يمكن تعديل تاريخ (من) و(إلى).
    last_history=MovementHistory.query.filter_by(movement_id=i).order_by(MovementHistory.id.desc()).first()
    dates_edit_after_cancel = (m.status=='تحت المراجعة' and last_history and last_history.action=='CANCEL_APPROVAL')
    if m.status=='تحت المراجعة' and not dates_edit_after_cancel:
        flash('لا يمكن تعديل الحركة وهي تحت المراجعة.'); return redirect('/movements')
    if m.status=='معتمدة':
        flash('لا يمكن تعديل الحركة المعتمدة. يجب إلغاء الاعتماد أولًا.'); return redirect('/movements')
    if not can_manage_movement(m) or not can('manage_movements'):
        abort(403)
    if request.method=='POST':
        f=request.form
        if dates_edit_after_cancel:
            if m.movement_type not in ('إجازة','انتداب'):
                flash('تعديل تاريخ البداية والنهاية متاح للإجازات والانتدابات فقط.'); return redirect(url_for('movement_edit',i=i))
            new_from=parse_date(f.get('from_date')); new_to=parse_date(f.get('to_date'))
            if not new_from or not new_to: flash('يجب إدخال تاريخ بداية ونهاية صحيحين.'); return redirect(url_for('movement_edit',i=i))
            if new_from>new_to: flash('تاريخ البداية يجب أن يكون قبل أو مساويًا لتاريخ النهاية.'); return redirect(url_for('movement_edit',i=i))
            overlap=movement_overlaps(m.employee_id,m.movement_type,f.get('from_date'),f.get('to_date'),None,i)
            if overlap: flash(overlap); return redirect(url_for('movement_edit',i=i))
            m.from_date=new_from; m.to_date=new_to; m.modified_by=me().id; m.modified_at=datetime.utcnow()
            record_movement_history(m,'تحت المراجعة','تحت المراجعة','EDIT','تعديل تاريخ البداية والنهاية بعد إلغاء الاعتماد')
            log('EDIT','Movement',i,'تعديل تاريخ البداية والنهاية بعد إلغاء الاعتماد')
            db.session.commit(); flash('تم تعديل تاريخ البداية والنهاية بعد إلغاء الاعتماد.'); return redirect('/movements')
        mt=f.get('movement_type'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id','').isdigit() else None
        approver=auto_approver_for_employee(m.employee, me()); approver_id=approver.id if approver else None
        if not approver_id:
            flash('لا يوجد معتمد محدد تلقائيًا لهذه المحافظة. يجب إسناد مشرف محافظة مخول بالمراجعة أولًا.'); return redirect(url_for('movement_edit',i=i))
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,f.get('from_date'),f.get('to_date'),f.get('permission_date'))
        if err: flash(err); return redirect(url_for('movement_edit',i=i))
        overlap=movement_overlaps(m.employee_id,mt,f.get('from_date'),f.get('to_date'),f.get('permission_date'),i)
        if overlap: flash(overlap); return redirect(url_for('movement_edit',i=i))
        old_status=m.status
        m.movement_type=mt; m.leave_type=f.get('leave_type') or None; m.destination_branch_id=dest; m.from_date=parse_date(f.get('from_date')); m.to_date=parse_date(f.get('to_date')); m.permission_date=parse_date(f.get('permission_date')); m.approver_id=approver_id; m.notes=None; m.modified_by=me().id; m.modified_at=datetime.utcnow(); m.status='تحت المراجعة'; m.rejection_reason=None; record_movement_history(m,old_status,'تحت المراجعة','EDIT','تعديل بيانات الحركة وإرسالها للمراجعة'); log('EDIT','Movement',i,'تعديل الحركة وإعادة إرسالها للمراجعة'); db.session.commit(); flash('تم تعديل الحركة وإرسالها للمراجعة.'); return redirect('/review')
    return render_template('movement_edit.html',m=m,emps=Employee.query.filter(Employee.branch_id.in_(bids()),Employee.is_active==True).order_by(Employee.full_name).all(),bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all(),leave_types=active_leave_types(),movement_types=active_movement_types(),approvers=approvers_for_employee(m.employee))
@app.post('/movements/<int:i>/submit')
@req
def movement_submit(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id) or not can_manage_movement(m): abort(403)
    if m.status in ('مسودة','مدخلة','مرفوضة'):
        approver=auto_approver_for_employee(m.employee, me()); aid=approver.id if approver else 0
        if not aid:
            flash('لا يوجد معتمد محدد تلقائيًا لهذه المحافظة. يجب إسناد مشرف محافظة مخول بالمراجعة أولًا.'); return redirect('/movements')
        old_status=m.status; m.status='تحت المراجعة'; m.approver_id=aid; m.rejection_reason=None; m.modified_by=me().id; m.modified_at=datetime.utcnow(); record_movement_history(m,old_status,'تحت المراجعة','SUBMIT','إرسال للمراجعة — المعتمد محدد تلقائيًا حسب التبعية'); log('SUBMIT','Movement',i,f'المعتمد التلقائي: {aid}'); db.session.commit(); flash('تم إرسال الحركة للمراجعة، وتم تحديد المعتمد تلقائيًا حسب التبعية.')
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

    allowed_govs=Governorate.query.filter(Governorate.is_active==True).order_by(Governorate.name.asc()).all()
    allowed_gov_ids={g.id for g in allowed_govs if g.id in set(gids())} if gids() else set()
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
    """One-time cleanup for the new deployment.
    Keeps the application administrator account only, removes legacy
    organizational/business records, and never repeats after the marker exists.
    """
    marker = Lookup.query.filter_by(kind='system', name='v34.9.6_legacy_purged').first()
    if marker:
        return False

    admin_username = os.getenv('ADMIN_USERNAME','admin')
    admin = User.query.filter_by(username=admin_username).first()
    if not admin:
        return False

    # Delete children first to satisfy foreign-key constraints.
    MovementHistory.query.delete(synchronize_session=False)
    Audit.query.delete(synchronize_session=False)
    ApprovalDelegation.query.delete(synchronize_session=False)
    SupervisorEntry.query.delete(synchronize_session=False)
    Movement.query.delete(synchronize_session=False)
    Employee.query.delete(synchronize_session=False)
    UserBranch.query.delete(synchronize_session=False)
    UserGovernorate.query.delete(synchronize_session=False)
    UserPermission.query.filter(UserPermission.user_id != admin.id).delete(synchronize_session=False)
    UserRole.query.filter(UserRole.user_id != admin.id).delete(synchronize_session=False)
    Branch.query.delete(synchronize_session=False)
    Governorate.query.delete(synchronize_session=False)
    User.query.filter(User.id != admin.id).delete(synchronize_session=False)

    # Reset administrator scope links; the administrator is global by role.
    UserBranch.query.filter_by(user_id=admin.id).delete(synchronize_session=False)
    UserGovernorate.query.filter_by(user_id=admin.id).delete(synchronize_session=False)

    if not UserRole.query.filter_by(user_id=admin.id, role='مسؤول التطبيق').first():
        db.session.add(UserRole(user_id=admin.id, role='مسؤول التطبيق'))
    for perm in PERMISSIONS:
        if not UserPermission.query.filter_by(user_id=admin.id, permission=perm).first():
            db.session.add(UserPermission(user_id=admin.id, permission=perm))

    db.session.add(Lookup(kind='system', name='v34.9.6_legacy_purged', is_active=True))
    db.session.commit()
    return True

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
    ecols_existing={c['name'] for c in insp.get_columns('employee')}
    if 'user_id' not in ecols_existing:
        db.session.execute(text('ALTER TABLE employee ADD COLUMN user_id INTEGER'))
    mcols={c['name'] for c in insp.get_columns('movement')}
    if 'approver_id' not in mcols:
        db.session.execute(text('ALTER TABLE movement ADD COLUMN approver_id INTEGER'))
    ApprovalDelegation.__table__.create(bind=db.engine, checkfirst=True)
    SupervisorEntry.__table__.create(bind=db.engine, checkfirst=True)
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
    admin_name=os.getenv('ADMIN_USERNAME','admin'); admin_pass=os.getenv('ADMIN_PASSWORD','CHANGE_INITIAL_ADMIN_PASSWORD')
    u=User.query.filter_by(username=admin_name).first()
    if not u:
        u=User(username=admin_name,full_name='مسؤول التطبيق',password_hash=generate_password_hash(admin_pass)); db.session.add(u); db.session.flush(); db.session.add(UserRole(user_id=u.id,role='مسؤول التطبيق')); db.session.commit()
    else:
        if not u.job_title: u.job_title='مسؤول التطبيق'
        if not u.job_code: u.job_code='ADMIN'
        db.session.commit()
    if not UserRole.query.filter_by(user_id=u.id,role='مسؤول التطبيق').first():
        db.session.add(UserRole(user_id=u.id,role='مسؤول التطبيق')); db.session.commit()
    purge_old_records_once()

if __name__=='__main__': app.run(host='0.0.0.0',port=8000)
