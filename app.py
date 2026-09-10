import os, secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import UniqueConstraint
from werkzeug.security import generate_password_hash, check_password_hash

app=Flask(__name__)
APP_VERSION='v9.0'
app.config.update(SECRET_KEY=os.getenv('SECRET_KEY','CHANGE-ME'),SQLALCHEMY_DATABASE_URI=os.getenv('DATABASE_URL','sqlite:///local.db'),SQLALCHEMY_TRACK_MODIFICATIONS=False,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1',MAX_CONTENT_LENGTH=2*1024*1024)
db=SQLAlchemy(app)
ROLES=['مسؤول التطبيق','مشرف محافظة','المدخل الأول']
MOVEMENT_TYPES=['إجازة','انتداب','إذن']
LEAVE_TYPES=['سنوية','مرضية','غياب','مصيف','زواج','أمومة','غير مدفوعة','وفاة درجة أولى','جيش']
STATUSES=['مسودة','مدخلة','تحت المراجعة','معتمدة','مرفوضة']

class User(db.Model):
    id=db.Column(db.Integer,primary_key=True); username=db.Column(db.String(80),unique=True,nullable=False); full_name=db.Column(db.String(200),nullable=False); password_hash=db.Column(db.Text,nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False); must_change_password=db.Column(db.Boolean,default=True,nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); last_login=db.Column(db.DateTime)
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
class Employee(db.Model):
    id=db.Column(db.Integer,primary_key=True); employee_code=db.Column(db.String(100),unique=True,nullable=False); full_name=db.Column(db.String(250),nullable=False); branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT'),nullable=False); job_title=db.Column(db.String(200)); job_code=db.Column(db.String(100)); hire_date=db.Column(db.Date); company_phone=db.Column(db.String(80)); personal_phone=db.Column(db.String(80)); is_active=db.Column(db.Boolean,default=True,nullable=False); branch=db.relationship('Branch')
class Movement(db.Model):
    id=db.Column(db.Integer,primary_key=True); employee_id=db.Column(db.Integer,db.ForeignKey('employee.id',ondelete='RESTRICT'),nullable=False); movement_type=db.Column(db.String(30),nullable=False); leave_type=db.Column(db.String(100)); destination_branch_id=db.Column(db.Integer,db.ForeignKey('branch.id',ondelete='RESTRICT')); from_date=db.Column(db.Date); to_date=db.Column(db.Date); permission_date=db.Column(db.Date); status=db.Column(db.String(30),default='مسودة',nullable=False); notes=db.Column(db.Text); created_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='RESTRICT'),nullable=False); created_at=db.Column(db.DateTime,default=datetime.utcnow); modified_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); modified_at=db.Column(db.DateTime); reviewed_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); reviewed_at=db.Column(db.DateTime); approved_by=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); approved_at=db.Column(db.DateTime); employee=db.relationship('Employee'); destination=db.relationship('Branch',foreign_keys=[destination_branch_id])
class Audit(db.Model):
    id=db.Column(db.Integer,primary_key=True); user_id=db.Column(db.Integer,db.ForeignKey('user.id',ondelete='SET NULL')); action=db.Column(db.String(80),nullable=False); entity=db.Column(db.String(80)); entity_id=db.Column(db.Integer); details=db.Column(db.Text); created_at=db.Column(db.DateTime,default=datetime.utcnow)
class Lookup(db.Model):
    id=db.Column(db.Integer,primary_key=True); kind=db.Column(db.String(30),nullable=False); name=db.Column(db.String(120),nullable=False); is_active=db.Column(db.Boolean,default=True,nullable=False); __table_args__=(UniqueConstraint('kind','name',name='uq_lookup_kind_name'),)

def me(): return db.session.get(User,session.get('uid'))
def roles(u=None):
    u=u or me(); return {x.role for x in UserRole.query.filter_by(user_id=u.id).all()} if u else set()
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
def user_gov_ids(u): return {x.governorate_id for x in UserGovernorate.query.filter_by(user_id=u.id).all()}
def user_branch_ids(u): return {x.branch_id for x in UserBranch.query.filter_by(user_id=u.id).all()}
@app.context_processor
def inject_context(): return {'me':me(),'roles':roles(),'csrf':csrf_token(),'user_roles':user_roles,'user_gov_ids':user_gov_ids,'user_branch_ids':user_branch_ids}

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
    rs=roles()
    return bool(e and branch_ok(e.branch_id) and ('مسؤول التطبيق' in rs or 'المدخل الأول' in rs))

