"""Contracts and pure matching tests for robust ticket-code/branch resolution."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
MODELS = (ROOT / "employee_movements" / "models.py").read_text(encoding="utf-8")
ROUTES = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
RESOLUTION = (ROOT / "employee_movements" / "services" / "mission_ticket_resolution.py").read_text(encoding="utf-8")
PAGE = (ROOT / "employee_movements" / "templates" / "mission_from_screenshot.html").read_text(encoding="utf-8")
BOOTSTRAP = (ROOT / "employee_movements" / "bootstrap.py").read_text(encoding="utf-8")
PRIVACY = (ROOT / "employee_movements" / "assistant" / "privacy.py").read_text(encoding="utf-8")


def _load_ticket_matching_module():
    """Load the pure matching service without importing Flask application startup."""
    package_name = "_ticket_matching_contract_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(ROOT / "employee_movements")]
    sys.modules[package_name] = package

    search_spec = importlib.util.spec_from_file_location(
        f"{package_name}.search", ROOT / "employee_movements" / "search.py"
    )
    search_module = importlib.util.module_from_spec(search_spec)
    sys.modules[search_spec.name] = search_module
    search_spec.loader.exec_module(search_module)

    services = types.ModuleType(f"{package_name}.services")
    services.__path__ = [str(ROOT / "employee_movements" / "services")]
    sys.modules[services.__name__] = services

    matching_spec = importlib.util.spec_from_file_location(
        f"{package_name}.services.ticket_matching",
        ROOT / "employee_movements" / "services" / "ticket_matching.py",
    )
    matching_module = importlib.util.module_from_spec(matching_spec)
    sys.modules[matching_spec.name] = matching_module
    matching_spec.loader.exec_module(matching_module)
    return matching_module


MATCHING = _load_ticket_matching_module()


def test_code_normalization_accepts_arabic_digits_and_common_ocr_confusions():
    assert MATCHING.normalize_job_code("٢٠٠٢٠٣٥٣") == "20020353"
    assert MATCHING.normalize_job_code("2002O353") == "20020353"
    assert MATCHING.normalize_job_code(" 200-20353 ") == "20020353"


def test_prefix_variants_are_generated_only_for_numeric_codes():
    assert MATCHING.job_code_lookup_variants("20353") == {"20353", "20020353"}
    assert MATCHING.job_code_lookup_variants("20020353") == {"20020353", "20353"}
    assert MATCHING.job_code_lookup_variants("EMP20353") == {"emp20353"}


def test_branch_code_inside_ocr_text_is_an_exact_match_only_when_unique():
    unique = [{"id": 36, "code": "369", "name": "مشلة", "label": "369 · مشلة · الغربية", "aliases": []}]
    matched = MATCHING.branch_exact_match("369 - مشله - الغربية", unique)
    assert [item["id"] for item in matched] == [36]

    duplicate = unique + [{"id": 37, "code": "369", "name": "مشلة أخرى", "label": "369 · مشلة أخرى · محافظة أخرى", "aliases": []}]
    matched = MATCHING.branch_exact_match("369 - مشله - الغربية", duplicate)
    assert {item["id"] for item in matched} == {36, 37}


def test_candidate_ranker_can_use_confirmed_code_alias_and_basic_branch_as_evidence():
    branch = SimpleNamespace(name="كفر الزيات أول", governorate=SimpleNamespace(name="الغربية"))
    employee = SimpleNamespace(id=17, job_code="20020353", full_name="موظف تجريبي", branch=branch)
    ranked = MATCHING.rank_employee_code_candidates(
        "20020358", [employee], "كفرالزيات اول", aliases_by_employee={17: ["20020358"]}
    )
    assert len(ranked) == 1
    assert ranked[0]["employee"].id == 17
    assert ranked[0]["code_score"] == 1.0
    assert ranked[0]["branch_score"] > 0.8


def test_near_branch_match_is_only_ranked_for_manual_confirmation():
    candidates = [
        {"id": 1, "name": "الغربية - مشلة", "label": "الغربية - مشلة · الغربية", "aliases": []},
        {"id": 2, "name": "الغربية - كفر الزيات", "label": "الغربية - كفر الزيات · الغربية", "aliases": []},
    ]
    ranked = MATCHING.rank_branch_candidates("الغربيه مشله", candidates)
    assert ranked
    assert ranked[0]["id"] == 1
    assert ranked[0]["match_score"] < 1.0 or MATCHING.normalize_entity_name("الغربيه مشله") == MATCHING.normalize_entity_name(ranked[0]["name"])


def test_employee_code_alias_model_is_global_unique_and_cascades_with_employee():
    model = MODELS.split("class TicketEmployeeCodeAlias(db.Model):", 1)[1].split("class BranchNameAlias(db.Model):", 1)[0]
    assert "UniqueConstraint('normalized_alias', name='uq_ticket_employee_code_alias_normalized')" in model
    assert "db.ForeignKey('employee.id', ondelete='CASCADE')" in model
    assert "normalized_alias = db.Column(db.String(100), nullable=False, index=True)" in model
    assert "TicketEmployeeCodeAlias" in BOOTSTRAP


def test_database_backed_resolution_is_in_a_service_not_the_http_blueprint():
    assert "from ..services.mission_ticket_resolution import (" in ROUTES
    assert "def _ticket_mission_employee(job_code):" in RESOLUTION
    assert "def _ticket_mission_branch_choices(value, branches):" in RESOLUTION
    assert "def _ticket_mission_save_branch_alias(raw_name, branch, creator_id):" in RESOLUTION
    assert "from ..blueprints.missions import" not in RESOLUTION


def test_lookup_checks_all_direct_and_alias_candidates_before_auto_selecting():
    resolver = RESOLUTION.split("def _ticket_mission_employee(job_code):", 1)[1].split("def _ticket_mission_employee_suggestions", 1)[0]
    assert "official_rows" in resolver
    assert "alias_rows" in resolver
    assert "candidates_by_id" in resolver
    assert "if len(candidates_by_id) > 1" in resolver
    assert "_ticket_job_code_sql(Employee.job_code).in_(variants)" in resolver
    assert "لم نختَر أحدًا تلقائيًا" in resolver


def test_code_alias_is_saved_only_after_explicit_opt_in_and_after_mission_validation():
    route = ROUTES.split("def mission_from_screenshot_create():", 1)[1].split("@bp.get('/reports/assignments/mission-edit", 1)[0]
    assert "if form.get('remember_job_code_alias') == 'yes' and source_job_code and not expected_employee_confirmation_needed:" in route
    assert "if form.get('remember_basic_branch_alias') == 'yes' and actual_basic_branch:" in route
    assert "_ticket_mission_save_job_code_alias(" in route
    assert route.index("movement = Movement(") < route.index("_ticket_mission_save_job_code_alias(") < route.rindex("db.session.commit()")
    save = RESOLUTION.split("def _ticket_mission_save_job_code_alias(", 1)[1].split("def _ticket_mission_branch_records", 1)[0]
    assert "job_code_lookup_variants(official_code)" in save
    assert "conflicting_official" in save
    assert "existing.employee_id != employee.id" in save
    assert "with db.session.begin_nested()" in save


def test_ticket_review_preserves_raw_ocr_code_but_only_shows_requested_fields():
    assert 'name="source_job_code"' in PAGE
    assert 'name="remember_job_code_alias" value="yes"' in PAGE
    assert 'name="remember_basic_branch_alias" value="yes"' in PAGE
    assert 'name="remember_branch_alias" value="yes"' in PAGE
    for field in (
        'name="basic_branch_name"', 'name="destination_branch_id"', 'name="job_code"',
        'name="destination_is_basic"', 'name="needs_mission"', 'name="from_date"', 'name="to_date"',
    ):
        assert field in PAGE


def test_learned_alternate_job_codes_are_included_in_local_external_model_privacy_screening():
    assert "TicketEmployeeCodeAlias" in PRIVACY
    assert "TicketEmployeeCodeAlias.normalized_alias.in_(normalized_identifiers)" in PRIVACY
    assert "job_code_lookup_variants(observed_identifier) & matched_alias_values" in PRIVACY
    assert "values.add(observed_identifier)" in PRIVACY
