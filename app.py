import os
from datetime import datetime, date
from functools import wraps
from secrets import token_urlsafe
from urllib.parse import urljoin, urlparse
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash

APP_VERSION = '1.0.5-cyan-bootstrap' 
APP_ENV = os.getenv('APP_ENV', 'development').strip().lower()
app = Flask(__name__)
secret_key = os.getenv('SECRET_KEY', '').strip()
if APP_ENV == 'production' and len(secret_key) < 32:
    raise RuntimeError('SECRET_KEY must be a unique random secret of at least 32 characters in production.')
app.config['SECRET_KEY'] = secret_key or token_urlsafe(48)
db_url = os.getenv('DATABASE_URL', '').strip()
if APP_ENV == 'production' and not db_url:
    raise RuntimeError('DATABASE_URL is required in production; refusing to start with a local SQLite database.')
if not db_url:
    db_url = 'sqlite:///employee_movements.db'
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif db_url.startswith('postgresql://'):
    db_url = db_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = APP_ENV == 'production'
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_TIME_LIMIT'] = 3600
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

ROLES = {
    'admin': 'Admin',
    'supervisor': 'مشرف محافظة',
    'manager_support': 'مدير دعم التطبيق',
    'first_entry': 'مدخل أول',
}
MOVEMENT_TYPES = {'leave': 'إجازة', 'assignment': 'انتداب', 'permission': 'إذن'}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(160), nullable=False)
    role = db.Column(db.String(40), nullable=False, default='supervisor')
    active = db.Column(db.Boolean, default=True, nullable=False)
    is_review_account = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    scopes = db.relationship('UserGovernorate', back_populates='user', cascade='all, delete-orphan')
    def set_password(self, password): self.password_hash = generate_password_hash(password)
    def check_password(self, password): return check_password_hash(self.password_hash, password)

class Governorate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    branches = db.relationship('Branch', back_populates='governorate', cascade='all, delete-orphan')

class UserGovernorate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    governorate_id = db.Column(db.Integer, db.ForeignKey('governorate.id'), nullable=False)
    user = db.relationship('User', back_populates='scopes')
    governorate = db.relationship('Governorate')
    __table_args__ = (db.UniqueConstraint('user_id', 'governorate_id'),)

class Branch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    code = db.Column(db.String(40), nullable=True)
    governorate_id = db.Column(db.Integer, db.ForeignKey('governorate.id'), nullable=False)
    governorate = db.relationship('Governorate', back_populates='branches')
    employees = db.relationship('Employee', back_populates='branch')
    __table_args__ = (db.UniqueConstraint('name', 'governorate_id'),)

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hr_code = db.Column(db.String(60), unique=True, nullable=False)
    full_name = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    job_title = db.Column(db.String(120), nullable=True)
    branch_id = db.Column(db.Integer, db.ForeignKey('branch.id'), nullable=False)
    resignation_date = db.Column(db.Date, nullable=True)
    branch = db.relationship('Branch', back_populates='employees')
    movements = db.relationship('Movement', back_populates='employee', cascade='all, delete-orphan')

