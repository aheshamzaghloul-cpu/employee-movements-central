"""Regression contracts for create-form draft retention and stale picker responses."""
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MOVEMENTS = (ROOT / "employee_movements/templates/movements.html").read_text(encoding="utf-8")
MOVEMENT_ROUTE = (ROOT / "employee_movements/blueprints/movements.py").read_text(encoding="utf-8")


def _inline_prefix_before_destination_picker() -> str:
    match = re.search(r"<script>\s*(.*?)</script>", MOVEMENTS, flags=re.S)
    assert match, "the movement create page must include its form interaction handler"
    script = match.group(1)
    marker = "  const destinationGov=$('movementDestinationGovernorate'), destinationBranch=$('movementDestinationBranch');"
    assert marker in script
    return script.split(marker, 1)[0] + "\n})();"


def test_create_open_assignment_retains_end_date_as_a_draft_and_server_ignores_it():
    date_rules = MOVEMENTS.split("function syncMovementDateRules(){", 1)[1].split("const destinationGov=", 1)[0]
    create_route = MOVEMENT_ROUTE.split("def movement_create():", 1)[1].split("@bp.get('/movements')", 1)[0]
    assert "assignmentToDate.disabled=open" in date_rules
    assert "assignmentToDate.required=isAssignment&&!open" in date_rules
    assert "if(open)assignmentToDate.value=''" not in date_rules
    assert "if(openAssignment.checked&&assignmentToDate)assignmentToDate.value=''" not in MOVEMENTS
    assert "to_date = None if (movement_type == 'انتداب' and form.get('open_assignment') == '1')" in create_route


