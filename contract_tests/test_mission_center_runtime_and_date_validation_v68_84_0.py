from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_mission_center_has_no_stale_reopen_handler_reference():
    script = _read("employee_movements/static/js/mission_center.js")
    assert "const reopenForm = workspace.querySelector('[data-selected-reopen-form]');" in script
    assert script.index("const reopenForm = workspace.querySelector('") < script.index("reopenForm?.addEventListener('submit'")
    assert "clearSelection();" in script
    assert "initMissionDateRangeFilter();" in script


def test_mission_date_range_is_validated_before_submission_and_accessible():
    script = _read("employee_movements/static/js/mission_center.js")
    template = _read("employee_movements/templates/mission_reports.html")
    assert "function initMissionDateRangeFilter()" in script
    assert "from.value > to.value" in script
    assert "to.setCustomValidity(invalid ? message : '')" in script
    assert "event.preventDefault();" in script
    assert 'id="missionDateRangeClientError" role="alert" hidden' in template
    assert "aria-invalid" in script and "aria-describedby" in script


def test_date_range_error_is_not_only_server_side():
    script = _read("employee_movements/static/js/mission_center.js")
    assert "from.addEventListener('input', updateRangeState)" in script
    assert "to.addEventListener('change', updateRangeState)" in script
    assert "to.focus();" in script
    assert "to.reportValidity();" in script
