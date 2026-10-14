from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "employee_movements" / "static" / "js" / "app.js").read_text(encoding="utf-8")
T = ROOT / "employee_movements" / "templates"


def block_for_auto_search(source: str) -> str:
    start = source.index("qsa('[data-auto-search]')")
    end = source.index("qsa('form')", start)
    return source[start:end]


def test_auto_search_empty_state_is_inserted_relative_to_the_target_table():
    block = block_for_auto_search(APP)
    assert "table.insertAdjacentElement('afterend',empty)" in block
    assert "surface.insertAdjacentElement('afterend',empty)" not in block


def test_users_account_search_and_progressive_table_share_the_expected_contract():
    users = (T / "users.html").read_text(encoding="utf-8")
    assert 'data-auto-search="#users-table"' in users
    assert 'table data-smart-table id="users-table"' in users
    assert "interactive-search-count" in block_for_auto_search(APP)
    assert "data-smart-table-search" in APP
