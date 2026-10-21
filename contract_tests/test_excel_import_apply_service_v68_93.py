"""Dependency-light tests for the separated Excel apply/validation service."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = ROOT / "employee_movements" / "services" / "excel_import_apply.py"
SPEC = importlib.util.spec_from_file_location("excel_import_apply_service_v6893", SERVICE_PATH)
assert SPEC and SPEC.loader
SERVICE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SERVICE
SPEC.loader.exec_module(SERVICE)


class _SelectionPlan:
    def __init__(self, *, adds=(), fields=None):
        self.adds = set(adds)
        self.fields = fields or {}

    def is_selected_add(self, action):
        return (action.get("type"), action.get("row")) in self.adds

    def selected_fields(self, action):
        return frozenset(self.fields.get(id(action), ()))


class _Session:
    def __init__(self, records=None):
        self.records = records or {}
        self.added = []
        self.flush_count = 0
        self.get_calls = []

    def add(self, record):
        self.added.append(record)

    def flush(self):
        self.flush_count += 1

    def get(self, model, record_id):
        self.get_calls.append((model, record_id))
        return self.records.get((model, record_id))


class _Branch:
    def __init__(self, **values):
        self.__dict__.update(values)


class _Employee:
    def __init__(self, **values):
        self.__dict__.update(values)


class _Governorate:
    pass


class _GovernorateAlias:
    pass


class _TicketAlias:
    pass


class _EmployeeNameAlias:
    pass


def _normal_key(value):
    return " ".join(str(value or "").casefold().split())


def _normal_code(value):
    return "".join(ch for ch in str(value or "").strip() if ch.isalnum())


def _variants(value):
    key = _normal_code(value)
    return {key} if key else set()


def test_apply_service_adds_branch_and_updates_only_selected_fields():
    existing = _Branch(id=9, name="فرع قديم", code="B-9")
    session = _Session({(_Branch, 9): existing})
    add_action = {
        "type": "new_branch", "row": 2, "governorate_id": 3,
        "values": {"name": "فرع جديد", "code": "B-10"},
    }
    update_action = {
        "type": "branch", "id": 9, "row": 3,
        "changes": {
            "name": {"old": "فرع قديم", "new": "فرع معدل"},
            "code": {"old": "B-9", "new": "B-99"},
        },
    }
    plan = _SelectionPlan(adds={("new_branch", 2)}, fields={id(update_action): {"name"}})
    result = SERVICE.apply_selected_excel_import_changes(
        "branches", [add_action, update_action], plan, 1,
        session=session, Governorate=_Governorate,
        GovernorateNameAlias=_GovernorateAlias, Branch=_Branch,
        Employee=_Employee, excel_key=_normal_key,
    )

    assert result.added == 1
    assert result.updated == 1
    assert result.skipped == 1
    assert len(session.added) == 1
    assert session.added[0].name == "فرع جديد"
    assert existing.name == "فرع معدل"
    assert existing.code == "B-9"
    assert session.flush_count == 1


def test_apply_service_creates_employee_with_normalized_optional_email_and_date():
    session = _Session()
    action = {
        "type": "new_employee", "row": 4, "branch_id": 12,
        "hire_date": "2024-02-29",
        "values": {
            "name": "موظف تجريبي", "email": "   ", "job_title": "محاسب",
            "job_code": "E-1", "company_phone": "123", "personal_phone": "456",
        },
    }
    plan = _SelectionPlan(adds={("new_employee", 4)})
    result = SERVICE.apply_selected_excel_import_changes(
        "employees", [action], plan, 0,
        session=session, Governorate=_Governorate,
        GovernorateNameAlias=_GovernorateAlias, Branch=_Branch,
        Employee=_Employee, excel_key=_normal_key,
    )

    assert (result.added, result.updated, result.skipped) == (1, 0, 0)
    assert session.added[0].email is None
    assert str(session.added[0].hire_date) == "2024-02-29"
    assert session.flush_count == 1


def test_validation_rejects_selected_employee_addition_with_missing_branch_before_writes():
    session = _Session()
    action = {
        "type": "new_employee", "row": 6, "branch_id": 41,
        "values": {"job_code": "E-41"},
    }
    plan = _SelectionPlan(adds={("new_employee", 6)})
    try:
        SERVICE.validate_selected_excel_import_changes(
            "employees", [action], [], plan,
            session=session, Branch=_Branch, Employee=_Employee,
            Governorate=_Governorate, TicketEmployeeCodeAlias=_TicketAlias,
            EmployeeNameAlias=_EmployeeNameAlias, excel_key=_normal_key,
            normalize_job_code=_normal_code, job_code_lookup_variants=_variants,
        )
    except ValueError as exc:
        assert "missing or inactive branch" in str(exc)
    else:
        raise AssertionError("Missing branch references must be rejected")
    assert session.get_calls == [(_Branch, 41)]
    assert not session.added


def test_validation_empty_selection_is_a_no_op_and_does_not_query_database():
    session = _Session()
    plan = _SelectionPlan()
    SERVICE.validate_selected_excel_import_changes(
        "employees", [], [], plan,
        session=session, Branch=_Branch, Employee=_Employee,
        Governorate=_Governorate, TicketEmployeeCodeAlias=_TicketAlias,
        EmployeeNameAlias=_EmployeeNameAlias, excel_key=_normal_key,
        normalize_job_code=_normal_code, job_code_lookup_variants=_variants,
    )
    assert session.get_calls == []
    assert session.added == []


def test_apply_service_rejects_unknown_kind_without_mutating_records():
    session = _Session()
    try:
        SERVICE.apply_selected_excel_import_changes(
            "unknown", [], _SelectionPlan(), 0,
            session=session, Governorate=_Governorate,
            GovernorateNameAlias=_GovernorateAlias, Branch=_Branch,
            Employee=_Employee, excel_key=_normal_key,
        )
    except ValueError as exc:
        assert "Unknown Excel import kind" in str(exc)
    else:
        raise AssertionError("Unknown import kinds must be rejected")
    assert not session.added


class _Column:
    def __set_name__(self, owner, name):
        self.name = name

    def __eq__(self, other):
        return (self, other)


class _GovernorateQuery:
    def __init__(self, all_rows, active_rows):
        self.all_rows = all_rows
        self.active_rows = active_rows
        self.entity = None
        self.active_only = False

    def filter_by(self, **kwargs):
        self.active_only = kwargs.get("is_active") is True
        return self

    def with_entities(self, entity):
        self.entity = entity
        return self

    def all(self):
        rows = self.active_rows if self.active_only else self.all_rows
        if self.entity is not None:
            return [(getattr(row, self.entity.name),) for row in rows]
        return rows


class _GovernorateAliasQuery:
    def __init__(self, aliases):
        self.aliases = aliases
        self.entity = None

    def with_entities(self, entity):
        self.entity = entity
        return self

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def __iter__(self):
        return iter((getattr(alias, self.entity.name),) for alias in self.aliases)


class _GovRecord:
    id = _Column()
    name = _Column()
    is_active = _Column()

    def __init__(self, id=None, name=None, is_active=True):
        self.id = id
        self.name = name
        self.is_active = is_active


class _GovAliasRecord:
    governorate_id = _Column()
    alias_text = _Column()

    def __init__(self, governorate_id, alias_text):
        self.governorate_id = governorate_id
        self.alias_text = alias_text


def test_apply_service_skips_existing_governorate_names_and_adds_new_ones():
    current = [_GovRecord(1, "القاهرة"), _GovRecord(2, "مؤرشفة", is_active=False)]
    _GovRecord.query = _GovernorateQuery(current, [current[0]])
    _GovAliasRecord.query = _GovernorateAliasQuery([_GovAliasRecord(1, "Cairo Alias")])
    session = _Session()
    actions = [
        {"type": "new_governorate", "row": 2, "values": {"name": "القاهرة"}},
        {"type": "new_governorate", "row": 3, "values": {"name": "Cairo Alias"}},
        {"type": "new_governorate", "row": 4, "values": {"name": "المنوفية"}},
    ]
    plan = _SelectionPlan(adds={("new_governorate", 2), ("new_governorate", 3), ("new_governorate", 4)})
    result = SERVICE.apply_selected_excel_import_changes(
        "governorates", actions, plan, 0,
        session=session, Governorate=_GovRecord,
        GovernorateNameAlias=_GovAliasRecord, Branch=_Branch,
        Employee=_Employee, excel_key=_normal_key,
    )

    assert (result.added, result.updated, result.skipped) == (1, 0, 2)
    assert len(session.added) == 1
    assert session.added[0].name == "المنوفية"
