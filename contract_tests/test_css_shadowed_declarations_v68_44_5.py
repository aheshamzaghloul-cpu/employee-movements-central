from pathlib import Path

from scripts.cleanup_shadowed_declarations_v68_44_5 import plan_content


def _plan(css):
    return plan_content(css, Path("sample.css"))


def test_removes_only_earlier_same_selector_and_context_declaration():
    result, notes = _plan(".x { color: red; padding: 4px; }\n.x { color: blue; }\n")
    assert "color: red" not in result
    assert "padding: 4px" in result
    assert "color: blue" in result
    assert len(notes) == 1


def test_preserves_duplicate_property_fallbacks_inside_same_rule():
    source = ".x { display: -webkit-box; display: flex; }\n.x { display: grid; }\n"
    result, notes = _plan(source)
    assert result == source
    assert notes == []


def test_does_not_cross_media_contexts():
    source = ".x { color: red; }\n@media (max-width: 600px) { .x { color: blue; } }\n"
    result, notes = _plan(source)
    assert result == source
    assert notes == []


def test_respects_important_priority():
    source = ".x { color: red !important; }\n.x { color: blue; }\n"
    result, notes = _plan(source)
    assert result == source
    assert notes == []
    result, notes = _plan(".x { color: red !important; }\n.x { color: blue !important; }\n")
    assert "color: red !important" not in result
    assert "color: blue !important" in result
    assert len(notes) == 1


def test_custom_property_names_remain_case_sensitive():
    source = ".x { --Brand: red; }\n.x { --brand: blue; }\n"
    result, notes = _plan(source)
    assert result == source
    assert notes == []


def test_comments_protect_their_declaration_block():
    source = ".x { /* preserve this note */ color: red; }\n.x { color: blue; }\n"
    result, notes = _plan(source)
    assert result == source
    assert notes == []


def test_grouped_selectors_are_not_modified():
    source = ".x, .y { color: red; }\n.x { color: blue; }\n"
    result, notes = _plan(source)
    assert result == source
    assert notes == []


def test_legacy_shadowing_audit_helper_does_not_treat_fallbacks_as_overrides():
    from trim_shadowed_declarations import plan as legacy_plan

    path = Path(__file__).resolve().parents[1] / "employee_movements/static/css/test-sample.css"
    source = ".x { display: -webkit-box; display: flex; }\n.x { display: grid; }\n"
    edits, count, notes = legacy_plan(source, path)
    assert edits == []
    assert count == 0
    assert notes == []


def test_legacy_shadowing_helper_can_remove_other_props_without_touching_fallbacks():
    from trim_shadowed_declarations import plan as legacy_plan

    path = Path(__file__).resolve().parents[1] / "employee_movements/static/css/test-sample.css"
    source = ".x { color: red; display: -webkit-box; display: flex; }\n.x { color: blue; }\n"
    edits, count, notes = legacy_plan(source, path)
    assert count == 1
    assert len(edits) == 1
    assert "color" in notes[0]
    assert "display" not in notes[0]
