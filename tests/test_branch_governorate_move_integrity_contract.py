from pathlib import Path


def test_branch_parent_change_is_blocked_when_records_reference_branch():
    source = Path("employee_movements/blueprints/catalog.py").read_text(encoding="utf-8")
    start = source.index("@bp.post('/branches/<int:i>/edit')")
    end = source.index("@bp.post('/branches/<int:i>/toggle')", start)
    route = source[start:end]
    assert "if x.governorate_id != g.id" in route
    assert "Employee.query.filter_by(branch_id=i).count()" in route
    assert "UserBranch.query.filter_by(branch_id=i).count()" in route
    assert "EntryAssignmentBranch.query.filter_by(branch_id=i).count()" in route
    assert "Movement.query.filter_by(branch_id=i).count()" in route
    assert "Movement.query.filter_by(destination_branch_id=i).count()" in route
    assert "return redirect('/branches')" in route
    assert "عالج الارتباطات أولًا" in route
