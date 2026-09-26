(function(){
  const qs=(s,r=document)=>r.querySelector(s), qsa=(s,r=document)=>[...r.querySelectorAll(s)];

  function syncDependentSelect(gid,bid){
    const g=qs('#'+gid), b=qs('#'+bid); if(!g||!b)return;
    const options=qsa('option',b);
    function sync(){
      const v=g.value;
      options.forEach(o=>{if(!o.value)return; const ok=!v||o.dataset.governorate===v; o.hidden=!ok; o.disabled=!ok;});
      if(b.value && b.selectedOptions[0]?.disabled)b.value='';
    }
    g.addEventListener('change',sync); sync();
  }
  syncDependentSelect('new_employee_governorate','new_employee_branch');
  syncDependentSelect('employee_governorate','employee_branch');
  syncDependentSelect('employee_governorate_filter','employee_branch_filter');

  // Roles control which scope groups are required/visible.
  qsa('form').forEach(form=>{
    const roleBoxes=qsa('input[type=checkbox][name="roles"]',form);
    if(!roleBoxes.length)return;
    function syncRoles(){
      const roles=roleBoxes.filter(x=>x.checked).map(x=>x.value);
      qsa('[data-role-scope="supervisor"]',form).forEach(x=>x.hidden=!roles.includes('مشرف محافظة'));
      qsa('[data-role-scope="entry"]',form).forEach(x=>x.hidden=!roles.includes('المدخل الأول'));
      qsa('[data-required-role]',form).forEach(group=>{
        const required=roles.includes(group.dataset.requiredRole);
        group.dataset.required=required?'1':'0';
      });
    }
    roleBoxes.forEach(x=>x.addEventListener('change',syncRoles)); syncRoles();
  });

  // Multi-select checkbox tools remain for roles, permissions, governorates and branches.
  function boxes(name,root){return qsa('input[type="checkbox"][name="'+CSS.escape(name)+'"]',root)}
  qsa('[data-choice-all]').forEach(btn=>btn.addEventListener('click',()=>{const root=btn.closest('form')||document;boxes(btn.dataset.choiceAll,root).forEach(x=>x.checked=true); root.querySelectorAll('input[type=checkbox][name="roles"]').forEach(x=>x.dispatchEvent(new Event('change')));}));
  qsa('[data-choice-none]').forEach(btn=>btn.addEventListener('click',()=>{const root=btn.closest('form')||document;boxes(btn.dataset.choiceNone,root).forEach(x=>x.checked=false); root.querySelectorAll('input[type=checkbox][name="roles"]').forEach(x=>x.dispatchEvent(new Event('change')));}));

  // Validate checkbox groups that are conditionally required.
  qsa('form').forEach(form=>form.addEventListener('submit',e=>{
    const groups=qsa('[data-choice-group]',form);
    for(const group of groups){
      if(group.dataset.required!=='1')continue;
      const name=group.dataset.choiceGroup;
      if(!boxes(name,form).some(x=>x.checked)){e.preventDefault(); alert('يجب اختيار عنصر واحد على الأقل.'); return;}
    }
  }));

  // Movement dynamic fields and automatic approver by dependency.
  const movementType=qs('#movement_type'), movementEmployee=qs('#movement_employee');
  function syncMovement(){
    const v=movementType?.value||'';
    qsa('[data-movement]').forEach(el=>{const types=[el.dataset.movement,el.dataset.movement2].filter(Boolean); el.hidden=!types.includes(v);});
    const leave=qs('#leave_type'), dest=qs('#destination_branch_id'), fd=qs('#from_date'), td=qs('#to_date'), pd=qs('#permission_date');
    if(leave)leave.required=v==='إجازة'; if(dest)dest.required=v==='انتداب'; if(fd)fd.required=v==='إجازة'||v==='انتداب'; if(td)td.required=v==='إجازة'||v==='انتداب'; if(pd)pd.required=v==='إذن';
    [leave,dest,fd,td,pd].forEach(el=>{if(!el)return; const wrap=el.closest('[data-movement]'); if(wrap&&wrap.hidden){el.required=false; if(el.tagName==='SELECT')el.value='';}});
    const days=qs('#movement_days');
    if(days){if(v==='إذن'){days.textContent='—';} else if(fd?.value&&td?.value){const a=new Date(fd.value),b=new Date(td.value);days.textContent=b>=a?Math.floor((b-a)/86400000)+1:'—';} else days.textContent='—';}
    const hint=qs('#movement_duration_hint'); if(hint)hint.textContent=v==='إذن'?'الإذن يُسجل بتاريخ واحد.':'تحسب تلقائيًا من تاريخ البداية حتى النهاية.';
  }
  function syncAutoApprover(){
    const display=qs('#approver_display'); if(!display)return;
    const selected=movementEmployee?.selectedOptions?.[0];
    display.innerHTML='';
    const o=document.createElement('option');
    o.value=selected?.dataset.approverId||'';
    o.textContent=selected?.dataset.approverLabel||'يظهر تلقائيًا بعد اختيار الموظف';
    o.selected=true; display.appendChild(o);
  }
  movementType?.addEventListener('change',syncMovement); ['#from_date','#to_date'].forEach(s=>qs(s)?.addEventListener('input',syncMovement)); movementEmployee?.addEventListener('change',syncAutoApprover);
  syncMovement(); syncAutoApprover();
  const movementForm=qs('#movement_form');
  movementForm?.addEventListener('submit',e=>{if(movementEmployee&&!movementEmployee.value){e.preventDefault();alert('يجب اختيار الموظف.');}});

  // Dropdown multi-select summaries.
  function updateMultiSummaries(root=document){
    qsa('[data-multi-dropdown]',root).forEach(dd=>{
      const group=qs('[data-choice-group]',dd); if(!group)return;
      const name=group.dataset.choiceGroup; const boxes=qsa('input[type=checkbox][name=\"'+CSS.escape(name)+'\"]',dd);
      const checked=boxes.filter(x=>x.checked); const target=qs('[data-multi-summary=\"'+CSS.escape(name)+'\"]',dd);
      if(target) target.textContent=checked.length?`${checked.length} محدد`:'لم يتم الاختيار';
    });
  }
  qsa('[data-multi-dropdown] input[type=checkbox]').forEach(x=>x.addEventListener('change',()=>updateMultiSummaries()));
  qsa('[data-choice-all], [data-choice-none]').forEach(btn=>btn.addEventListener('click',()=>setTimeout(updateMultiSummaries,0)));
  updateMultiSummaries();

  // Homepage employee search.
  const homeSearch=qs('#home_employee_search'), homeResults=qs('#home_search_results'), homeEmpty=qs('#home_search_empty'); let searchTimer=null,searchSeq=0;
  function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}
  function hideHome(){if(homeResults){homeResults.hidden=true;homeResults.innerHTML='';}if(homeEmpty)homeEmpty.hidden=true;}
  function renderHome(items){if(!homeResults||!homeEmpty)return;homeEmpty.hidden=items.length!==0;if(!items.length){homeResults.hidden=true;return;} const card=(t,x,c)=>x?`<div class="search-movement ${c}"><span>${t}</span><b>${esc(x.label)}</b><small>${esc(x.detail||'—')}</small></div>`:`<div class="search-movement ${c} muted"><span>${t}</span><b>لا توجد بيانات</b><small>—</small></div>`;homeResults.innerHTML=items.map(x=>`<a class="search-result" href="/employee/${x.id}"><div class="search-person"><strong>${esc(x.name)}</strong><small>الكود الوظيفي: ${esc(x.code)} — ${esc(x.branch)}</small></div><div class="search-movements">${card('آخر إجازة',x.last_leave,'leave')}${card('آخر انتداب',x.last_assignment,'assign')}${card('آخر إذن',x.last_permission,'permit')}</div><span class="search-code">فتح البطاقة ←</span></a>`).join('');homeResults.hidden=false;}
  async function doHome(){const q=(homeSearch?.value||'').trim();if(q.length<2){hideHome();return;}const seq=++searchSeq;if(homeResults){homeResults.hidden=false;homeResults.innerHTML='<div class="search-loading">جاري البحث…</div>';}try{const r=await fetch('/employee-search?q='+encodeURIComponent(q),{headers:{Accept:'application/json'}});const d=await r.json();if(seq===searchSeq)renderHome(d.results||[]);}catch(_){if(seq===searchSeq)homeResults.innerHTML='<div class="search-loading">تعذر تنفيذ البحث.</div>';}}
  homeSearch?.addEventListener('input',()=>{clearTimeout(searchTimer);searchTimer=setTimeout(doHome,220)});homeSearch?.addEventListener('keydown',e=>{if(e.key==='Escape')hideHome()});document.addEventListener('click',e=>{if(homeResults&&!e.target.closest('.employee-search-wrap'))hideHome()});

  // Home movement employee lookup: governorate first, then branch OR live name/code search.
  const movementSearchForm=qs('#movement-employee-search-form');
  const movementGov=qs('#movement-search-governorate');
  const movementBranch=qs('#movement-search-branch');
  const movementPickerWrap=qs('#movement-employee-picker-wrap');
  const movementPicker=qs('#movement-search-employee');
  const movementName=qs('#movement-search-name');
  const movementSuggestions=qs('#movement-search-suggestions');
  let movementSearchTimer=null, movementSearchSeq=0;
  function hideMovementSuggestions(){if(movementSuggestions){movementSuggestions.hidden=true;movementSuggestions.innerHTML='';}}
  function setMovementBranches(items, selected=''){
    if(!movementBranch)return;
    movementBranch.innerHTML='<option value="">كل الفروع</option>'+items.map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join('');
    if(selected) movementBranch.value=String(selected);
  }
  function renderMovementSuggestions(items){
    if(!movementSuggestions)return;
    if(!items.length){movementSuggestions.innerHTML='<div class="movement-suggestion-empty">لا توجد نتائج مطابقة.</div>';movementSuggestions.hidden=false;return;}
    movementSuggestions.innerHTML=items.map(e=>`<button type="button" class="movement-suggestion" data-employee-id="${esc(e.id)}"><span><strong>${esc(e.name)}</strong><small>${esc(e.branch||'')} ${e.code?'· كود '+esc(e.code):''}</small></span><b>عرض البطاقة ←</b></button>`).join('');
    movementSuggestions.hidden=false;
    qsa('.movement-suggestion',movementSuggestions).forEach(btn=>btn.addEventListener('click',()=>{
      const params=new URLSearchParams(); params.set('movement_governorate_id',movementGov.value);
      if(movementBranch?.value) params.set('movement_branch_id',movementBranch.value);
      params.set('employee_id',btn.dataset.employeeId);
      window.location.href='/?'+params.toString();
    }));
  }
  async function loadMovementSearch(){
    const gid=movementGov?.value||''; if(!gid){if(movementName){movementName.disabled=true;movementName.value='';} hideMovementSuggestions(); setMovementBranches([]); return;}
    if(movementName) movementName.disabled=false;
    const q=(movementName?.value||'').trim(); const bid=movementBranch?.value||''; const seq=++movementSearchSeq;
    if(q.length===1 && movementSuggestions){movementSuggestions.hidden=false;movementSuggestions.innerHTML='<div class="movement-suggestion-empty">اكتب حرفًا آخر للبحث…</div>';}
    try{
      const url='/api/movement-employees?governorate_id='+encodeURIComponent(gid)+(bid?'&branch_id='+encodeURIComponent(bid):'')+(q?'&q='+encodeURIComponent(q):'');
      const r=await fetch(url,{headers:{Accept:'application/json'}}); const d=await r.json();
      if(seq!==movementSearchSeq)return;
      setMovementBranches(d.branches||[],bid);
      if(movementPicker && movementPickerWrap){
        if(bid){
          movementPicker.innerHTML='<option value="">اختر الموظف</option>'+(d.results||[]).map(e=>`<option value="${esc(e.id)}">${esc(e.name)}${e.code?' — '+esc(e.code):''}</option>`).join('');
          movementPickerWrap.hidden=false;
        }else{ movementPickerWrap.hidden=true; movementPicker.innerHTML='<option value="">اختر الموظف</option>'; }
      }
      if(q.length>=2) renderMovementSuggestions(d.results||[]); else hideMovementSuggestions();
    }catch(_){if(seq===movementSearchSeq&&movementSuggestions){movementSuggestions.innerHTML='<div class="movement-suggestion-empty">تعذر تنفيذ البحث.</div>';movementSuggestions.hidden=false;}}
  }
  movementGov?.addEventListener('change',()=>{if(movementBranch)movementBranch.value=''; if(movementName)movementName.value=''; hideMovementSuggestions(); loadMovementSearch();});
  movementBranch?.addEventListener('change',()=>{if(movementName)movementName.value=''; hideMovementSuggestions(); if(movementGov?.value)loadMovementSearch();});
  movementPicker?.addEventListener('change',()=>{
    if(!movementPicker.value)return;
    const params=new URLSearchParams(); params.set('movement_governorate_id',movementGov.value); if(movementBranch?.value)params.set('movement_branch_id',movementBranch.value); params.set('employee_id',movementPicker.value); window.location.href='/?'+params.toString();
  });
  movementName?.addEventListener('input',()=>{clearTimeout(movementSearchTimer);movementSearchTimer=setTimeout(loadMovementSearch,180);});
  movementName?.addEventListener('keydown',e=>{if(e.key==='Escape')hideMovementSuggestions();});
  document.addEventListener('click',e=>{if(movementSuggestions&&!e.target.closest('.movement-employee-search'))hideMovementSuggestions();});
  if(movementGov?.value)loadMovementSearch();
  movementSearchForm?.addEventListener('submit',e=>{
    if(!movementGov?.value){e.preventDefault();alert('اختر المحافظة أولًا.');return;}
    if(movementName?.value.trim()){e.preventDefault();loadMovementSearch();return;}
  });

  // Compact real movement form on homepage.
  const hmGov=qs('#home_move_gov'), hmBranch=qs('#home_move_branch'), hmEmp=qs('#home_move_employee'), hmType=qs('#home_move_type');
  async function hmLoadBranches(){ if(!hmGov||!hmBranch)return; hmBranch.innerHTML='<option value="">اختر الفرع</option>'; hmBranch.disabled=true; hmEmp.innerHTML='<option value="">اختر الموظف</option>'; hmEmp.disabled=true; if(!hmGov.value)return; try{const r=await fetch('/api/movement-employees?governorate_id='+encodeURIComponent(hmGov.value)); const d=await r.json(); hmBranch.innerHTML='<option value="">اختر الفرع</option>'+(d.branches||[]).map(b=>`<option value="${esc(b.id)}">${esc(b.name)}</option>`).join(''); hmBranch.disabled=!(d.branches||[]).length;}catch(_){}}
  async function hmLoadEmployees(){if(!hmGov?.value||!hmBranch?.value)return; hmEmp.innerHTML='<option value="">جاري التحميل…</option>'; hmEmp.disabled=true; try{const r=await fetch('/api/movement-employees?governorate_id='+encodeURIComponent(hmGov.value)+'&branch_id='+encodeURIComponent(hmBranch.value)); const d=await r.json(); hmEmp.innerHTML='<option value="">اختر الموظف</option>'+(d.results||[]).map(e=>`<option value="${esc(e.id)}">${esc(e.name)}${e.code?' — '+esc(e.code):''}</option>`).join(''); hmEmp.disabled=!(d.results||[]).length;}catch(_){hmEmp.innerHTML='<option value="">تعذر التحميل</option>';}}
  function hmSyncType(){qsa('.movement-dynamic[data-move-type]').forEach(el=>{const types=(el.dataset.moveType||'').split(','); el.style.display=types.includes(hmType?.value)?'flex':'none';});}
  hmGov?.addEventListener('change',hmLoadBranches); hmBranch?.addEventListener('change',hmLoadEmployees); hmType?.addEventListener('change',hmSyncType); hmSyncType();

  // Generic table search and confirmations.
  qsa('[data-confirm]').forEach(el=>el.addEventListener('click',e=>{if(!confirm(el.dataset.confirm))e.preventDefault()}));
  qsa('[data-auto-search]').forEach(input=>input.addEventListener('input',()=>{const q=input.value.trim().toLowerCase(),target=input.dataset.autoSearch;qsa(target+' tbody tr').forEach(tr=>tr.style.display=!q||tr.innerText.toLowerCase().includes(q)?'':'none');}));

  // Employee history filters.
  const hist=qs('#employee_history_table'); if(hist){const rows=qsa('tbody tr[data-movement-type]',hist),buttons=qsa('[data-history-filter]'),search=qs('#employee_history_search'),no=qs('#history_no_match');let filter='all';const apply=()=>{const q=(search?.value||'').toLowerCase().trim();let n=0;rows.forEach(r=>{const ok=(filter==='all'||r.dataset.movementType===filter)&&(!q||r.innerText.toLowerCase().includes(q));r.hidden=!ok;if(ok)n++});if(no)no.hidden=n!==0};buttons.forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.historyFilter;buttons.forEach(x=>x.classList.toggle('active',x===b));apply()}));search?.addEventListener('input',apply);}

  // Filter branch dropdown by governorate on employee list.
  const fg=qs('#employee_governorate_filter'), fb=qs('#employee_branch_filter'); if(fg&&fb){const sync=()=>{[...fb.options].forEach(o=>{if(!o.value)return;const ok=!fg.value||o.dataset.governorate===fg.value;o.hidden=!ok;o.disabled=!ok});if(fb.value&&fb.selectedOptions[0]?.disabled)fb.value='';};fg.addEventListener('change',sync);sync();}
})();