def can_manage_movement(m=None):
    rs=roles()
    if 'مسؤول التطبيق' in rs: return True
    if 'المدخل الأول' not in rs: return False
    return bool(m and m.created_by==me().id) if m else True

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method=='POST':
        u=User.query.filter_by(username=request.form.get('username','').strip()).first()
        if not u or not u.is_active or not check_password_hash(u.password_hash,request.form.get('password','')): flash('بيانات الدخول غير صحيحة.'); return render_template('login.html')
        session.clear(); session['uid']=u.id; session['csrf']=secrets.token_urlsafe(24); u.last_login=datetime.utcnow(); log('LOGIN','User',u.id); db.session.commit(); return redirect('/')
    return render_template('login.html')
@app.get('/logout')
def logout(): session.clear(); return redirect('/login')
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
    bs=bids(); q=Employee.query.filter(Employee.branch_id.in_(bs)).count() if bs else 0; m=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs)).count() if bs else 0; p=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs),Movement.status=='تحت المراجعة').count() if bs else 0
    return render_template('home.html',g=len(gids()),b=len(bs),e=q,m=m,p=p)

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
@only('مسؤول التطبيق')
def branches():
    if request.method=='POST':
        gid=request.form.get('governorate_id'); name=request.form.get('name','').strip(); code=request.form.get('code','').strip() or None
        g=db.session.get(Governorate,int(gid)) if gid and gid.isdigit() else None
        if not g or not g.is_active or not name: flash('بيانات الفرع غير صحيحة.')
        elif Branch.query.filter_by(governorate_id=g.id,name=name).first(): flash('الفرع موجود بالفعل في هذه المحافظة.')
        else: x=Branch(governorate_id=g.id,name=name,code=code); db.session.add(x); db.session.commit(); log('ADD','Branch',x.id,name); db.session.commit(); flash('تمت الإضافة.')
    return render_template('branches.html',rows=Branch.query.order_by(Branch.name),gs=Governorate.query.filter_by(is_active=True))
@app.post('/branches/<int:i>/edit')
@req
@only('مسؤول التطبيق')
def be(i):
    x=db.session.get(Branch,i); g=db.session.get(Governorate,int(request.form.get('governorate_id','0'))); n=request.form.get('name','').strip(); code=request.form.get('code','').strip() or None
    if not x or not g or not g.is_active or not n: abort(400)
    dup=Branch.query.filter(Branch.governorate_id==g.id,Branch.name==n,Branch.id!=i).first()
    if dup: flash('الفرع موجود بالفعل في هذه المحافظة.')
    else:
        x.governorate_id=g.id; x.name=n; x.code=code; log('EDIT','Branch',i,n); db.session.commit(); flash('تم التعديل.')
    return redirect('/branches')
@app.post('/branches/<int:i>/toggle')
@req
@only('مسؤول التطبيق')
def bt(i):
    x=db.session.get(Branch,i)
    if not x: abort(404)
    x.is_active=not x.is_active; log('TOGGLE','Branch',i); db.session.commit(); return redirect('/branches')
@app.post('/branches/<int:i>/delete')
@req
@only('مسؤول التطبيق')
def bd(i):
    x=db.session.get(Branch,i)
    if not x: abort(404)
    if Employee.query.filter_by(branch_id=i).count() or UserBranch.query.filter_by(branch_id=i).count() or Movement.query.filter_by(destination_branch_id=i).count(): flash('لا يمكن الحذف لوجود بيانات مرتبطة؛ استخدم التعطيل.')
    else: db.session.delete(x); log('DELETE','Branch',i); db.session.commit(); flash('تم الحذف.')
    return redirect('/branches')

