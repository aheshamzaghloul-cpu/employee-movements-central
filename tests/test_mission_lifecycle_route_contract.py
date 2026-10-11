from pathlib import Path


def test_mission_close_revalidates_dates_and_overlap_before_mutation():
    source = (Path(__file__).parents[1] / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    close = source.split("def mission_close(", 1)[1].split("@bp.post('/reports/assignments/mission-reopen", 1)[0]
    assert "if not m.from_date or not m.to_date" in close
    assert "if m.to_date < m.from_date" in close
    assert "movement_overlaps(" in close
    assert close.index("movement_overlaps(") < close.index("close_mission(m)")


def test_mission_reopen_checks_open_ended_overlap_before_mutation():
    source = (Path(__file__).parents[1] / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
    reopen = source.split("def mission_reopen(", 1)[1].split("@bp.get('/reports/assignments/mission-print-date", 1)[0]
    assert "if not m.from_date" in reopen
    assert "movement_overlaps(" in reopen
    assert "m.from_date, None, None, m.id" in reopen
    assert reopen.index("movement_overlaps(") < reopen.index("reopen_mission(m)")