// v34 movement registration: show employee's basic branch and approver name/job.
document.addEventListener('DOMContentLoaded', function(){
  const emp=document.getElementById('movement_employee');
  const branch=document.getElementById('employee_home_branch');
  const app=document.getElementById('approver_display');
  if(!emp) return;
  function sync(){
    const o=emp.options[emp.selectedIndex];
    if(branch) branch.value=o ? (o.dataset.branchLabel||'') : '';
    if(app){ app.innerHTML=''; const opt=document.createElement('option'); opt.textContent=o && o.dataset.approverLabel ? o.dataset.approverLabel : 'يظهر تلقائيًا بعد اختيار الموظف'; app.appendChild(opt); }
  }
  emp.addEventListener('change',sync); sync();
});


// v34.8: صلاحيات الدور الافتراضية تضاف تلقائيًا عند إنشاء الحساب، وتبقى قابلة للتعديل لاحقًا.
(function(){
  const qs=(s,r=document)=>r.querySelector(s), qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const roleDefaults={};
  function syncRoleDefaults(form){
    const roles=qsa('input[name="roles"]:checked',form).map(x=>x.value);
    qsa('input[name="permissions"]',form).forEach(p=>{
      const defs=(p.dataset.permissionDefaultRoles||'').split('|').filter(Boolean);
      const should=roles.some(r=>defs.includes(r));
      if(should){ p.checked=true; p.dataset.autoDefault='1'; }
      else if(p.dataset.autoDefault==='1'){ p.checked=false; p.dataset.autoDefault=''; }
    });
  }
  qsa('form').forEach(form=>{
    if(!qsa('input[name="roles"]',form).length || !qsa('input[name="permissions"]',form).length) return;
    qsa('input[name="roles"]',form).forEach(x=>x.addEventListener('change',()=>syncRoleDefaults(form)));
    syncRoleDefaults(form);
  });
})();

