from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSISTANT = ROOT / "employee_movements" / "assistant"


def read(name):
    return (ASSISTANT / name).read_text(encoding="utf-8")


def test_read_only_tools_are_separated_from_agent_orchestration():
    agent = read("agent.py")
    reads = read("tool_read_handlers.py")
    dispatch = read("tool_dispatch.py")
    preparation = read("action_preparation.py")
    assert "from .tool_read_handlers import execute_read_tool" in dispatch
    for name in ("search_employees", "get_employee_profile", "search_branches", "search_governorates", "search_movements"):
        assert f'if name == "{name}":' in reads
    assert 'if name == "prepare_action":' in dispatch
    assert 'if name == "prepare_action":' not in reads
    assert "def prepare_action(args, ctx):" in preparation
    assert "def _prepare_action(args, ctx):" in agent  # backward-compatible wrapper
    assert "db.session.commit()" not in reads + dispatch + preparation


def test_manager_execution_service_has_no_commit_boundary_and_rechecks_admin():
    manager = read("manager.py")
    service = read("manager_execution.py")
    planner = read("manager_planning.py")
    assert "from .manager_execution import execute_plan as _execute_plan" in manager
    assert "from .manager_planning import build_plan as _build_plan" in manager
    assert "def plan(a):" in manager
    assert "def build_plan(a):" in planner
    assert "if not is_app_manager():" in planner
    assert "db.session.commit()" in manager[manager.index("def execute(plan):"):manager.index("def _execute(plan):")]
    assert "if not is_app_manager():" in service
    assert "db.session.commit()" not in service


def test_admin_user_creation_inserts_each_role_once():
    service = read("manager_execution.py")
    start = service.index("elif kind == 'user_create':")
    end = service.index("elif kind == 'user_toggle':", start)
    block = service[start:end]
    assert block.count("db.session.add(UserRole(user_id=u.id, role=role))") == 1
    assert "for perm in ROLE_DEFAULT_PERMISSIONS.get(role, set()):" in block


def test_manager_confirmation_planning_is_split_by_business_domain():
    planner = read("manager_planning.py")
    people = read("manager_plan_people.py")
    users = read("manager_plan_users.py")
    structure = read("manager_plan_structure.py")
    movements = read("manager_plan_movements.py")
    assert "if not is_app_manager():" in planner
    assert "return plan_user_action(a, intent)" in planner
    assert "return plan_employee_action(a, intent)" in planner
    assert "return plan_governorate_action(a, intent)" in planner
    assert "return plan_movement_action(a, intent)" in planner
    assert "def plan_entry_action(a, intent):" in people
    assert "def plan_role_action(a, intent):" in users
    assert "def plan_lookup_action(a, intent):" in structure
    assert "resolve_movement_for_employee" in movements
    assert "db.session.commit()" not in planner + people + users + structure + movements
