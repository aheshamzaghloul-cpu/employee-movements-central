"""Regression tests for ServiceDesk screenshot mission decision rules."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "employee_movements" / "services" / "ticket_mission_rules.py"
spec = spec_from_file_location("ticket_mission_rules", RULES_PATH)
assert spec and spec.loader
rules = module_from_spec(spec)
spec.loader.exec_module(rules)


def test_create_mission_only_when_destination_is_not_basic_and_mission_is_needed():
    assert rules.should_create_mission("no", "yes") is True
    assert rules.should_create_mission("yes", "yes") is False
    assert rules.should_create_mission("no", "no") is False
    assert rules.should_create_mission("yes", "no") is False
    assert rules.should_create_mission("", "yes") is False
    assert rules.should_create_mission("no", "") is False
    assert rules.should_create_mission(" NO ", " YES ") is True


def test_route_uses_the_explicit_decision_rule_and_reverses_old_branch_match_guard():
    source = (ROOT / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
    section = source.split("def mission_from_screenshot_create():", 1)[1].split("@bp.get('/reports/assignments/mission-edit/", 1)[0]
    assert "should_create_mission(fields.get('destination_is_basic'), fields.get('needs_mission'))" in section
    assert "destination_is_basic" in section and "ليس فرعي الأساسي" in section
    assert "basic_branch_alias_match = _ticket_mission_basic_branch_alias_matches(" in section
    assert "not basic_branch_alias_match and branch_name_score < 0.52" in section
    assert "اسم الفرع الأساسي في الصورة لا يطابق سجل الموظف بما يكفي" in section
    assert "if destination.id == employee.branch_id:" in section
    assert "لا يجوز أن يسبق «من يوم»" in section


def test_ticket_form_explains_the_correct_answers():
    template = (ROOT / "employee_movements" / "templates" / "mission_from_screenshot.html").read_text(encoding="utf-8")
    assert "لا، ليس فرعي الأساسي" in template
    assert "إجابة «هل تحتاج مأمورية؟» هي «نعم»" in template
