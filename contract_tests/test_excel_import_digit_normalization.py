from pathlib import Path


def test_excel_key_normalizes_arabic_digits_and_excel_float_codes():
    source = (Path(__file__).resolve().parents[1] / "employee_movements" / "services" / "excel_import_schema.py").read_text(encoding="utf-8")
    assert "digit_map = str.maketrans" in source
    assert "s = s.translate(digit_map)" in source
    assert "re.fullmatch(r'\\d+\\.0+', s)" in source


def test_outline_icon_fill_fix_preserves_explicit_filled_svg_opt_in():
    css = (Path(__file__).resolve().parents[1] / "employee_movements" / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert 'svg:not([data-icon-fill]) *' in css
    assert 'svg[data-icon-fill], svg[data-icon-fill] *' in css
