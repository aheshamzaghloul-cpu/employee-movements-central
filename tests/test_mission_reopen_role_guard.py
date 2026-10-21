from pathlib import Path


def test_direct_mission_reopen_is_disabled_and_uses_manager_review_workflow():
    source = (
        Path(__file__).resolve().parents[1]
        / "employee_movements" / "blueprints" / "missions.py"
    ).read_text(encoding="utf-8")
    start = source.index("def mission_reopen(")
    end = source.find("@bp.", start)
    block = source[start:end if end >= 0 else len(source)]
    assert 'لا يمكن إعادة فتح المأمورية مباشرة' in block
    assert 'طلب تعديل ليعتمده الـManager' in block
    assert 'reopen_mission(m)' not in block