// v34.8: كل بند رئيسي قابل للعرض الكامل أو الاختصار إلى اسم البند فقط.
(function(){
  const qs=(s,r=document)=>r.querySelector(s), qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  qsa('.box').forEach((box,idx)=>{
    if(box.classList.contains('no-collapse') || box.closest('.mission-page')) return;
    const title=qs('.section-title',box);
    if(!title) return;
    const heading=qs('h1,h2,h3',title);
    if(!heading) return;
    let body=document.createElement('div'); body.className='smart-body';
    const children=[...box.children].filter(el=>el!==title);
    if(!children.length) return;
    children.forEach(el=>body.appendChild(el));
    box.appendChild(body); box.classList.add('smart-collapsible');
    const btn=document.createElement('button'); btn.type='button'; btn.className='smart-collapse-btn'; btn.title='عرض/اختصار البند'; btn.setAttribute('aria-label','عرض أو اختصار البند');
    btn.addEventListener('click',()=>{box.classList.toggle('smart-is-collapsed');});
    title.appendChild(btn);
  });
})();

// v34.36 — proportional content scaling + free placement, including the first-entry directory.
(function(){
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  function ensureInner(w){
    if(w.querySelector(':scope > .widget-inner')) return w.querySelector(':scope > .widget-inner');
    const inner=document.createElement('div'); inner.className='widget-inner';
    [...w.childNodes].forEach(n=>{
      if(n.nodeType===1 && (n.classList.contains('widget-tools')||n.classList.contains('widget-resize'))) return;
      inner.appendChild(n);
    });
    w.appendChild(inner); return inner;
  }
  function scaleInner(w){
    const inner=ensureInner(w); if(!inner)return;
    const baseW=500,baseH=650;
    const area=Math.max(1,w.offsetWidth*w.offsetHeight);
    // v34.47: هدوء في مقياس المحتوى حتى تبقى النصوص واضحة داخل اللوحات الثلاث
    // دون أن تتضخم العناصر عند زيادة ارتفاع البطاقة.
    const scale=clamp(Math.sqrt(area/(baseW*baseH)),0.88,1.18);
    w.style.setProperty('--widget-scale',scale.toFixed(3));
    inner.style.width='100%';
    inner.style.minHeight='100%';
    inner.style.zoom=scale;
    inner.style.transformOrigin='top right';
  }

  // Home dashboard v34.40: fixed 30/70 responsive layout; cards are not draggable.
  // Only the corner resize handle remains active. Grid placement is controlled by CSS.
  const home=document.querySelector('#dashboard-workspace');
  if(home){
    const key='employee_dashboard_sizes_v34_46';
    const widgets=()=>[...home.querySelectorAll(':scope > .dashboard-widget')];
    const read=()=>{try{return JSON.parse(localStorage.getItem(key)||'{}')}catch(e){return {}}};
    function save(){const state={};widgets().forEach(w=>{state[w.dataset.widgetId]={w:Math.round(w.offsetWidth),h:Math.round(w.offsetHeight)}});try{localStorage.setItem(key,JSON.stringify(state))}catch(e){}}
    function apply(){const state=read();widgets().forEach(w=>{const d=state[w.dataset.widgetId];if(d){w.style.height=Math.max(170,d.h)+'px';}})}
    let active=null;
    function resize(w,e){if(e.button!==0)return;active={w,sx:e.clientX,sy:e.clientY,h:w.offsetHeight};w.classList.add('dragging');w.setPointerCapture?.(e.pointerId);e.preventDefault();e.stopPropagation()}
    function move(e){if(!active)return;const a=active,dy=e.clientY-a.sy;a.w.style.height=Math.max(170,a.h+dy)+'px'}
    function end(){if(!active)return;active.w.classList.remove('dragging');active=null;save()}
    apply();
    widgets().forEach(w=>{
      ensureInner(w);
      let r=w.querySelector(':scope > .widget-resize');
      if(!r){r=document.createElement('span');r.className='widget-resize';r.title='تغيير الحجم';w.appendChild(r)}
      scaleInner(w);
      r.addEventListener('pointerdown',e=>resize(w,e));
    });
    document.addEventListener('pointermove',move,{passive:false});
    document.addEventListener('pointerup',end,{passive:true});
  }

  // Reusable free canvas for administration/report cards. Cards are movable anywhere and resizable from the corner.
  document.querySelectorAll('.free-card-workspace').forEach(workspace=>{
    if(workspace.classList.contains('supervisor-full-workspace')) return;
    const id=workspace.id||('workspace-'+Math.random().toString(36).slice(2));
    const key='employee_free_cards_v34_36_'+id+location.search;
    const cards=()=>[...workspace.querySelectorAll('.free-card')];
    const read=()=>{try{return JSON.parse(localStorage.getItem(key)||'{}')}catch(e){return {}}};
    function canvasSize(){const max=cards().reduce((m,c)=>Math.max(m,(parseFloat(c.style.top)||0)+(parseFloat(c.style.height)||0)),0);workspace.style.minHeight=Math.max(max+40,260)+'px'}
    function ensureControls(c){
      if(!c.querySelector(':scope > .widget-tools')){const t=document.createElement('div');t.className='widget-tools';t.innerHTML='<span class="widget-drag" title="سحب البطاقة">⋮⋮</span>';c.appendChild(t)}
      if(!c.querySelector(':scope > .widget-resize')){const r=document.createElement('span');r.className='widget-resize';r.title='تغيير الحجم';c.appendChild(r)}
      return ensureInner(c);
    }
    function place(c,x,y,w,h){const minW=220,minH=145,ww=clamp(w||340,minW,Math.max(minW,workspace.clientWidth-12));c.style.left=clamp(x||0,0,Math.max(0,workspace.clientWidth-ww))+'px';c.style.top=Math.max(0,y||0)+'px';c.style.width=ww+'px';c.style.height=Math.max(minH,h||190)+'px';scaleInner(c)}
    function initial(){const gap=18,col=Math.max(260,Math.floor((workspace.clientWidth-gap*2)/3)),row=190;cards().forEach((c,i)=>place(c,(i%3)*(col+gap),Math.floor(i/3)*(row+gap),col,row));canvasSize();save()}
    function save(){canvasSize();const state={canvasWidth:workspace.clientWidth,cards:{}};cards().forEach(c=>state.cards[c.dataset.freeCardId]={x:Math.round(c.offsetLeft),y:Math.round(c.offsetTop),w:Math.round(c.offsetWidth),h:Math.round(c.offsetHeight)});try{localStorage.setItem(key,JSON.stringify(state))}catch(e){}}
    function apply(){const state=read();if(!state.cards||!Object.keys(state.cards).length){initial();return}const ratio=workspace.clientWidth/(state.canvasWidth||workspace.clientWidth);cards().forEach((c,i)=>{const d=state.cards[c.dataset.freeCardId];if(d)place(c,d.x*ratio,d.y,d.w*ratio,d.h);else place(c,(i%3)*280,Math.floor(i/3)*210,340,190)});canvasSize()}
    let active=null;
    function down(c,e,type){if(e.button!==0)return;active={type,c,sx:e.clientX,sy:e.clientY,l:c.offsetLeft,t:c.offsetTop,w:c.offsetWidth,h:c.offsetHeight};c.classList.add('dragging');c.setPointerCapture?.(e.pointerId);e.preventDefault();e.stopPropagation()}
    function move(e){if(!active)return;const a=active,dx=e.clientX-a.sx,dy=e.clientY-a.sy;if(a.type==='drag'){a.c.style.left=clamp(a.l+dx,0,Math.max(0,workspace.clientWidth-a.w))+'px';a.c.style.top=Math.max(0,a.t+dy)+'px'}else{a.c.style.width=clamp(a.w+dx,220,Math.max(220,workspace.clientWidth-a.l))+'px';a.c.style.height=Math.max(145,a.h+dy)+'px';scaleInner(a.c)}canvasSize()}
    function end(){if(!active)return;active.c.classList.remove('dragging');active=null;save()}
    apply();cards().forEach(c=>{ensureControls(c);scaleInner(c);c.querySelector('.widget-drag')?.addEventListener('pointerdown',e=>down(c,e,'drag'));c.querySelector('.widget-resize')?.addEventListener('pointerdown',e=>down(c,e,'resize'))});
    document.addEventListener('pointermove',move,{passive:false});document.addEventListener('pointerup',end,{passive:true});window.addEventListener('resize',()=>{cards().forEach(scaleInner);save()});
  });
})();

