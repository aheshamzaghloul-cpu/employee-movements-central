"""Regression contracts for conditional movement fields and recoverable mission-print dates."""
from pathlib import Path
import json
import re
import subprocess
from jinja2 import Environment

ROOT = Path(__file__).resolve().parents[1]
APP_JS = (ROOT / "employee_movements/static/js/app.js").read_text(encoding="utf-8")
MOVEMENT_TEMPLATE = (ROOT / "employee_movements/templates/movement_edit.html").read_text(encoding="utf-8")
MISSIONS = (ROOT / "employee_movements/blueprints/missions.py").read_text(encoding="utf-8")
PRINT_TEMPLATE = (ROOT / "employee_movements/templates/mission_print_date.html").read_text(encoding="utf-8")


def test_movement_edit_dynamically_gates_all_type_specific_fields():
    assert "const isLeave=v==='إجازة', isAssignment=v==='انتداب', isPermission=v==='إذن';" in APP_JS
    assert "if(leave){leave.required=isLeave;leave.disabled=!isLeave;}" in APP_JS
    assert "if(gov){gov.required=isAssignment;gov.disabled=!isAssignment;}" in APP_JS
    assert "if(dest){dest.required=isAssignment;dest.disabled=!isAssignment||!gov?.value;}" in APP_JS
    assert "if(fd){fd.required=hasDateRange;fd.disabled=!hasDateRange;}" in APP_JS
    assert "td.disabled=!hasDateRange||isOpenAssignment" in APP_JS
    assert "if(pd){pd.required=isPermission;pd.disabled=!isPermission;}" in APP_JS


def test_movement_type_switch_retains_draft_values_but_excludes_inactive_fields_from_post():
    block = APP_JS.split("function syncMovement(){", 1)[1].split("function syncAutoApprover", 1)[0]
    assert "Their values are retained" in block
    assert "if(el.tagName==='SELECT')el.value=''" not in block
    assert "el.disabled" not in block  # each field's type-specific disabled state is explicit above
    assert 'id="destination_governorate_id"' in MOVEMENT_TEMPLATE
    assert 'data-movement="إجازة" data-movement2="انتداب" hidden for="from_date"' in MOVEMENT_TEMPLATE


def test_invalid_temporary_print_date_is_rerendered_with_the_entered_value():
    assert "def _render_mission_print_date_form(m, return_to=None, form_values=None, validation_error=''):" in MISSIONS
    assert "form_values=dict(form_values or {})" in MISSIONS
    assert "{'print_to_date': raw_print_to_date}" in MISSIONS
    assert "'أدخل تاريخ «إلى» صحيحًا للطباعة باستخدام التقويم.'" in MISSIONS
    assert "'تاريخ «إلى» لا يجوز أن يسبق تاريخ «من». '" not in MISSIONS
    assert "value=\"{{form_values.get('print_to_date','')}}\"" in PRINT_TEMPLATE
    assert 'id="missionPrintDateError" role="alert"' in PRINT_TEMPLATE
    assert "to.setCustomValidity" in PRINT_TEMPLATE


def test_temporary_print_end_date_is_not_written_to_the_open_movement():
    route = MISSIONS.split("def mission_print_date_save(movement_id):", 1)[1].split(
        "@bp.get('/reports/assignments/mission-pdf/", 1
    )[0]
    assert "print_to_date=print_to_date" in route
    assert "m.to_date = print_to_date" not in route
    assert "mission_template_pdf(" in route


def test_updated_movement_and_print_templates_remain_valid_jinja():
    env = Environment()
    env.parse(MOVEMENT_TEMPLATE)
    env.parse(PRINT_TEMPLATE)


