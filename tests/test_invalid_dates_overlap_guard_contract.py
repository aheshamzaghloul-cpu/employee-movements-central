from pathlib import Path


def test_overlap_helper_converts_invalid_dates_to_validation_message():
    source = (Path(__file__).parents[1] / "employee_movements" / "validation.py").read_text(encoding="utf-8")
    start = source.index("def movement_overlaps(")
    end = source.index("\n\ndef validate_movement_fields", start)
    body = source[start:end]

    assert "try:" in body
    assert "except ValueError:" in body
    assert "return 'التاريخ غير صحيح.'" in body



def test_field_validation_parses_calendar_dates_and_compares_date_values():
    source = (Path(__file__).parents[1] / "employee_movements" / "validation.py").read_text(encoding="utf-8")
    start = source.index("def validate_movement_fields(")
    end = source.index("\n\ndef parse_optional_iso_date", start)
    body = source[start:end]

    assert "parsed_start = parse_date_value(fd)" in body
    assert "parsed_end = parse_date_value(td)" in body
    assert "except ValueError:" in body
    assert "return 'التاريخ غير صحيح.'" in body
    assert "parsed_start > parsed_end" in body
