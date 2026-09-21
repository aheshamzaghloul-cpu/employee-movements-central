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

// v34.34: free home dashboard canvas — medium defaults, free drag/resize, persistent layout.
(function(){
  const workspace=document.querySelector('#dashboard-workspace');
  if(!workspace) return;
  const key='employee_dashboard_layout_v34_34';
  const widgets=()=>[...workspace.querySelectorAll(':scope > .dashboard-widget')];
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  function read(){try{return JSON.parse(localStorage.getItem(key)||'{}')}catch(e){return {}}}
  function canvasSize(){
    const maxBottom=widgets().reduce((m,w)=>Math.max(m,(parseFloat(w.style.top)||0)+(parseFloat(w.style.height)||0)),0);
    const minHeight=Math.max(window.innerHeight-150,760);
    workspace.style.minHeight=Math.max(minHeight,maxBottom+80)+'px';
  }
  function save(){
    canvasSize();
    const state={canvasWidth:workspace.clientWidth,canvasHeight:workspace.scrollHeight,widgets:{}};
    const wr=workspace.getBoundingClientRect();
    widgets().forEach(w=>{
      state.widgets[w.dataset.widgetId]={
        x:Math.round(w.offsetLeft),y:Math.round(w.offsetTop),
        w:Math.round(w.offsetWidth),h:Math.round(w.offsetHeight)
      };
    });
    try{localStorage.setItem(key,JSON.stringify(state))}catch(e){}
  }
  function place(w,x,y,width,height){
    const minW=220,minH=145;
    const maxW=Math.max(minW,workspace.clientWidth-16);
    const ww=clamp(width||340,minW,maxW);
    const hh=Math.max(minH,height||190);
    const xx=clamp(x||0,0,Math.max(0,workspace.clientWidth-ww));
    const yy=Math.max(0,y||0);
    w.style.left=xx+'px';w.style.top=yy+'px';w.style.width=ww+'px';w.style.height=hh+'px';
  }
  function initialLayout(){
    // First visit: every widget starts at a consistent medium size.
    const width=workspace.clientWidth;
    const gap=20;
    const col=Math.max(260,Math.floor((width-gap*2)/3));
    const rowH=190;
    const positions=[
      [0,0],[col+gap,0],[2*(col+gap),0],
      [0,rowH+gap],[col+gap,rowH+gap],[2*(col+gap),rowH+gap],
      [0,2*(rowH+gap)]
    ];
    widgets().forEach((w,i)=>{
      const [x,y]=positions[i]||[0,i*(rowH+gap)];
      place(w,x,y,col,rowH);
    });
    canvasSize();
  }
  function applySaved(){
    const state=read();
    if(!state.widgets || !Object.keys(state.widgets).length){initialLayout();save();return;}
    const oldWidth=state.canvasWidth||workspace.clientWidth;
    const ratio=workspace.clientWidth>0 ? workspace.clientWidth/oldWidth : 1;
    widgets().forEach((w,i)=>{
      const d=state.widgets[w.dataset.widgetId];
      if(d){
        const ww=Math.min((d.w||340)*ratio,workspace.clientWidth-16);
        place(w,(d.x||0)*ratio,d.y||0,ww,d.h||190);
      }else{
        const col=Math.max(260,Math.floor((workspace.clientWidth-40)/3));
        place(w,(i%3)*(col+20),Math.floor(i/3)*210,col,190);
      }
    });
    canvasSize();
  }
  let active=null;
  function beginDrag(w,e){
    if(e.button!==0)return;
    const wr=workspace.getBoundingClientRect();
    active={type:'drag',w,startX:e.clientX,startY:e.clientY,left:w.offsetLeft,top:w.offsetTop,width:w.offsetWidth,height:w.offsetHeight};
    w.classList.add('dragging','widget-active');
    w.setPointerCapture?.(e.pointerId);
    e.preventDefault();
  }
  function beginResize(w,e){
    if(e.button!==0)return;
    active={type:'resize',w,startX:e.clientX,startY:e.clientY,left:w.offsetLeft,top:w.offsetTop,width:w.offsetWidth,height:w.offsetHeight};
    w.classList.add('dragging','widget-active');
    w.setPointerCapture?.(e.pointerId);
    e.preventDefault();e.stopPropagation();
  }
  function move(e){
    if(!active)return;
    const a=active,dx=e.clientX-a.startX,dy=e.clientY-a.startY;
    if(a.type==='drag'){
      const x=clamp(a.left+dx,0,Math.max(0,workspace.clientWidth-a.width));
      const y=Math.max(0,a.top+dy);
      a.w.style.left=x+'px';a.w.style.top=y+'px';
    }else{
      const minW=220,minH=145;
      const width=clamp(a.width+dx,minW,Math.max(minW,workspace.clientWidth-a.left));
      const height=Math.max(minH,a.height+dy);
      a.w.style.width=width+'px';a.w.style.height=height+'px';
    }
    canvasSize();
  }
  function end(){
    if(!active)return;
    active.w.classList.remove('dragging');
    setTimeout(()=>active&&active.w.classList.remove('widget-active'),80);
    active=null;save();
  }
  applySaved();
  widgets().forEach(w=>{
    const grip=w.querySelector('.widget-drag');
    const resize=w.querySelector('.widget-resize');
    grip?.addEventListener('pointerdown',e=>beginDrag(w,e));
    resize?.addEventListener('pointerdown',e=>beginResize(w,e));
  });
  document.addEventListener('pointermove',move,{passive:false});
  document.addEventListener('pointerup',end,{passive:true});
  window.addEventListener('resize',()=>{
    const oldWidth=read().canvasWidth||workspace.clientWidth;
    const ratio=workspace.clientWidth/oldWidth;
    widgets().forEach(w=>{
      const x=clamp(w.offsetLeft*ratio,0,Math.max(0,workspace.clientWidth-w.offsetWidth));
      w.style.left=x+'px';
    });
    canvasSize();save();
  });
})();