def test_temporary_print_date_validation_runtime_blocks_bad_range_and_recovers():
    match = re.search(r"<script>\s*(.*?)</script>", PRINT_TEMPLATE, flags=re.S)
    assert match, "the mission print date page must include its local validation handler"
    harness = r'''const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = SCRIPT_SOURCE;
function element(value='') {
  return {
    value, hidden:false, handlers:{}, attrs:{}, validityMessage:'', focused:0, reported:0,
    addEventListener(name, fn){ this.handlers[name]=fn; },
    setCustomValidity(value){ this.validityMessage=value; },
    setAttribute(name,value){ this.attrs[name]=value; },
    removeAttribute(name){ delete this.attrs[name]; },
    reportValidity(){ this.reported++; }, focus(){ this.focused++; }
  };
}
const form=element(), from=element('2026-10-20'), to=element('2026-10-19'), error=element();
const byId={missionPrintDateForm:form,missionPrintFromDate:from,missionPrintToDate:to,missionPrintDateError:error};
vm.runInNewContext(script,{document:{getElementById:id=>byId[id]||null}});
assert.match(to.validityMessage,/لا يجوز أن يسبق/);
assert.equal(to.attrs['aria-invalid'],'true');
let prevented=false;
form.handlers.submit({preventDefault(){prevented=true;}});
assert.equal(prevented,true); assert.equal(to.reported,1); assert.equal(to.focused,1);
to.value='2026-10-22'; to.handlers.input();
assert.equal(to.validityMessage,''); assert.equal(to.attrs['aria-invalid'],undefined);
assert.equal(error.hidden,true); assert.equal(to.attrs['aria-describedby'],'missionPrintDateHint');
prevented=false; form.handlers.submit({preventDefault(){prevented=true;}});
assert.equal(prevented,false);
from.value='—'; to.value='2026-10-01'; to.handlers.change();
assert.equal(to.validityMessage,'');
'''.replace('SCRIPT_SOURCE', json.dumps(match.group(1)))
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_open_assignment_keeps_the_end_date_draft_but_never_posts_it_as_a_saved_end_date():
    app_js = APP_JS.split("function syncMovement(){", 1)[1].split("function syncAutoApprover", 1)[0]
    inline = MOVEMENT_TEMPLATE.split("<script>", 1)[1].split("</script>", 1)[0]
    edit_route = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")
    edit_route = edit_route.split("def movement_edit(i):", 1)[1].split("@bp.post('/movements/<int:i>/submit')", 1)[0]
    assert "td.disabled=!hasDateRange||isOpenAssignment" in app_js
    assert "if(isOpenAssignment)td.value=''" not in app_js
    assert "to.disabled=open" in inline
    assert "if(open)to.value=''" not in inline
    # Server-side semantics remain authoritative even if a client sends stale data.
    assert "if mt == 'انتداب' and f.get('open_assignment') == '1':\n            td = None" in edit_route


def test_open_assignment_end_date_draft_survives_open_close_toggle_at_runtime():
    """Exercise the real movement-edit inline handler with a minimal DOM double."""
    match = re.search(r"<script>\s*(.*?)</script>", MOVEMENT_TEMPLATE, flags=re.S)
    assert match, "movement edit page should retain its local interaction script"
    harness = r'''const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = SCRIPT_SOURCE;
function element(value='') {
  return {
    value, checked:false, disabled:false, required:false, hidden:false, min:'',
    handlers:{}, validityMessage:'', options:[],
    addEventListener(name, fn){ this.handlers[name]=fn; },
    setCustomValidity(value){ this.validityMessage=value; }
  };
}
const type=element('انتداب'), checkbox=element(), from=element('2026-10-20'),
      to=element('2026-10-24'), toWrap=element();
const byId={movement_type:type,open_assignment:checkbox,from_date:from,to_date:to,
            to_date_wrap:toWrap,destination_governorate_id:null,destination_branch_id:null};
vm.runInNewContext(script,{document:{getElementById:id=>byId[id]||null}});
assert.equal(to.value,'2026-10-24');
checkbox.checked=true; checkbox.handlers.change();
assert.equal(to.disabled,true); assert.equal(to.required,false);
assert.equal(toWrap.hidden,true); assert.equal(to.value,'2026-10-24');
checkbox.checked=false; checkbox.handlers.change();
assert.equal(to.disabled,false); assert.equal(to.required,true);
assert.equal(toWrap.hidden,false); assert.equal(to.value,'2026-10-24');
'''.replace('SCRIPT_SOURCE', json.dumps(match.group(1)))
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
