import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACCESS = (ROOT / "employee_movements/access.py").read_text(encoding="utf-8")
MOVEMENTS = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
HOME = (ROOT / "employee_movements/templates/home.html").read_text(encoding="utf-8")
HOME_CSS = (ROOT / "employee_movements/static/css/pages/home.css").read_text(encoding="utf-8")
DIRECTORY = (ROOT / "employee_movements/assistant/directory.py").read_text(encoding="utf-8")
ASSISTANT = (ROOT / "employee_movements/assistant/routes.py").read_text(encoding="utf-8")
MODELS = (ROOT / "employee_movements/models.py").read_text(encoding="utf-8")
PRIVACY = (ROOT / "employee_movements/assistant/privacy.py").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "employee_movements/bootstrap.py").read_text(encoding="utf-8")


def test_single_governorate_supervisor_scope_is_selected_automatically():
    scope = ACCESS.split("def scope_governorate_id():", 1)[1].split("def scope_governorates_for_user", 1)[0]
    assert "current_scope_role == 'مشرف محافظة' and len(allowed_ids) == 1" in scope
    assert "session['operational_governorate_id'] = selected" in scope
    assert "selected_int in allowed_ids" in scope


def test_admin_and_manager_do_not_receive_an_implicit_work_governorate():
    scope = ACCESS.split("def scope_governorate_id():", 1)[1].split("def scope_governorates_for_user", 1)[0]
    assert "current_scope_role == 'مشرف محافظة'" in scope
    assert "Admin and Manager always make an explicit work-scope choice" in scope


def test_movement_picker_asks_for_type_first_and_loads_allowed_initial_branches():
    assert "scope_selected|int == g.id" in MOVEMENTS
    assert 'id="movementCreateType" name="movement_type" required' in MOVEMENTS
    assert 'id="movementGovernorateStep" hidden' in MOVEMENTS
    assert "movement_type:type.value" in MOVEMENTS
    assert "movement_global_picker_allowed" in (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    assert "if(type?.value){" in MOVEMENTS
    assert "initialEmployeeId={{ initial_employee.id if initial_employee else 'null' }}" in MOVEMENTS
    assert "loadCreateBranches().then(async()=>" in MOVEMENTS
    assert "setProgress(govCreate?.value?2:1)" in MOVEMENTS
    assert 'id="movementBranchSearch"' in MOVEMENTS and 'id="movementEmployeeSearch"' in MOVEMENTS
    assert 'PICKER_INITIAL_COUNT=8' in MOVEMENTS


def test_movement_picker_checks_api_response_and_uses_selected_employee_id():
    assert "if(!r.ok)throw new Error('employee_picker_failed')" in MOVEMENTS
    assert "Array.isArray(data.employees)?data.employees:[]" in MOVEMENTS
    assert "button.addEventListener('click',()=>selectCreateEmployee(e,activePickerBranch,button))" in MOVEMENTS
    assert "employeeId.value=e.id; detailsStep.hidden=false; selectedEmployee.innerHTML=''" in MOVEMENTS


def test_home_movement_action_preserves_selected_employee_for_manual_entry():
    assert HOME.index('id="homeEmployeeSearchTitle"') < HOME.index('id="homeManualMissionTitle"')
    assert "url_for('movements.movements', movement_type='انتداب'" in HOME
    assert "return_to=url_for('dashboard.home'" in HOME
    assert 'id="movement-create"' in MOVEMENTS
    assert 'id="homeChooseEmployeeAction"' not in HOME
    assert "employeeSearchSection?.scrollIntoView" not in HOME


def test_first_entry_branches_expand_and_employee_rows_link_to_employee_profiles():
    assert 'class="smart-entry-branch"' in HOME
    assert 'class="smart-entry-employee-list"' in HOME
    assert 'data-entry-employee-search' in HOME
    assert 'data-entry-employee-item' in HOME
    assert 'data-entry-employee-more' in HOME
    assert 'href="/employee/{{emp.id}}"' in HOME
    assert "smart-entry-branch > summary" in HOME_CSS
    assert ".smart-entry-employee:focus-visible" in HOME_CSS


def test_assistant_directory_search_folds_arabic_name_variants_in_sql():
    assert "def _sql_arabic_fold(column):" in DIRECTORY
    assert "('أ', 'ا')" in DIRECTORY and "('إ', 'ا')" in DIRECTORY
    assert "employee_search_filter(value, include_job_title=True, include_branch=True)" in DIRECTORY
    matching = (ROOT / "employee_movements/services/entity_matching.py").read_text(encoding="utf-8")
    assert "EmployeeNameAlias" in matching and "TicketEmployeeCodeAlias" in matching


def test_assistant_learns_name_links_locally_and_does_not_reassign_conflicting_aliases():
    assert "class AssistantAlias(db.Model):" in MODELS
    assert "UniqueConstraint('user_id', 'normalized_alias'" in MODELS
    assert "def _try_learn_employee_alias(prompt):" in ASSISTANT
    assert "alias_learning = _try_learn_employee_alias(prompt)" in ASSISTANT
    assert "if existing and existing.employee_id != employee.id" in ASSISTANT
    bootstrap_tree = ast.parse(BOOTSTRAP)
    model_imports = {
        alias.name
        for node in bootstrap_tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "models"
        for alias in node.names
    }
    assert {"AssistantAlias", "TicketEmployeeCodeAlias"}.issubset(model_imports)


def test_learned_alias_text_is_part_of_local_privacy_screening():
    assert "BranchNameAlias" in PRIVACY and "EmployeeNameAlias" in PRIVACY
    assert "GovernorateNameAlias" in PRIVACY and "TicketEmployeeCodeAlias" in PRIVACY
    assert "remembered_aliases = (" in PRIVACY
    assert "Local alias privacy screening could not complete; external processing blocked." in PRIVACY


def test_equivalent_arabic_spellings_are_handled_before_employee_lookup():
    learning = ASSISTANT.split("def _try_learn_employee_alias(prompt):", 1)[1].split("def answer_prompt", 1)[0]
    spelling_check = learning.index("if normalize_for_search(left) == normalize_for_search(right):")
    first_lookup = learning.index("left_employee, left_matches = find_employee(left)")
    assert spelling_check < first_lookup
    assert "لن أحتاج إلى حفظهما كموظفين منفصلين" not in learning
    assert "لن أحتاج" not in learning[spelling_check:first_lookup]


def test_all_templates_parse_after_first_entry_branch_expansion():
    import jinja2
    env = jinja2.Environment()
    templates = list((ROOT / "employee_movements/templates").rglob("*.html"))
    assert len(templates) == 45
    for path in templates:
        env.parse(path.read_text(encoding="utf-8"))
