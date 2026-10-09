from pathlib import Path


ROUTES = Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "employees.py"


def test_employee_lifecycle_dates_use_safe_form_parser():
    source = ROUTES.read_text(encoding="utf-8")
    assert "def _safe_parse_date(value):" in source
    assert "except (TypeError, ValueError):" in source
    assert "resignation_date = _safe_parse_date(raw_date)" in source
    assert "rehire_date = _safe_parse_date(raw_date)" in source


def test_employee_create_and_audit_share_one_commit():
    source = ROUTES.read_text(encoding="utf-8")
    add_start = source.index("            e = Employee(", source.index("def employees():"))
    add_end = source.index("            flash('تمت إضافة الموظف بنجاح.", add_start)
    add_path = source[add_start:add_end]
    assert "db.session.flush()" in add_path
    assert "log('ADD', 'Employee', e.id, e.full_name)" in add_path
    assert add_path.count("db.session.commit()") == 1
    assert add_path.index("log('ADD'") < add_path.index("db.session.commit()")


def test_employee_delete_checks_missing_record_before_permissions():
    source = ROUTES.read_text(encoding="utf-8")
    delete_start = source.index("def employee_delete(i):")
    delete_end = source.index("@bp.get('/employees/resigned')", delete_start)
    delete_path = source[delete_start:delete_end]
    assert delete_path.index("if not e:") < delete_path.index("can_manage_employee(e)")


def test_reactivated_employee_is_not_listed_as_currently_resigned():
    source = ROUTES.read_text(encoding="utf-8")
    resigned_start = source.index("def resigned_employees():")
    reactivate_start = source.index("def employee_reactivate(i):")
    card_start = source.index("@bp.get('/employee/<int:i>')", reactivate_start)
    resigned_path = source[resigned_start:reactivate_start]
    reactivate_path = source[reactivate_start:card_start]
    assert "Employee.is_active == False" in resigned_path
    assert "if e.is_active:" in reactivate_path
    assert "لا يحتاج إلى إعادة تعيين" in reactivate_path


def test_employee_email_and_hr_code_duplicates_are_case_insensitive():
    source = ROUTES.read_text(encoding="utf-8")
    assert "email = request.form.get('email', '').strip().lower()" in source
    assert "func.lower(Employee.email) == email" in source
    assert "func.lower(func.trim(Employee.job_code)) == job_code.lower()" in source
    assert "كود شئون العاملين مستخدم بالفعل لموظف آخر" in source


def test_resigned_employee_list_fails_closed_without_operational_scope():
    source = ROUTES.read_text(encoding="utf-8")
    resigned_start = source.index("def resigned_employees():")
    reactivate_start = source.index("def employee_reactivate(i):")
    resigned_path = source[resigned_start:reactivate_start]
    assert "q = q.filter(Employee.branch_id.in_(bs))" in resigned_path
    assert "if bs:" not in resigned_path


def test_employee_card_admin_bypass_respects_active_role():
    from pathlib import Path

    source = Path('employee_movements/blueprints/employees.py').read_text(encoding='utf-8')
    assert "'مسؤول التطبيق' not in roles(me()) and not branch_ok(e.branch_id)" in source
    assert "'مسؤول التطبيق' not in actual_roles(me()) and not branch_ok(e.branch_id)" not in source


def test_branch_delete_protects_organizational_entry_links():
    from pathlib import Path

    source = Path('employee_movements/blueprints/catalog.py').read_text(encoding='utf-8')
    assert 'EntryAssignmentBranch.query.filter_by(branch_id=i).count()' in source


def test_catalog_additions_commit_data_and_audit_together():
    from pathlib import Path

    source = Path('employee_movements/blueprints/catalog.py').read_text(encoding='utf-8')
    assert "log('ADD', 'Governorate', x.id, name)\n            db.session.commit()" in source
    assert "log('ADD', 'Branch', x.id, name)\n            db.session.commit()" in source
    assert "log('ADD', 'Lookup', x.id, name)\n            db.session.commit()" in source


def test_employee_edit_rejects_malformed_branch_id_without_unhandled_exception():
    source = ROUTES.read_text(encoding="utf-8")
    edit_start = source.index("def employee_edit(i):")
    convert_start = source.index("@bp.route('/employees/<int:i>/convert-role'", edit_start)
    edit_path = source[edit_start:convert_start]
    assert "request.form.get('branch_id')" in edit_path
    assert "if not raw_branch_id.isdigit():" in edit_path
    assert "int(request.form['branch_id'])" not in edit_path


def test_governorate_delete_protects_delegation_references():
    source = Path(__file__).resolve().parents[1] / "employee_movements" / "blueprints" / "catalog.py"
    text = source.read_text(encoding="utf-8")
    start = text.index("def governorate_delete(i):")
    end = text.index("@bp.route('/branches'", start)
    delete_path = text[start:end]
    assert "Branch.query.filter_by(governorate_id=i).count()" in delete_path
    assert "UserGovernorate.query.filter_by(governorate_id=i).count()" in delete_path
    assert "ApprovalDelegation.query.filter_by(governorate_id=i).count()" in delete_path
    assert "استخدم التعطيل" in delete_path


def test_branch_code_must_be_unique_within_governorate_on_create_and_edit():
    from pathlib import Path

    source = Path('employee_movements/blueprints/catalog.py').read_text(encoding='utf-8')
    assert "func.lower(func.trim(Branch.code)) == code.lower()" in source
    assert "كود الفرع مستخدم بالفعل في هذه المحافظة." in source
    assert "Branch.id != i" in source
