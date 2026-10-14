"""Isolated SQLite runtime checks for the shared server-side entity matcher.

Loads only the search/matching modules with a tiny in-memory ORM schema, so the
query behavior can be exercised even in review environments without Flask.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

from sqlalchemy import ForeignKey, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

ROOT = Path(__file__).resolve().parents[1]
_PACKAGE = "_entity_matching_sql_runtime_v68_34_0"


def _load_matcher():
    if f"{_PACKAGE}.services.entity_matching" in sys.modules:
        return sys.modules[f"{_PACKAGE}.services.entity_matching"]

    package = types.ModuleType(_PACKAGE)
    package.__path__ = [str(ROOT / "employee_movements")]
    sys.modules[_PACKAGE] = package
    services = types.ModuleType(f"{_PACKAGE}.services")
    services.__path__ = [str(ROOT / "employee_movements" / "services")]
    sys.modules[services.__name__] = services

    for fullname, path in (
        (f"{_PACKAGE}.search", ROOT / "employee_movements" / "search.py"),
        (f"{_PACKAGE}.services.ticket_matching", ROOT / "employee_movements" / "services" / "ticket_matching.py"),
    ):
        spec = importlib.util.spec_from_file_location(fullname, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[fullname] = module
        spec.loader.exec_module(module)

    engine = create_engine("sqlite:///:memory:")
    session = Session(engine)
    extensions = types.ModuleType(f"{_PACKAGE}.extensions")
    extensions.db = types.SimpleNamespace(session=session)
    sys.modules[extensions.__name__] = extensions

    class Base(DeclarativeBase):
        pass

    class Governorate(Base):
        __tablename__ = "governorate"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String)

    class Branch(Base):
        __tablename__ = "branch"
        id: Mapped[int] = mapped_column(primary_key=True)
        name: Mapped[str] = mapped_column(String)
        code: Mapped[str] = mapped_column(String)
        governorate_id: Mapped[int] = mapped_column(ForeignKey("governorate.id"))
        governorate: Mapped[Governorate] = relationship()

    class Employee(Base):
        __tablename__ = "employee"
        id: Mapped[int] = mapped_column(primary_key=True)
        full_name: Mapped[str] = mapped_column(String)
        job_code: Mapped[str] = mapped_column(String)
        employee_code: Mapped[str | None] = mapped_column(String, nullable=True)
        job_title: Mapped[str] = mapped_column(String, default="")
        email: Mapped[str] = mapped_column(String, default="")
        company_phone: Mapped[str] = mapped_column(String, default="")
        personal_phone: Mapped[str] = mapped_column(String, default="")
        branch_id: Mapped[int] = mapped_column(ForeignKey("branch.id"))
        branch: Mapped[Branch] = relationship()

    class EmployeeNameAlias(Base):
        __tablename__ = "employee_name_alias"
        id: Mapped[int] = mapped_column(primary_key=True)
        employee_id: Mapped[int] = mapped_column()
        normalized_alias: Mapped[str] = mapped_column(String)

    class TicketEmployeeCodeAlias(Base):
        __tablename__ = "ticket_employee_code_alias"
        id: Mapped[int] = mapped_column(primary_key=True)
        employee_id: Mapped[int] = mapped_column()
        normalized_alias: Mapped[str] = mapped_column(String)

    class BranchNameAlias(Base):
        __tablename__ = "branch_name_alias"
        id: Mapped[int] = mapped_column(primary_key=True)
        branch_id: Mapped[int] = mapped_column()
        normalized_alias: Mapped[str] = mapped_column(String)

    class GovernorateNameAlias(Base):
        __tablename__ = "governorate_name_alias"
        id: Mapped[int] = mapped_column(primary_key=True)
        governorate_id: Mapped[int] = mapped_column()
        normalized_alias: Mapped[str] = mapped_column(String)

    models = types.ModuleType(f"{_PACKAGE}.models")
    for model in (Governorate, Branch, Employee, EmployeeNameAlias, TicketEmployeeCodeAlias, BranchNameAlias, GovernorateNameAlias):
        setattr(models, model.__name__, model)
    sys.modules[models.__name__] = models
    Base.metadata.create_all(engine)

    governorate = Governorate(name="الغربية")
    session.add(governorate)
    session.flush()
    short_code_branch = Branch(name="فرع 1234", code="1234", governorate=governorate)
    ordinary_branch = Branch(name="فرع عادي", code="8", governorate=governorate)
    session.add_all([short_code_branch, ordinary_branch])
    session.flush()
    session.add_all([
        Employee(full_name="مطابقة خاطئة جزئية", job_code="8123456", employee_code=None, branch=ordinary_branch),
        Employee(full_name="كود 123", job_code="123", employee_code=None, branch=ordinary_branch),
        Employee(full_name="كود بادئة 200", job_code="200123", employee_code=None, branch=ordinary_branch),
        Employee(full_name="موظف في فرع كوده 1234", job_code="9000", employee_code=None, branch=short_code_branch),
    ])
    session.commit()

    fullname = f"{_PACKAGE}.services.entity_matching"
    spec = importlib.util.spec_from_file_location(fullname, ROOT / "employee_movements" / "services" / "entity_matching.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[fullname] = module
    spec.loader.exec_module(module)
    module._contract_session = session
    module._contract_employee_model = Employee
    return module


def test_server_short_numeric_search_exact_matches_and_known_200_prefix_only():
    matcher = _load_matcher()
    session = matcher._contract_session
    Employee = matcher._contract_employee_model

    matches_123 = session.query(Employee).filter(matcher.employee_search_filter("123", include_branch=False)).all()
    assert {employee.job_code for employee in matches_123} == {"123", "200123"}
    assert "8123456" not in {employee.job_code for employee in matches_123}

    matches_1234 = session.query(Employee).filter(matcher.employee_search_filter("1234", include_branch=True)).all()
    assert {employee.id for employee in matches_1234} == {4}

    matches_arabic = session.query(Employee).filter(matcher.employee_search_filter("١٢٣", include_branch=False)).all()
    assert {employee.job_code for employee in matches_arabic} == {"123", "200123"}