@app.route('/users',methods=['GET','POST'])
@req
@only('مسؤول التطبيق','مشرف محافظة')
def users():
    u=me(); visible=User.query.order_by(User.id.desc()).all() if 'مسؤول التطبيق' in roles(u) else [x for x in User.query.order_by(User.id.desc()).all() if x.id==u.id or allowed_target_user(x)]
    if request.method=='POST':
        role=request.form.get('role'); username=request.form.get('username','').strip(); full=request.form.get('full_name','').strip(); password=request.form.get('password','')
        if not allowed_create_user(role): abort(403)
        if not username or not full or not valid_password(password) or User.query.filter_by(username=username).first(): flash('تحقق من البيانات: الاسم/المستخدم فريد وكلمة المرور 8 أحرف على الأقل.')
        else:
            nu=User(username=username,full_name=full,password_hash=generate_password_hash(password)); db.session.add(nu); db.session.flush(); db.session.add(UserRole(user_id=nu.id,role=role));
            if role=='مشرف محافظة':
                chosen={int(x) for x in request.form.getlist('governorate_id') if x.isdigit()}
                allowed=set(gids()) if 'مسؤول التطبيق' not in roles(u) else {g.id for g in Governorate.query.filter_by(is_active=True)}
                chosen &= allowed
                if not chosen:
                    db.session.rollback(); flash('يجب إسناد محافظة واحدة على الأقل لمشرف المحافظة.'); return redirect('/users')
                for gid in chosen: db.session.add(UserGovernorate(user_id=nu.id,governorate_id=gid))
            if role=='المدخل الأول':
                chosen={int(x) for x in request.form.getlist('branch_id') if x.isdigit()} & set(bids())
                if not chosen:
                    db.session.rollback(); flash('يجب إسناد فرع واحد على الأقل للمدخل الأول.'); return redirect('/users')
                for bid in chosen: db.session.add(UserBranch(user_id=nu.id,branch_id=bid))
            log('ADD','User',nu.id,username); db.session.commit(); flash('تم إنشاء الحساب. سيُطلب من المستخدم تغيير كلمة المرور عند أول دخول.')
    gs=Governorate.query.filter(Governorate.id.in_(gids()),Governorate.is_active==True).all() if 'مسؤول التطبيق' not in roles(u) else Governorate.query.filter_by(is_active=True).all()
    bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all() if 'مسؤول التطبيق' not in roles(u) else Branch.query.filter_by(is_active=True).all()
    return render_template('users.html',rows=visible,gs=gs,bs=bs)
@app.route('/users/<int:i>/edit',methods=['GET','POST'])
@req
@only('مسؤول التطبيق')
def user_edit(i):
    u=db.session.get(User,i)
    if not u: abort(404)
    if request.method=='POST':
        u.full_name=request.form.get('full_name','').strip() or u.full_name
        selected=[r for r in request.form.getlist('roles') if r in ROLES]
        if not selected: flash('يجب اختيار دور واحد على الأقل.')
        elif i==me().id and 'مسؤول التطبيق' not in selected: flash('لا يمكن إزالة دور مسؤول التطبيق من حسابك هنا.')
        else:
            UserRole.query.filter_by(user_id=i).delete()
            for r in selected: db.session.add(UserRole(user_id=i,role=r))
            log('EDIT','User',i,'تعديل الاسم والأدوار'); db.session.commit(); flash('تم التعديل.'); return redirect('/users')
    return render_template('user_edit.html',u=u,user_roles=roles(u))
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
@only('مسؤول التطبيق','مشرف محافظة')
def ur(i):
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
    log('ASSIGN','User',i,'فروع'); db.session.commit(); return redirect('/users')


@app.route('/employees',methods=['GET','POST'])
@req
def employees():
    bs=bids()
    if request.method=='POST':
        if not ('مسؤول التطبيق' in roles() or 'المدخل الأول' in roles()): abort(403)
        bid=int(request.form['branch_id'])
        if not branch_ok(bid): abort(403)
        code=request.form.get('employee_code','').strip(); name=request.form.get('full_name','').strip()
        if not code or not name: flash('الكود والاسم مطلوبان.')
        elif Employee.query.filter_by(employee_code=code).first(): flash('كود الموظف موجود بالفعل.')
        else:
            e=Employee(employee_code=code,full_name=name,branch_id=bid,job_title=request.form.get('job_title'),job_code=request.form.get('job_code'),hire_date=parse_date(request.form.get('hire_date')),company_phone=request.form.get('company_phone'),personal_phone=request.form.get('personal_phone')); db.session.add(e); db.session.commit(); log('ADD','Employee',e.id,e.full_name); db.session.commit(); flash('تمت إضافة الموظف.')
    rows=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)).order_by(Employee.full_name).all() if bs else []
    return render_template('employees.html',rows=rows,bs=Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True).all() if bs else [])
@app.route('/employees/<int:i>/edit',methods=['GET','POST'])
@req
def employee_edit(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e): abort(403)
    if request.method=='POST':
        bid=int(request.form['branch_id'])
        if not branch_ok(bid): abort(403)
        code=request.form.get('employee_code','').strip(); name=request.form.get('full_name','').strip()
        dup=Employee.query.filter(Employee.employee_code==code,Employee.id!=i).first()
        if not code or not name: flash('الكود والاسم مطلوبان.'); return redirect(url_for('employee_edit',i=i))
        if dup: flash('كود الموظف موجود بالفعل.'); return redirect(url_for('employee_edit',i=i))
        e.employee_code=code; e.full_name=name; e.branch_id=bid; e.job_title=request.form.get('job_title'); e.job_code=request.form.get('job_code'); e.hire_date=parse_date(request.form.get('hire_date')); e.company_phone=request.form.get('company_phone'); e.personal_phone=request.form.get('personal_phone'); log('EDIT','Employee',i,e.full_name); db.session.commit(); flash('تم تعديل الموظف.'); return redirect(url_for('employees'))
    return render_template('employee_edit.html',e=e,bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all())
