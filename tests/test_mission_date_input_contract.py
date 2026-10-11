from pathlib import Path


def test_mission_date_routes_use_safe_parser_and_handle_invalid_input():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
    assert "def _safe_mission_date(value):" in source
    assert "fd = _safe_mission_date(raw_fd)" in source
    assert "td = _safe_mission_date(raw_td)" in source
    assert "print_to_date = _safe_mission_date(raw_print_to_date)" in source
    assert "if (raw_fd and fd is None) or (raw_td and td is None):" in source
    assert "تاريخ البداية أو النهاية غير صحيح" in source
    assert "تاريخ «إلى» صحيحًا للطباعة" in source

def test_mission_edit_request_review_rejects_malformed_dates_before_execution():
    source = (Path(__file__).parents[1] / "employee_movements" / "blueprints" / "missions.py").read_text(encoding="utf-8")
    start = source.index("def mission_edit_request_save(")
    end = source.index("@bp.get('/reports/assignments/export.xlsx')", start)
    route = source[start:end]
    guard = "if (raw_fd and fd is None) or (raw_td and td is None):"
    assert "fd = _safe_mission_date(raw_fd)" in route
    assert "td = _safe_mission_date(raw_td)" in route
    assert guard in route
    assert route.index(guard) < route.index("validate_and_execute_mission_edit_request(")
    assert "mission_edit_request_review" in route

