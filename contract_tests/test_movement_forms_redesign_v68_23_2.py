from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "employee_movements" / "templates"
STATIC = ROOT / "employee_movements" / "static"
VERSION = (ROOT / "VERSION.md").read_text(encoding="utf-8").strip()
BASE = (TEMPLATES / "base.html").read_text(encoding="utf-8")
MOVEMENTS = (TEMPLATES / "movements.html").read_text(encoding="utf-8")
MOVEMENT_EDIT = (TEMPLATES / "movement_edit.html").read_text(encoding="utf-8")
MISSION_EDIT = (TEMPLATES / "mission_edit.html").read_text(encoding="utf-8")
MISSION_REVIEW = (TEMPLATES / "mission_edit_request_review.html").read_text(encoding="utf-8")
PAGE_CSS = (STATIC / "css/pages/movement-forms.css").read_text(encoding="utf-8")
APP_CSS = (STATIC / "css/app.css").read_text(encoding="utf-8")
APP_JS = (STATIC / "js/app.js").read_text(encoding="utf-8")


def test_page_styles_are_scoped_to_movement_workflows_and_versioned():
    assert "css/pages/movement-forms.css" in BASE
    assert "request.path.startswith('/movements')" in BASE
    assert "request.path.startswith('/reports/assignments/mission-edit')" in BASE
    assert "request.path.startswith('/reports/assignments/edit-requests')" in BASE
    assert f"?v={VERSION}" in BASE
    assert ".movement-workspace" in PAGE_CSS and ".movement-edit-page" in PAGE_CSS


def test_create_form_preserves_server_fields_and_csrf_contract():
    for hook in (
        'action="/movements/create"', 'name="_csrf"', 'name="employee_id"',
        'name="movement_type"', 'name="leave_type"', 'name="leave_from_date"',
        'name="leave_to_date"', 'name="destination_branch_id"',
        'name="assignment_from_date"', 'name="assignment_to_date"',
        'name="open_assignment"', 'name="permission_date"',
    ):
        assert hook in MOVEMENTS


def test_create_form_dates_are_conditional_and_reject_end_before_start():
    assert "assignmentToDate.required=isAssignment&&!open" in MOVEMENTS
    assert "assignmentToDate.disabled=open" in MOVEMENTS
    assert "assignmentToDateField.hidden=open" in MOVEMENTS
    assert "leaveToDate.min=isLeave?(leaveFromDate?.value||''):''" in MOVEMENTS
    assert "تاريخ النهاية يجب ألا يسبق تاريخ البداية." in MOVEMENTS
    assert "تاريخ النهاية يسبق تاريخ البداية." in MOVEMENTS


def test_movement_edit_open_assignment_does_not_require_end_date():
    for hook in ('id="open_assignment"', 'id="to_date_wrap"', 'id="to_date"', 'name="to_date"'):
        assert hook in MOVEMENT_EDIT
    assert "td.required=(v==='إجازة')||(v==='انتداب'&&!isOpenAssignment)" in APP_JS
    assert "td.disabled=isOpenAssignment" in APP_JS
    assert "if(endWrap&&v==='انتداب')endWrap.hidden=isOpenAssignment" in APP_JS
    assert "td.setCustomValidity" in APP_JS


def test_mission_edit_keeps_an_open_assignment_end_optional_and_validates_dates():
    assert 'name="destination_branch_id"' in MISSION_EDIT
    assert 'name="from_date"' in MISSION_EDIT
    assert 'name="to_date"' in MISSION_EDIT
    assert 'id="missionEditToDate"' in MISSION_EDIT
    assert 'to.required' not in MISSION_EDIT
    assert "to.min=from.value||''" in MISSION_EDIT
    assert "تاريخ النهاية لا يجوز أن يسبق تاريخ البداية." in MISSION_EDIT


def test_manager_review_end_date_requirement_tracks_final_state():
    assert 'name="final_state" id="reviewMissionFinalState"' in MISSION_REVIEW
    assert "to.required=finalState?.value==='مغلقة'" in MISSION_REVIEW
    assert "finalState?.addEventListener('change',validateDates)" in MISSION_REVIEW
    assert "مطلوب للحالة المغلقة" in MISSION_REVIEW
    assert "اختياري للحالة تحت التحرير" in MISSION_REVIEW
    assert 'name="manager_notes"' in MISSION_REVIEW


def test_form_actions_are_not_sticky_over_mobile_inputs():
    assert re.search(r"\.movement-edit-page \.ui-movement-form-actions\s*\{[^}]*position:static", PAGE_CSS)
    assert "@media(max-width:560px)" in PAGE_CSS
    assert "grid-template-columns:minmax(0,1fr)" in PAGE_CSS


def test_off_canvas_sidebar_no_longer_widens_the_document_on_mobile():
    assert "html { overflow-x: hidden; overflow-x: clip; }" in APP_CSS
    assert "transform: translateX(105%)" in APP_CSS
    assert ".premium-sidebar.is-open" in APP_CSS


def test_html_form_labels_and_status_regions_are_accessible():
    assert 'for="movementCreateType"' in MOVEMENTS
    assert 'role="status" aria-live="polite"' in MOVEMENTS
    assert 'for="missionEditToDate"' in MISSION_EDIT
    assert 'for="reviewMissionToDate"' in MISSION_REVIEW
    assert 'aria-labelledby="movementEditTypeTitle"' in MOVEMENT_EDIT


def test_switching_movement_type_clears_stale_validation_on_inactive_dates():
    assert "assignmentToDate.min=isAssignment?(assignmentFromDate?.value||''):''" in MOVEMENTS
    assert "leaveToDate.min=isLeave?(leaveFromDate?.value||''):''" in MOVEMENTS
    assert "hasDateRange=v==='إجازة'||v==='انتداب'" in APP_JS
    assert "td.min=hasDateRange?(fd?.value||''):''" in APP_JS
    assert "hasDateRange&&fd?.value&&td.value&&td.value<fd.value" in APP_JS