@app.post('/employees/<int:i>/toggle')
@req
def et(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e): abort(403)
    e.is_active=not e.is_active; log('TOGGLE','Employee',i); db.session.commit(); return redirect('/employees')
@app.post('/employees/<int:i>/delete')
@req
def ed(i):
    e=db.session.get(Employee,i)
    if not can_manage_employee(e): abort(403)
    if Movement.query.filter_by(employee_id=i).count(): flash('لا يمكن حذف موظف له حركات تاريخية؛ استخدم التعطيل.')
    else: db.session.delete(e); log('DELETE','Employee',i); db.session.commit(); flash('تم حذف الموظف.')
    return redirect('/employees')
@app.get('/employee/<int:i>')
@req
def card(i):
    e=db.session.get(Employee,i)
    if not e or not branch_ok(e.branch_id): abort(403)
    ms=Movement.query.filter_by(employee_id=i).order_by(Movement.from_date.desc().nullslast(),Movement.permission_date.desc().nullslast(),Movement.id.desc()).all(); last={k:next((m for m in ms if m.movement_type==k),None) for k in MOVEMENT_TYPES}; return render_template('employee.html',e=e,ms=ms,last=last)

@app.route('/movements',methods=['GET','POST'])
@req
def movements():
    bs=bids()
    if request.method=='POST' and not can_manage_movement(): abort(403)
    emps=Employee.query.filter(Employee.is_active==True,Employee.branch_id.in_(bs)).order_by(Employee.full_name).all() if bs else []
    if request.method=='POST':
        f=request.form; e=db.session.get(Employee,int(f['employee_id']))
        if not e or not branch_ok(e.branch_id): abort(403)
        mt=f.get('movement_type'); fd=f.get('from_date'); td=f.get('to_date'); pd=f.get('permission_date'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id') else None; status=f.get('action','مسودة')
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,fd,td,pd)
        if err: flash(err); return redirect('/movements')
        if status not in ('مسودة','مدخلة'): status='مدخلة'
        m=Movement(employee_id=e.id,movement_type=mt,leave_type=f.get('leave_type') or None,destination_branch_id=dest,from_date=parse_date(fd),to_date=parse_date(td),permission_date=parse_date(pd),notes=f.get('notes'),created_by=me().id,status=status); db.session.add(m); db.session.commit(); log('ADD','Movement',m.id,status); db.session.commit(); flash('تم حفظ الحركة.')
    rows=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs)).order_by(Movement.created_at.desc()).all() if bs else []
    return render_template('movements.html',rows=rows,emps=emps,bs=Branch.query.filter(Branch.id.in_(bs),Branch.is_active==True).all() if bs else [],leave_types=active_leave_types(),movement_types=active_movement_types(),statuses=STATUSES)
