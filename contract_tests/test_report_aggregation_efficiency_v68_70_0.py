from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "employee_movements" / "blueprints" / "reports.py"


def test_manager_hub_uses_grouped_aggregates_instead_of_per_governorate_count_queries():
    source = REPORTS.read_text(encoding="utf-8")
    manager = source[source.index("def manager_hub():"):source.index("@bp.get('/audit')")]
    assert "group_by(Branch.governorate_id)" in manager
    assert "employee_counts = dict(" in manager
    assert "movement_counts = {" in manager
    assert "employee_q.count()" not in manager
    assert "movement_q.filter(Movement.movement_type == 'إجازة').count()" not in manager
    assert "Governorate.is_active == True" in manager


def test_global_mission_report_stats_use_a_single_conditional_aggregate():
    source = REPORTS.read_text(encoding="utf-8")
    report = source[source.index("def reports_missions():"):source.index("@bp.get('/reports')")]
    assert "aggregate_row = movement_q.order_by(None).with_entities(" in report
    assert "func.coalesce(func.sum(case((today_condition, 1), else_=0)), 0)" in report
    assert "func.coalesce(func.sum(case((month_condition, 1), else_=0)), 0)" in report
    assert "movement_q.count()" not in report
    assert "movement_q.filter(" not in report


def test_general_report_status_and_type_summaries_are_grouped_and_keep_zero_values():
    source = REPORTS.read_text(encoding="utf-8")
    report = source[source.index("def reports():"):source.index("@bp.get('/reports/<report_type>')")]
    assert "summary = {status_value: 0 for status_value in STATUSES}" in report
    assert "group_by(Movement.status).all()" in report
    assert "by_type = {movement_type_value: 0 for movement_type_value in MOVEMENT_TYPES}" in report
    assert "group_by(Movement.movement_type).all()" in report


def test_manager_hub_pending_requests_preload_template_relationships():
    source = REPORTS.read_text(encoding="utf-8")
    manager = source[source.index("def manager_hub():"):source.index("@bp.get('/audit')")]
    assert "joinedload(MissionEditRequest.requester)" in manager
    assert "joinedload(MissionEditRequest.movement).joinedload(Movement.employee)" in manager