class Movement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    kind = db.Column(db.String(30), nullable=False)
    start_date = db.Column(db.Date, nullable=False, default=date.today)
    end_date = db.Column(db.Date, nullable=True)
    destination = db.Column(db.String(180), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    employee = db.relationship('Employee', back_populates='movements')
    creator = db.relationship('User')

class Delegation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    governorate_id = db.Column(db.Integer, db.ForeignKey('governorate.id'), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    active = db.Column(db.Boolean, default=True, nullable=False)
    from_user = db.relationship('User', foreign_keys=[from_user_id])
    to_user = db.relationship('User', foreign_keys=[to_user_id])
    governorate = db.relationship('Governorate')


def current_user():
    uid = session.get('user_id')
    return db.session.get(User, uid) if uid else None

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for('login', next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def roles_required(*roles):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*args, **kwargs):
            user = current_user()
            if not user or user.role not in roles:
                flash('ليس لديك صلاحية لتنفيذ هذا الإجراء.', 'error')
                return redirect(url_for('home'))
            return fn(*args, **kwargs)
        return wrapper
    return deco

def selected_governorate():
    user = current_user()
    gid = session.get('work_governorate_id')
    if not user or not gid: return None
    gov = db.session.get(Governorate, gid)
    if not gov: return None
    if user.role == 'admin': return gov
    allowed = {s.governorate_id for s in user.scopes}
    delegated = {d.governorate_id for d in Delegation.query.filter_by(to_user_id=user.id, active=True).filter(Delegation.start_date <= date.today(), Delegation.end_date >= date.today()).all()}
    return gov if gid in allowed or gid in delegated else None

def operational_access(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        user = current_user()
        if user.role == 'first_entry':
            flash('دور المدخل الأول مرتبط بسجل الموظف وليس حساب دخول مستقلًا في هذا الإصدار.', 'info')
            return redirect(url_for('home'))
        if not selected_governorate():
            flash('اختر محافظة العمل أولًا.', 'info')
            return redirect(url_for('choose_governorate'))
        return fn(*args, **kwargs)
    return wrapper

@app.context_processor
def inject_globals():
    user = current_user()
    return {'current_user': user, 'role_names': ROLES, 'movement_types': MOVEMENT_TYPES,
            'work_governorate': selected_governorate(), 'app_version': APP_VERSION}

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        user = User.query.filter_by(username=username, active=True).first()
        if user and user.check_password(password):
            session.clear(); session['user_id'] = user.id
            nxt = request.args.get('next') or url_for('home')
            # Never redirect to an arbitrary external host after login.
            target = urlparse(urljoin(request.host_url, nxt))
            if target.scheme not in ('http', 'https') or target.netloc != request.host:
                nxt = url_for('home')
            return redirect(nxt)
        flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'error')
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    session.clear(); return redirect(url_for('login'))

@app.route('/')
@login_required
def home():
    user = current_user()
    query = request.args.get('q','').strip()
    employee_results = []
    if query:
        employee_results = Employee.query.filter(Employee.resignation_date.is_(None)).filter(
            db.or_(Employee.full_name.ilike(f'%{query}%'), Employee.hr_code.ilike(f'%{query}%'), Employee.phone.ilike(f'%{query}%'))
        ).order_by(Employee.full_name).limit(30).all()
    gov = selected_governorate()
    if user.role in ('admin','supervisor','manager_support') and not gov:
        return render_template('home.html', needs_scope=True, employee_results=employee_results, query=query,
                               employees_count=0, active_movements=0, branches_count=0, recent_movements=[])
    employees_q = Employee.query.filter(Employee.resignation_date.is_(None))
    movements_q = Movement.query.filter_by(active=True)
    branches_q = Branch.query
    if gov:
        employees_q = employees_q.join(Branch).filter(Branch.governorate_id == gov.id)
        movements_q = movements_q.join(Employee).join(Branch).filter(Branch.governorate_id == gov.id)
        branches_q = branches_q.filter_by(governorate_id=gov.id)
    return render_template('home.html', needs_scope=False, employee_results=employee_results, query=query,
        employees_count=employees_q.count(), active_movements=movements_q.count(), branches_count=branches_q.count(),
        recent_movements=movements_q.order_by(Movement.created_at.desc()).limit(8).all())

@app.route('/choose-governorate', methods=['GET','POST'])
@login_required
def choose_governorate():
    user = current_user()
    if user.role == 'admin': allowed = Governorate.query.order_by(Governorate.name).all()
    else:
        allowed_ids = {s.governorate_id for s in user.scopes}
        allowed_ids |= {d.governorate_id for d in Delegation.query.filter_by(to_user_id=user.id, active=True).filter(Delegation.start_date <= date.today(), Delegation.end_date >= date.today()).all()}
        allowed = Governorate.query.filter(Governorate.id.in_(allowed_ids)).order_by(Governorate.name).all() if allowed_ids else []
    if request.method == 'POST':
        try: gid = int(request.form.get('governorate_id',''))
        except ValueError: gid = 0
        if any(g.id == gid for g in allowed):
            session['work_governorate_id'] = gid
            return redirect(url_for('home'))
        flash('المحافظة غير موجودة ضمن نطاق صلاحياتك.', 'error')
    return render_template('choose_governorate.html', governorates=allowed)

@app.route('/employees')
@operational_access
def employees():
    gov = selected_governorate()
    q = request.args.get('q','').strip()
    query = Employee.query.join(Branch).filter(Branch.governorate_id == gov.id, Employee.resignation_date.is_(None))
    if q: query = query.filter(db.or_(Employee.full_name.ilike(f'%{q}%'), Employee.hr_code.ilike(f'%{q}%')))
    return render_template('employees.html', employees=query.order_by(Employee.full_name).all(), q=q, branches=Branch.query.filter_by(governorate_id=gov.id).order_by(Branch.name).all())

@app.route('/employees/add', methods=['POST'])
@operational_access
def employee_add():
    gov = selected_governorate()
    try: branch_id = int(request.form.get('branch_id',''))
    except ValueError: branch_id = 0
    branch = Branch.query.filter_by(id=branch_id, governorate_id=gov.id).first()
    code = request.form.get('hr_code','').strip(); name = request.form.get('full_name','').strip()
    if not branch or not code or not name:
        flash('أكمل البيانات المطلوبة واختر فرعًا صحيحًا.', 'error')
    elif Employee.query.filter_by(hr_code=code).first(): flash('كود شئون العاملين مستخدم بالفعل.', 'error')
    else:
        db.session.add(Employee(hr_code=code, full_name=name, phone=request.form.get('phone','').strip(), job_title=request.form.get('job_title','').strip(), branch_id=branch.id))
        db.session.commit(); flash('تمت إضافة الموظف.', 'success')
    return redirect(url_for('employees'))

@app.route('/movements')
@operational_access
def movements():
    gov = selected_governorate()
    items = Movement.query.join(Employee).join(Branch).filter(Branch.governorate_id == gov.id).order_by(Movement.created_at.desc()).limit(300).all()
    employees = Employee.query.join(Branch).filter(Branch.governorate_id == gov.id, Employee.resignation_date.is_(None)).order_by(Employee.full_name).all()
    return render_template('movements.html', movements=items, employees=employees)

@app.route('/movements/add', methods=['POST'])
@operational_access
def movement_add():
    gov = selected_governorate(); user = current_user()
    try: employee_id = int(request.form.get('employee_id',''))
    except ValueError: employee_id = 0
    employee = Employee.query.join(Branch).filter(Employee.id == employee_id, Branch.governorate_id == gov.id, Employee.resignation_date.is_(None)).first()
    kind = request.form.get('kind','')
    try: start = date.fromisoformat(request.form.get('start_date',''))
    except ValueError: start = None
    try: end = date.fromisoformat(request.form.get('end_date','')) if request.form.get('end_date') else None
    except ValueError: end = None
    if not employee or kind not in MOVEMENT_TYPES or not start or (end and end < start):
        flash('راجع الموظف ونوع الحركة والتواريخ.', 'error')
    else:
        db.session.add(Movement(employee_id=employee.id, kind=kind, start_date=start, end_date=end,
            destination=request.form.get('destination','').strip(), notes=request.form.get('notes','').strip(), created_by=user.id))
        db.session.commit(); flash('تم تسجيل الحركة.', 'success')
    return redirect(url_for('movements'))

@app.route('/movements/<int:movement_id>/cancel', methods=['POST'])
@operational_access
def movement_cancel(movement_id):
    gov = selected_governorate()
    movement = Movement.query.join(Employee).join(Branch).filter(Movement.id == movement_id, Branch.governorate_id == gov.id).first_or_404()
    movement.active = False; db.session.commit(); flash('تم إلغاء الحركة مع الاحتفاظ بسجلها.', 'success')
    return redirect(url_for('movements'))

@app.route('/reports')
@operational_access
def reports():
    gov = selected_governorate()
    rows = Movement.query.join(Employee).join(Branch).filter(Branch.governorate_id == gov.id).order_by(Movement.start_date.desc()).limit(500).all()
    return render_template('reports.html', movements=rows)

@app.route('/delegations', methods=['GET','POST'])
@roles_required('supervisor','admin')
def delegations():
    user = current_user()
    if not selected_governorate(): return redirect(url_for('choose_governorate'))
    gov = selected_governorate()
    if request.method == 'POST':
        try:
            target_id = int(request.form.get('to_user_id','')); start = date.fromisoformat(request.form.get('start_date','')); end = date.fromisoformat(request.form.get('end_date',''))
            target = User.query.filter_by(id=target_id, role='supervisor', active=True).first()
            if not target or end < start: raise ValueError()
            db.session.add(Delegation(from_user_id=user.id,to_user_id=target.id,governorate_id=gov.id,start_date=start,end_date=end)); db.session.commit()
            flash('تم تسجيل التفويض.', 'success')
        except (ValueError, TypeError): flash('راجع المشرف والتواريخ.', 'error')
        return redirect(url_for('delegations'))
    records = Delegation.query.filter_by(from_user_id=user.id, governorate_id=gov.id).order_by(Delegation.start_date.desc()).all()
    supervisors = User.query.filter_by(role='supervisor', active=True).filter(User.id != user.id).order_by(User.full_name).all()
    return render_template('delegations.html', records=records, supervisors=supervisors)

@app.route('/admin')
@roles_required('admin')
def admin():
    return render_template('admin.html', users=User.query.order_by(User.full_name).all(), governorates=Governorate.query.order_by(Governorate.name).all(), branches=Branch.query.order_by(Branch.name).all())

@app.route('/admin/governorates/add', methods=['POST'])
@roles_required('admin')
def governorate_add():
    name = request.form.get('name','').strip()
    if name and not Governorate.query.filter_by(name=name).first():
        db.session.add(Governorate(name=name)); db.session.commit(); flash('تمت إضافة المحافظة.', 'success')
    else: flash('اسم المحافظة فارغ أو مسجل بالفعل.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/branches/add', methods=['POST'])
@roles_required('admin')
def branch_add():
    name = request.form.get('name','').strip(); code = request.form.get('code','').strip()
    try: gid = int(request.form.get('governorate_id',''))
    except ValueError: gid = 0
    gov = db.session.get(Governorate, gid)
    if name and gov and not Branch.query.filter_by(name=name, governorate_id=gid).first():
        db.session.add(Branch(name=name, code=code, governorate_id=gid)); db.session.commit(); flash('تمت إضافة الفرع.', 'success')
    else: flash('راجع اسم الفرع والمحافظة.', 'error')
    return redirect(url_for('admin'))

@app.route('/admin/users/add', methods=['POST'])
@roles_required('admin')
def user_add():
    username=request.form.get('username','').strip(); full_name=request.form.get('full_name','').strip(); password=request.form.get('password',''); role=request.form.get('role','')
    if not username or not full_name or len(password) < 12 or role not in ('admin','supervisor','manager_support'):
        flash('أكمل البيانات. كلمة المرور يجب ألا تقل عن 12 حرفًا.', 'error')
    elif User.query.filter_by(username=username).first(): flash('اسم المستخدم مستخدم بالفعل.', 'error')
    else:
        user=User(username=username,full_name=full_name,role=role); user.set_password(password); db.session.add(user); db.session.commit(); flash('تم إنشاء المستخدم.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/users/<int:user_id>/scopes', methods=['POST'])
@roles_required('admin')
def user_scopes_update(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return ('Not found', 404)
    if user.role == 'admin':
        flash('حساب Admin لا يحتاج إلى تعيين محافظات محددة.', 'info')
        return redirect(url_for('admin'))
    raw_ids = request.form.getlist('governorate_ids')
    try:
        requested_ids = {int(value) for value in raw_ids}
    except (TypeError, ValueError):
        flash('تعذر قراءة المحافظات المحددة.', 'error')
        return redirect(url_for('admin'))
    valid_ids = {row.id for row in Governorate.query.filter(Governorate.id.in_(requested_ids)).all()} if requested_ids else set()
    user.scopes[:] = [UserGovernorate(governorate_id=gid) for gid in sorted(valid_ids)]
    db.session.commit()
    flash('تم تحديث نطاق المحافظات للمستخدم.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/edit', methods=['POST'])
@roles_required('admin')
def user_edit(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return ('Not found', 404)
    full_name = request.form.get('full_name', '').strip()
    role = request.form.get('role', '').strip()
    new_password = request.form.get('new_password', '')
    if not full_name or role not in ('admin', 'supervisor', 'manager_support'):
        flash('راجع الاسم والدور المحدد.', 'error')
        return redirect(url_for('admin'))
    if user.id == current_user().id and role != 'admin':
        flash('لا يمكنك تغيير دور حساب Admin الذي تستخدمه حاليًا.', 'error')
        return redirect(url_for('admin'))
    if new_password and len(new_password) < 12:
        flash('كلمة المرور الجديدة يجب ألا تقل عن 12 حرفًا.', 'error')
        return redirect(url_for('admin'))
    if user.role == 'admin' and role != 'admin' and user.active:
        other_admins = User.query.filter_by(role='admin', active=True).filter(User.id != user.id).count()
        if other_admins == 0:
            flash('يجب الاحتفاظ بحساب Admin نشط واحد على الأقل.', 'error')
            return redirect(url_for('admin'))
    user.full_name = full_name
    user.role = role
    if new_password:
        user.set_password(new_password)
    if role == 'admin':
        user.scopes.clear()
    db.session.commit()
    flash('تم تحديث بيانات المستخدم وصلاحيات دوره.', 'success')
    return redirect(url_for('admin'))


@app.route('/admin/users/<int:user_id>/toggle', methods=['POST'])
@roles_required('admin')
def user_toggle(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return ('Not found', 404)
    if user.id == current_user().id:
        flash('لا يمكنك تعطيل حسابك الحالي.', 'error')
    elif user.active and user.role == 'admin' and User.query.filter_by(role='admin', active=True).count() <= 1:
        flash('لا يمكن تعطيل آخر حساب Admin نشط.', 'error')
    else:
        user.active = not user.active
        db.session.commit()
        flash('تم تحديث حالة المستخدم.', 'success')
    return redirect(url_for('admin'))

@app.route('/assistant', methods=['POST'])
@login_required
def assistant():
    # Safe foundation: no database mutations from natural-language input in this initial build.
    message=request.json.get('message','').strip() if request.is_json else request.form.get('message','').strip()
    if not message: return jsonify({'reply':'اكتب سؤالك أولًا.'}), 400
    if not os.getenv('GEMINI_API_KEY'):
        return jsonify({'reply':'بسيوني متاح كبنية أولية، لكن لم يتم ضبط GEMINI_API_KEY بعد. لن أنفّذ أي تغيير في البيانات من خلال المحادثة في هذا الإصدار.'})
    return jsonify({'reply':'تم استلام سؤالك. تكامل Gemini مع بيانات النظام وتنفيذ الإجراءات المقيّدة بالصلاحيات يحتاج إلى استكمال واختبار قبل تفعيله.'})

@app.errorhandler(404)
def not_found(_): return render_template('error.html', code=404, message='الصفحة غير موجودة'), 404
@app.errorhandler(500)
def server_error(_):
    db.session.rollback()
    return render_template('error.html', code=500, message='حدث خطأ غير متوقع. راجع سجلات تشغيل التطبيق.'), 500

with app.app_context():
    db.create_all()
    # Small additive migration for deployments that created the initial cyan schema before review support.
    user_columns = {column['name'] for column in inspect(db.engine).get_columns('user')}
    if 'is_review_account' not in user_columns:
        with db.engine.begin() as connection:
            connection.execute(text('ALTER TABLE "user" ADD COLUMN is_review_account BOOLEAN NOT NULL DEFAULT FALSE'))
    # First administrator: configure credentials as deployment secrets, never in source control.
    bootstrap_user = os.getenv('BOOTSTRAP_ADMIN_USERNAME', '').strip()
    bootstrap_pass = os.getenv('BOOTSTRAP_ADMIN_PASSWORD', '')
    if bool(bootstrap_user) != bool(bootstrap_pass):
        raise RuntimeError('Set both BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD, or leave both unset.')
    if bootstrap_user and bootstrap_pass:
        if len(bootstrap_pass) < 12:
            raise RuntimeError('BOOTSTRAP_ADMIN_PASSWORD must contain at least 12 characters.')
        existing_bootstrap = User.query.filter_by(username=bootstrap_user).first()
        if existing_bootstrap is None:
            admin_user = User(username=bootstrap_user, full_name='Admin', role='admin')
            admin_user.set_password(bootstrap_pass)
            db.session.add(admin_user)
            db.session.commit()
        elif existing_bootstrap.role != 'admin' and User.query.filter_by(role='admin', active=True).count() == 0:
            raise RuntimeError('BOOTSTRAP_ADMIN_USERNAME already belongs to a non-admin account; choose a new username or restore an active Admin account.')

    if APP_ENV == 'production' and User.query.filter_by(role='admin', active=True).count() == 0:
        raise RuntimeError('No active Admin account exists. Configure bootstrap credentials or restore an active Admin account before starting production.')

    # Temporary full-review account. It is created only when explicitly enabled.
    # The account receives the admin role for end-to-end review and must use a unique secret password.
    review_enabled = os.getenv('REVIEW_ACCOUNT_ENABLED', '0').strip() == '1'
    review_username = os.getenv('REVIEW_USERNAME', 'full_review_test').strip()
    review_password = os.getenv('REVIEW_PASSWORD', '')
    existing_review = User.query.filter_by(username=review_username).first() if review_username else None
    if review_enabled:
        if not review_username or len(review_password) < 16:
            raise RuntimeError('REVIEW_ACCOUNT_ENABLED=1 requires REVIEW_USERNAME and REVIEW_PASSWORD of at least 16 characters.')
        if existing_review and not existing_review.is_review_account:
            raise RuntimeError('REVIEW_USERNAME already belongs to a non-review account; choose a different username.')
        if not existing_review:
            existing_review = User(username=review_username, full_name='حساب المراجعة المؤقت', role='admin', is_review_account=True)
            existing_review.set_password(review_password)
            db.session.add(existing_review)
        else:
            existing_review.full_name = 'حساب المراجعة المؤقت'
            existing_review.role = 'admin'
            existing_review.active = True
            existing_review.set_password(review_password)
        db.session.commit()
    elif existing_review and existing_review.is_review_account:
        # Turning the feature off disables the review login without deleting its audit history.
        existing_review.active = False
        db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT','5000')), debug=False)
