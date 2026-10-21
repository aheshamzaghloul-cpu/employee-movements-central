"""Print should include all locally matching rows from the current server page."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_smart_table_temporarily_expands_results_for_print_and_restores_ui_state():
    source = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
    block = source.split("// v67.7 — smart data surfaces: search, counts and focus without changing server-side workflows.", 1)[1].split("document.querySelectorAll('[data-report-search-root]')", 1)[0]
    assert "const visibleLimit=expanded?matches.length:pageSize" in block
    assert "window.addEventListener('beforeprint'" in block
    assert "window.addEventListener('afterprint'" in block
    assert "expandedBeforePrint = expanded" in block
    assert "expanded = true" in block
    assert "expanded = expandedBeforePrint" in block
    assert "expandedBeforePrint = null" in block

def test_mission_center_print_toolbar_stays_hidden_but_table_rows_can_expand():
    template = (ROOT / "employee_movements/templates/mission_reports.html").read_text(encoding="utf-8")
    css = (ROOT / "employee_movements/static/css/ui-components.css").read_text(encoding="utf-8")
    assert 'data-smart-table data-smart-search-placeholder' in template
    assert 'data-smart-server-page="true"' in template
    assert ".smart-data-toolbar" in css and "@media print" in css
