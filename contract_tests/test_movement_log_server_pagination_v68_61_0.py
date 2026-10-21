from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTE = (ROOT / 'employee_movements/blueprints/movements.py').read_text(encoding='utf-8')
TEMPLATE = (ROOT / 'employee_movements/templates/movements.html').read_text(encoding='utf-8')


def _movement_route_block():
    start = ROUTE.index('def movements():')
    end = ROUTE.index("@bp.route('/movements/<int:i>/edit'")
    return ROUTE[start:end]


def test_historical_movement_log_uses_database_count_limit_and_offset():
    block = _movement_route_block()
    assert "movement_page_size = 100" in block
    assert "total_records = log_query.order_by(None).count()" in block
    assert ".limit(movement_page_size)" in block
    assert ".offset((movement_page - 1) * movement_page_size)" in block
    assert ".all()" in block
    assert "Movement.query.join(Employee).join(Branch).join(Governorate)" not in block


def test_current_movement_cards_use_window_rank_not_every_historical_movement():
    block = _movement_route_block()
    assert "func.row_number().over(" in block
    assert "partition_by=Movement.employee_id" in block
    assert "ranked_current.c.current_rank == 1" in block
    assert "current_page_size = 50" in block
    assert ".offset((current_page - 1) * current_page_size)" in block


def test_followup_card_is_counted_and_fetched_in_bounded_pages():
    block = _movement_route_block()
    assert "followup_rows_total = followup_query.order_by(None).count()" in block
    assert "followup_page_size = 50" in block
    assert ".offset((followup_page - 1) * followup_page_size)" in block
    assert "Movement.to_date <= tomorrow" in block
    assert "assignment_open_filter(Movement)" in block
    assert "or_(Movement.movement_type != 'انتداب', assignment_open_filter(Movement))" in block


def test_movement_log_filters_are_applied_by_sql_including_confirmed_aliases():
    block = _movement_route_block()
    assert "def movement_log_query():" in block
    assert "search_contains(Employee.full_name, term)" in block
    assert "search_contains(Employee.job_code, term)" in block
    assert "matched_employee_aliases" in block
    assert "matched_employee_codes" in block
    assert "matched_branch_aliases" in block
    assert "matched_governorate_aliases" in block


def test_movement_filter_form_and_pagination_preserve_selection_and_show_global_counts():
    assert 'id="movementFilterForm"' in TEMPLATE
    assert 'name="governorate_id" id="movementGovernorateFilter"' in TEMPLATE
    assert 'name="branch_id" id="movementBranchFilter"' in TEMPLATE
    assert 'name="employee_id" id="movementEmployeeFilter"' in TEMPLATE
    assert 'name="q" id="movementRecordsSearch"' in TEMPLATE
    assert 'name="movement_type" id="movementRecordsType"' in TEMPLATE
    assert "movement_page+1" in TEMPLATE and "movement_page-1" in TEMPLATE
    assert "current_page+1" in TEMPLATE and "followup_page+1" in TEMPLATE
    assert "document.querySelectorAll('#movement-log [data-movement-filter-row]')" in TEMPLATE