@app.route('/movements/<int:i>/edit',methods=['GET','POST'])
@req
def movement_edit(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if m.status in ('معتمدة','تحت المراجعة'): flash('لا يمكن تعديل الحركة وهي معتمدة أو تحت المراجعة.'); return redirect('/movements')
    if not can_manage_movement(m): abort(403)
    if request.method=='POST':
        f=request.form; mt=f.get('movement_type'); dest=int(f['destination_branch_id']) if f.get('destination_branch_id') else None
        err=validate_movement_fields(mt,f.get('leave_type') or None,dest,f.get('from_date'),f.get('to_date'),f.get('permission_date'))
        if err: flash(err); return redirect(url_for('movement_edit',i=i))
        m.movement_type=mt; m.leave_type=f.get('leave_type') or None; m.destination_branch_id=dest; m.from_date=parse_date(f.get('from_date')); m.to_date=parse_date(f.get('to_date')); m.permission_date=parse_date(f.get('permission_date')); m.notes=f.get('notes'); m.modified_by=me().id; m.modified_at=datetime.utcnow(); log('EDIT','Movement',i,'تعديل الحركة'); db.session.commit(); flash('تم تعديل الحركة.'); return redirect('/movements')
    return render_template('movement_edit.html',m=m,emps=Employee.query.filter(Employee.branch_id.in_(bids()),Employee.is_active==True).order_by(Employee.full_name).all(),bs=Branch.query.filter(Branch.id.in_(bids()),Branch.is_active==True).all(),leave_types=active_leave_types(),movement_types=active_movement_types())
@app.post('/movements/<int:i>/submit')
@req
def movement_submit(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id) or not can_manage_movement(m): abort(403)
    if m.status in ('مسودة','مدخلة','مرفوضة'): m.status='تحت المراجعة'; m.modified_by=me().id; m.modified_at=datetime.utcnow(); log('SUBMIT','Movement',i); db.session.commit(); flash('تم إرسال الحركة للمراجعة.')
    return redirect('/movements')
@app.post('/movements/<int:i>/status')
@req
@only('مسؤول التطبيق','مشرف محافظة')
def ms(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    s=request.form.get('status')
    if s not in ('معتمدة','مرفوضة') or m.status!='تحت المراجعة': abort(400)
    m.status=s; m.reviewed_by=me().id; m.reviewed_at=datetime.utcnow(); m.approved_by=me().id if s=='معتمدة' else None; m.approved_at=datetime.utcnow() if s=='معتمدة' else None; log('APPROVE' if s=='معتمدة' else 'REJECT','Movement',i,s); db.session.commit(); return redirect('/movements')
@app.post('/movements/<int:i>/delete')
@req
def md(i):
    m=db.session.get(Movement,i)
    if not m or not branch_ok(m.employee.branch_id): abort(403)
    if m.status=='معتمدة': flash('لا يمكن حذف حركة معتمدة.')
    elif can_manage_movement(m): db.session.delete(m); log('DELETE','Movement',i); db.session.commit(); flash('تم حذف الحركة.')
    else: flash('لا تملك صلاحية الحذف.')
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

@app.get('/audit')
@req
@only('مسؤول التطبيق')
def audit(): return render_template('audit.html',rows=Audit.query.order_by(Audit.created_at.desc()).limit(1000).all())
@app.get('/reports')
@req
def reports():
    bs=bids(); q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs)) if bs else Movement.query.filter(False)
    status=request.args.get('status','').strip(); mt=request.args.get('movement_type','').strip();
    if status in STATUSES: q=q.filter(Movement.status==status)
    if mt in active_movement_types(): q=q.filter(Movement.movement_type==mt)
    summary={s:q.filter(Movement.status==s).count() for s in STATUSES}; by_type={t:q.filter(Movement.movement_type==t).count() for t in MOVEMENT_TYPES}
    return render_template('reports.html',summary=summary,by_type=by_type,status=status,movement_type=mt,statuses=STATUSES,movement_types=active_movement_types())
@app.get('/reports.csv')
@req
def report_csv():
    import csv,io
    bs=bids(); q=Movement.query.join(Employee).filter(Employee.branch_id.in_(bs)) if bs else Movement.query.filter(False)
    status=request.args.get('status','').strip(); mt=request.args.get('movement_type','').strip()
    if status in STATUSES: q=q.filter(Movement.status==status)
    if mt in active_movement_types(): q=q.filter(Movement.movement_type==mt)
    rows=q.order_by(Movement.created_at.desc()).all()
    out=io.StringIO(); w=csv.writer(out); w.writerow(['MovementID','EmployeeCode','EmployeeName','Branch','MovementType','LeaveType','From','To','PermissionDate','Status','CreatedAt'])
    for m in rows: w.writerow([m.id,m.employee.employee_code,m.employee.full_name,m.employee.branch.name,m.movement_type,m.leave_type or '',m.from_date or '',m.to_date or '',m.permission_date or '',m.status,m.created_at])
    from flask import Response
    return Response('\ufeff'+out.getvalue(),mimetype='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename=movements_report.csv'})

with app.app_context():
    db.create_all()
    admin_name=os.getenv('ADMIN_USERNAME','admin'); admin_pass=os.getenv('ADMIN_PASSWORD','CHANGE_INITIAL_ADMIN_PASSWORD')
    u=User.query.filter_by(username=admin_name).first()
    if not u:
        u=User(username=admin_name,full_name='مسؤول التطبيق',password_hash=generate_password_hash(admin_pass)); db.session.add(u); db.session.flush(); db.session.add(UserRole(user_id=u.id,role='مسؤول التطبيق')); db.session.commit()
    else:
        if not UserRole.query.filter_by(user_id=u.id,role='مسؤول التطبيق').first(): db.session.add(UserRole(user_id=u.id,role='مسؤول التطبيق')); db.session.commit()
if __name__=='__main__': app.run(host='0.0.0.0',port=8000)