def test_create_open_assignment_toggle_retains_draft_at_runtime():
    script = _inline_prefix_before_destination_picker()
    harness = r'''const vm = require('node:vm');
const assert = require('node:assert/strict');
const script = SCRIPT_SOURCE;
function element(value='') {
  return { value, checked:false, disabled:false, required:false, hidden:false, min:'', handlers:{}, validityMessage:'',
    addEventListener(name, fn){ this.handlers[name]=fn; },
    setCustomValidity(value){ this.validityMessage=value; } };
}
const byId={
  movementCreateType:element('انتداب'), movementLeavePanel:element(), movementAssignmentPanel:element(),
  movementPermissionPanel:element(), openAssignment:element(), assignmentToDate:element('2026-10-28'),
  assignmentToDateField:element(), leaveFromDate:element(''), leaveToDate:element(''),
  assignmentFromDate:element('2026-10-20'), permissionDate:element(''), movementLeaveType:element(''),
  movementDestinationGovernorate:element(''), movementDestinationBranch:element('')
};
byId.openAssignment.checked=false;
vm.runInNewContext(script,{document:{getElementById:id=>byId[id]||null}});
const end=byId.assignmentToDate, open=byId.openAssignment, wrap=byId.assignmentToDateField;
assert.equal(end.value,'2026-10-28');
open.checked=true; open.handlers.change();
assert.equal(end.disabled,true); assert.equal(end.required,false); assert.equal(wrap.hidden,true);
assert.equal(end.value,'2026-10-28','switching to open assignment must preserve the draft');
open.checked=false; open.handlers.change();
assert.equal(end.disabled,false); assert.equal(end.required,true); assert.equal(wrap.hidden,false);
assert.equal(end.value,'2026-10-28','switching back must restore the same draft');
'''.replace("SCRIPT_SOURCE", json.dumps(script))
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_picker_loaders_guard_against_out_of_order_governorate_and_branch_responses():
    reset = MOVEMENTS.split("function resetAfterGovernorate(){", 1)[1].split("function branchCard(b){", 1)[0]
    reset = "function resetAfterGovernorate(){" + reset
    loader_start = MOVEMENTS.index("async function loadCreateBranches(){")
    loader_end = MOVEMENTS.index("function renderEmployeePicker(){", loader_start)
    loaders = MOVEMENTS[loader_start:loader_end]
    assert "let branchRequestSeq=0, employeeRequestSeq=0;" in MOVEMENTS
    assert "requestSeq!==branchRequestSeq" in loaders
    assert "gid!==(govCreate?.value||'')" in loaders
    assert "movementType!==(type?.value||'')" in loaders
    assert "requestSeq===employeeRequestSeq" in loaders
    assert "requestedBranchId===String(activePickerBranch?.id||'')" in loaders

    app_source = """
let availableBranches=[], availableEmployees=[], activePickerBranch=null, showAllBranches=false, showAllEmployees=false;
let branchRequestSeq=0, employeeRequestSeq=0, renderedBranchIds=[], renderedEmployeeIds=[];
function renderBranchPicker(){ renderedBranchIds=availableBranches.map(x=>x.id); }
function renderEmployeePicker(){ renderedEmployeeIds=availableEmployees.map(x=>x.id); }
""" + reset + loaders + """
globalThis.api={
  loadCreateBranches, loadCreateEmployees,
  getBranches:()=>availableBranches.map(x=>x.id),
  getEmployees:()=>availableEmployees.map(x=>x.id),
  getRenderedBranches:()=>renderedBranchIds,
  getRenderedEmployees:()=>renderedEmployeeIds
};
"""
    harness_template = r'''const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=APP_SOURCE;
const deferred=[];
const element=(value='')=>({value,checked:false,disabled:false,required:false,hidden:false,innerHTML:'',textContent:'',handlers:{},
  addEventListener(name,fn){this.handlers[name]=fn;},focus(){},scrollIntoView(){},setCustomValidity(){}});
const type=element('انتداب'), govCreate=element('1');
const branchStep=element(),employeeStep=element(),detailsStep=element(),branchGrid=element(),employeeGrid=element();
const employeeId=element(),selectedEmployee=element(),branchSearch=element(),employeeSearch=element();
const branchCount=element(),employeeCount=element(),branchShowAll=element(),employeeShowAll=element();
const branchEmpty=element(),employeeEmpty=element(),preflight=element(),movementEmployeeHint=element();
const context={
  type,govCreate,branchStep,employeeStep,detailsStep,branchGrid,employeeGrid,employeeId,selectedEmployee,
  branchSearch,employeeSearch,branchCount,employeeCount,branchShowAll,employeeShowAll,branchEmpty,employeeEmpty,
  preflight,
  $:id=>id==='movementEmployeeHint'?movementEmployeeHint:null,
  setProgress:()=>{},
  fetch:url=>new Promise((resolve,reject)=>deferred.push({url,resolve,reject})),
  document:{querySelectorAll:()=>[]},URLSearchParams,console
};
vm.runInNewContext(source,context);
(async()=>{
 const api=context.api;
 const first=api.loadCreateBranches();
 context.govCreate.value='2';
 const second=api.loadCreateBranches();
 deferred[1].resolve({ok:true,json:async()=>({branches:[{id:2,name:'فرع المحافظة الثانية'}]})});
 await second;
 deferred[0].resolve({ok:true,json:async()=>({branches:[{id:1,name:'فرع المحافظة الأولى'}]})});
 await first;
 assert.deepEqual(api.getBranches(),[2]);
 assert.deepEqual(api.getRenderedBranches(),[2]);
 const empFirst=api.loadCreateEmployees({id:21,name:'فرع أ'});
 const empSecond=api.loadCreateEmployees({id:22,name:'فرع ب'});
 deferred[3].resolve({ok:true,json:async()=>({employees:[{id:222,name:'موظف الفرع ب'}]})});
 await empSecond;
 deferred[2].resolve({ok:true,json:async()=>({employees:[{id:211,name:'موظف الفرع أ'}]})});
 await empFirst;
 assert.deepEqual(api.getEmployees(),[222]);
 assert.deepEqual(api.getRenderedEmployees(),[222]);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
    harness = harness_template.replace("APP_SOURCE", json.dumps(app_source))
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


def test_create_form_invalidates_old_preflight_and_disables_submit_immediately():
    start = MOVEMENTS.index("function refreshMovementReview(){")
    end = MOVEMENTS.index("function showCurrentWarning(e){", start)
    block = MOVEMENTS[start:end]
    assert "preflightSeq++;" in block
    assert "if(submit)submit.disabled=true;" in block
    assert block.index("preflightSeq++;") < block.index("setTimeout(runMovementPreflight,180)")

    harness = r'''const vm=require('node:vm');
const assert=require('node:assert/strict');
const source=FUNCTION_SOURCE;
const elem=(value='')=>({value,hidden:false,disabled:false,textContent:'',selectedOptions:[],setAttribute(){},classList:{toggle(){}}});
const type=elem('انتداب'), employeeId=elem('123'), from=elem('2026-10-20'), to=elem('2026-10-25');
const destination=elem('9'); destination.selectedOptions=[{textContent:'فرع الوجهة'}];
const openAssignment=elem(''); openAssignment.checked=false;
const review=elem(), reviewText=elem(), submit=elem(''); submit.disabled=false;
const context={type,employeeId,review,reviewText,submit,preflightSeq:7,preflightTimer:0,
  document:{querySelector:selector=>selector.includes('assignment_from_date')?from:selector.includes('assignment_to_date')?to:elem('')},
  $:id=>id==='movementDestinationBranch'?destination:(id==='openAssignment'?openAssignment:null),
  clearTimeout(){},setTimeout(){return 99;},runMovementPreflight(){}};
vm.runInNewContext(source,context);
context.refreshMovementReview();
assert.equal(context.preflightSeq,8,'new input must invalidate the prior in-flight preflight');
assert.equal(context.submit.disabled,true,'submission must remain disabled while checking the newest state');
'''.replace('FUNCTION_SOURCE', json.dumps(block))
    result = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
