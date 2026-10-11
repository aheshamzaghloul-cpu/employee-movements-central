from pathlib import Path


def test_mission_reopen_requires_manager_or_application_admin():
    source = (
        Path(__file__).resolve().parents[1]
        / "employee_movements" / "blueprints" / "missions.py"
    ).read_text(encoding="utf-8")
    start = source.index("def mission_reopen(")
    end = source.find("@bp.", start)
    block = source[start:end if end >= 0 else len(source)]
    assert "if not ({'مسؤول التطبيق', 'Manager Application Support'} & roles()):" in block
    assert "abort(403)" in block