// v35.32 — المساعد: تغيير حجم حر بدون زر + حدود الشاشة
(function(){
 const modal=document.getElementById('assistantModal'), fab=document.getElementById('assistantFab'), win=document.getElementById('assistantWindow'), bar=document.getElementById('assistantDragBar'), frame=document.getElementById('assistantFrame');
 if(!modal||!fab||!win||!bar)return;
 function keepInViewport(){
   if(window.innerWidth<=700){win.style.width='';win.style.height='';win.style.left='';win.style.top='';win.style.right='';win.style.bottom='';return;}
   const r=win.getBoundingClientRect(), pad=8;
   const maxW=window.innerWidth-pad*2, maxH=window.innerHeight-pad*2;
   if(win.offsetWidth>maxW) win.style.width=maxW+'px';
   if(win.offsetHeight>maxH) win.style.height=maxH+'px';
   const rr=win.getBoundingClientRect();
   if(rr.left<pad) win.style.left=pad+'px';
   if(rr.top<pad) win.style.top=pad+'px';
   if(rr.right>window.innerWidth-pad) win.style.left=Math.max(pad,window.innerWidth-win.offsetWidth-pad)+'px';
   if(rr.bottom>window.innerHeight-pad) win.style.top=Math.max(pad,window.innerHeight-win.offsetHeight-pad)+'px';
   win.style.right='auto'; win.style.bottom='auto';
 }
 function open(){
   modal.hidden=false; modal.style.display='block'; modal.setAttribute('aria-hidden','false');
   modal.classList.add('is-open'); fab.hidden=true;
   win.classList.remove('is-minimized'); keepInViewport();
   if(frame&&!frame.getAttribute('src'))frame.src='/assistant?embed=1';
 }
 function hide(){
   win.classList.remove('is-minimized'); modal.classList.remove('is-open');
   modal.hidden=true; modal.style.display='none'; modal.setAttribute('aria-hidden','true');
   fab.hidden=false;
 }
 fab.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();open();});

 // v35.52 — assistant: drag window by title bar only (no resize handles)
 let dragging=null;
 bar.addEventListener('pointerdown',e=>{
   if(e.button!==0)return;
   const r=win.getBoundingClientRect();
   dragging={x:e.clientX,y:e.clientY,left:r.left,top:r.top};
   win.style.position='fixed'; win.style.right='auto'; win.style.bottom='auto';
   win.classList.add('is-dragging');
   try{bar.setPointerCapture(e.pointerId)}catch(_){ }
   e.preventDefault(); e.stopPropagation();
 });
 function moveDrag(e){
   if(!dragging)return;
   e.preventDefault(); e.stopPropagation();
   const pad=8, dx=e.clientX-dragging.x, dy=e.clientY-dragging.y;
   const maxLeft=Math.max(pad,window.innerWidth-win.offsetWidth-pad);
   const maxTop=Math.max(pad,window.innerHeight-win.offsetHeight-pad);
   win.style.left=Math.round(Math.max(pad,Math.min(maxLeft,dragging.left+dx)))+'px';
   win.style.top=Math.round(Math.max(pad,Math.min(maxTop,dragging.top+dy)))+'px';
 }
 function endDrag(e){
   if(!dragging)return;
   try{if(bar.hasPointerCapture?.(e.pointerId))bar.releasePointerCapture(e.pointerId)}catch(_){ }
   dragging=null; win.classList.remove('is-dragging'); keepInViewport();
 }
 document.addEventListener('pointermove',moveDrag,{passive:false});
 document.addEventListener('pointerup',endDrag,{passive:false});
 document.addEventListener('pointercancel',endDrag,{passive:false});
 // The assistant has only two states: visible window or the floating icon. Clicking outside returns to the icon.
 document.addEventListener('pointerdown',e=>{
   if(modal.hidden || !modal.classList.contains('is-open')) return;
   if(e.target===fab || fab.contains(e.target)) return;
   if(win.contains(e.target)) return;
   hide();
 }, true);
 document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!modal.hidden)hide();});
 window.addEventListener('resize',keepInViewport);
})();
