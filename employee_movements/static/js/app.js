(function(){
  const qs=(s,r=document)=>r.querySelector(s), qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const notify=(message,type='warning')=>{ if(typeof window.toast==='function') window.toast(message,type); else setTimeout(()=>{ if(typeof window.toast==='function') window.toast(message,type); },0); };

  // Keep movement row menus compact and predictable: only one may be open,
  // outside clicks dismiss it, and Escape restores focus to its trigger.
  const movementActionMenus=qsa('details.movement-row-action-menu');
  movementActionMenus.forEach(menu=>menu.addEventListener('toggle',()=>{
    if(menu.open) movementActionMenus.forEach(other=>{if(other!==menu)other.open=false;});
  }));
  if(movementActionMenus.length){
    document.addEventListener('click',event=>{
      if(!(event.target instanceof Element)||event.target.closest('.movement-row-action-menu'))return;
      movementActionMenus.forEach(menu=>{menu.open=false;});
    });
    document.addEventListener('keydown',event=>{
      if(event.key!=='Escape')return;
      const opened=movementActionMenus.find(menu=>menu.open);
      if(!opened)return;
      event.preventDefault();opened.open=false;opened.querySelector('summary')?.focus({preventScroll:true});
    });
  }

  // Accessible password visibility control shared by sign-in and account forms.
  qsa('[data-password-toggle]').forEach(toggle=>{
    const targetId=toggle.dataset.passwordToggle;
    const input=targetId?document.getElementById(targetId):null;
    if(!input) return;
    toggle.addEventListener('click',()=>{
      const reveal=input.type==='password';
      input.type=reveal?'text':'password';
      toggle.textContent=reveal?'إخفاء':'إظهار';
      toggle.setAttribute('aria-pressed',String(reveal));
      toggle.setAttribute('aria-label',reveal?'إخفاء كلمة المرور':'إظهار كلمة المرور');
      input.focus({preventScroll:true});
    });
  });

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

  // Employees page: selecting a governorate/branch refreshes the native employee suggestions.
  const empSearchForm=qs('#employees-search-form');
  const empGov=qs('#employee_governorate_filter');
  const empBranch=qs('#employee_branch_filter');
  if(empSearchForm && (empGov || empBranch)){
    [empGov,empBranch].filter(Boolean).forEach(el=>el.addEventListener('change',()=>empSearchForm.submit()));
  }

  // Roles control which scope groups are required/visible.
  qsa('form').forEach(form=>{
    const roleBoxes=qsa('input[type=checkbox][name="roles"]',form);
    if(!roleBoxes.length)return;
    function syncRoles(){
      const roles=roleBoxes.filter(x=>x.checked).map(x=>x.value);
      qsa('[data-role-scope="supervisor"]',form).forEach(x=>x.hidden=!roles.includes('مشرف محافظة'));
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
      if(!boxes(name,form).some(x=>x.checked)){e.preventDefault(); notify('يجب اختيار عنصر واحد على الأقل.','warning'); return;}
    }
  }));

  // Movement dynamic fields and automatic approver by dependency.
  const movementType=qs('#movement_type'), movementEmployee=qs('#movement_employee');
  function syncMovement(){
    const v=movementType?.value||'';
    qsa('[data-movement]').forEach(el=>{const types=[el.dataset.movement,el.dataset.movement2].filter(Boolean); el.hidden=!types.includes(v);});
    const isLeave=v==='إجازة', isAssignment=v==='انتداب', isPermission=v==='إذن';
    const hasDateRange=v==='إجازة'||v==='انتداب';
    const leave=qs('#leave_type'), gov=qs('#destination_governorate_id'), dest=qs('#destination_branch_id');
    const fd=qs('#from_date'), td=qs('#to_date'), pd=qs('#permission_date');
    const openAssignment=qs('#open_assignment'), isOpenAssignment=isAssignment&&!!openAssignment?.checked;
    const endWrap=qs('#to_date_wrap');
    if(endWrap)endWrap.hidden=!hasDateRange||(isAssignment&&isOpenAssignment);

    // Hidden fields must not participate in native validation or be posted as
    // stale values for a different movement type. Their values are retained so
    // switching back to a type does not needlessly erase the user's draft.
    if(leave){leave.required=isLeave;leave.disabled=!isLeave;}
    if(gov){gov.required=isAssignment;gov.disabled=!isAssignment;}
    if(dest){dest.required=isAssignment;dest.disabled=!isAssignment||!gov?.value;}
    if(fd){fd.required=hasDateRange;fd.disabled=!hasDateRange;}
    if(td){
      td.required=(v==='إجازة')||(v==='انتداب'&&!isOpenAssignment);
      td.disabled=!hasDateRange||isOpenAssignment;
      td.min=hasDateRange?(fd?.value||''):'';
      // Preserve the end-date draft when toggling an assignment open/closed.
      // Disabled controls are not submitted, and the server explicitly stores
      // no end date for an open assignment, so retaining this UI draft is safe.
      const dateError=hasDateRange&&fd?.value&&td.value&&td.value<fd.value;
      td.setCustomValidity(dateError?'تاريخ النهاية يجب ألا يسبق تاريخ البداية.':'');
      if(dateError){td.setAttribute('aria-invalid','true');}
      else td.removeAttribute('aria-invalid');
    }
    if(pd){pd.required=isPermission;pd.disabled=!isPermission;}
    if(openAssignment)openAssignment.disabled=!isAssignment;
    const days=qs('#movement_days');
    if(days){if(isPermission){days.textContent='—';} else if(fd?.value&&td?.value&&!isOpenAssignment){const a=new Date(fd.value),b=new Date(td.value);days.textContent=b>=a?Math.floor((b-a)/86400000)+1:'—';} else days.textContent='—';}
    const hint=qs('#movement_duration_hint'); if(hint)hint.textContent=isPermission?'الإذن يُسجل بتاريخ واحد.':isOpenAssignment?'الانتداب المفتوح لا يحتاج تاريخ نهاية.':'تحسب تلقائيًا من تاريخ البداية حتى النهاية.';
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
  movementType?.addEventListener('change',syncMovement); ['#from_date','#to_date'].forEach(s=>qs(s)?.addEventListener('input',syncMovement)); qs('#open_assignment')?.addEventListener('change',syncMovement); movementEmployee?.addEventListener('change',syncAutoApprover);
  syncMovement(); syncAutoApprover();
  const movementForm=qs('#movement_form');
  movementForm?.addEventListener('submit',e=>{if(movementEmployee&&!movementEmployee.value){e.preventDefault();notify('يجب اختيار الموظف.','warning');}});

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

  // Shared HTML escaping for dynamic movement-picker labels.
  function esc(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}

  // Homepage global employee search: live identity suggestions; server-side filters remain authoritative.
  const homeSearchForm=qs('#homeEmployeeSearchForm');
  const homeSearchInput=homeSearchForm?.querySelector('[name="movement_name"]');
  const homeSearchGov=qs('#homeSearchGovernorate'), homeSearchBranch=qs('#homeSearchBranch');
  const homeLiveResults=qs('#homeEmployeeLiveResults');
  let homeLiveTimer=null, homeLiveSequence=0;
  const searchNorm=window.normalizeEmployeeSearchText||((v)=>String(v||'').toLocaleLowerCase('ar').trim());
  function hideHomeLive(){if(homeLiveResults){homeLiveResults.hidden=true;homeLiveResults.innerHTML='';}}
  function renderHomeLive(items, query){
    if(!homeLiveResults)return;
    if(!items.length){homeLiveResults.innerHTML='<div class="smart-empty compact">لا توجد نتائج مطابقة. جرّب الاسم أو الكود أو غيّر مرشحات المحافظة والفرع.</div>';homeLiveResults.hidden=false;return;}
    const paramsFor=(id)=>{const p=new URLSearchParams();p.set('movement_name',query);if(homeSearchGov?.value)p.set('movement_governorate_id',homeSearchGov.value);if(homeSearchBranch?.value)p.set('movement_branch_id',homeSearchBranch.value);p.set('employee_id',String(id));return '/?'+p.toString()+'#employee-search';};
    homeLiveResults.innerHTML=items.map(e=>`<a href="${esc(paramsFor(e.id))}"><i>${esc((e.name||'م').slice(0,1))}</i><span><b>${esc(e.name)}</b><small>${esc(e.job_title||'وظيفة غير مسجلة')} · كود شئون العاملين: ${esc(e.code||'—')}</small><small>${esc(e.employment_status||'حالة غير مسجلة')} · التعيين: ${esc(e.hire_date||'غير مسجل')} · العودة: ${esc(e.rehire_date||'غير مسجل')} · الاستقالة: ${esc(e.resignation_date||'غير مسجل')}</small><small>هاتف العمل: ${esc(e.company_phone||'غير مسجل')} · الشخصي: ${esc(e.personal_phone||'غير مسجل')}</small><small>البريد الإلكتروني: ${esc(e.email||'غير مسجل')}</small><small class="smart-entry-contact-inline${e.entry_responsible_status==='conflict'?' is-conflict':''}"><b>مسؤول إدخال الفرع:</b> ${esc(e.entry_responsible||'غير محدد')}</small><small><b>آخر انتداب:</b> ${esc(e.last_assignment||'لا يوجد انتداب مسجل')}</small>${e.match_kind==='approximate'?'<small class="smart-match-caution">اقتراح قريب — تأكد من الهوية</small>':''}</span><em>${esc(e.branch||'—')}${e.branch_code?' · '+esc(e.branch_code):''} · ${esc(e.governorate||'—')}</em></a>`).join('');
    homeLiveResults.hidden=false;
  }
  async function runHomeLiveSearch(){
    const raw=(homeSearchInput?.value||'').trim(), q=searchNorm(raw), seq=++homeLiveSequence;
    if(q.length<2&&!homeSearchBranch?.value){hideHomeLive();return;}
    if(raw.length>120){homeLiveResults.innerHTML='<div class="smart-empty compact">الحد الأقصى لعبارة البحث 120 حرفًا.</div>';homeLiveResults.hidden=false;return;}
    homeLiveResults.innerHTML='<div class="smart-empty compact">جارٍ البحث…</div>';homeLiveResults.hidden=false;
    const params=new URLSearchParams({q:raw});if(homeSearchGov?.value)params.set('governorate_id',homeSearchGov.value);if(homeSearchBranch?.value)params.set('branch_id',homeSearchBranch.value);
    try{const response=await fetch('/employee-search?'+params.toString(),{headers:{Accept:'application/json'}});if(!response.ok)throw new Error('search_failed');const data=await response.json();if(seq===homeLiveSequence)renderHomeLive(data.results||[],raw);}
    catch(_){if(seq===homeLiveSequence){homeLiveResults.innerHTML='<div class="smart-empty compact">تعذر تنفيذ البحث الآن. استخدم زر «بحث» لإعادة المحاولة.</div>';homeLiveResults.hidden=false;}}
  }
  function syncHomeSearchBranches(){
    if(!homeSearchBranch)return;
    const gid=homeSearchGov?.value||'';
    [...homeSearchBranch.options].forEach(option=>{
      if(!option.value)return;
      const ok=!gid||option.dataset.governorate===gid;
      option.hidden=!ok;option.disabled=!ok;
    });
    if(homeSearchBranch.value&&homeSearchBranch.selectedOptions[0]?.disabled)homeSearchBranch.value='';
  }
  homeSearchGov?.addEventListener('change',()=>{syncHomeSearchBranches();clearTimeout(homeLiveTimer);homeLiveTimer=setTimeout(runHomeLiveSearch,0);});
  homeSearchBranch?.addEventListener('change',()=>{
    if(homeSearchBranch.value&&homeSearchGov){const option=homeSearchBranch.selectedOptions[0];if(option?.dataset.governorate)homeSearchGov.value=option.dataset.governorate;}
    syncHomeSearchBranches();clearTimeout(homeLiveTimer);homeLiveTimer=setTimeout(runHomeLiveSearch,0);
  });
  homeSearchInput?.addEventListener('input',()=>{clearTimeout(homeLiveTimer);homeLiveTimer=setTimeout(runHomeLiveSearch,180);});
  syncHomeSearchBranches();
  homeSearchInput?.addEventListener('keydown',e=>{if(e.key==='Escape')hideHomeLive();});
  homeSearchForm?.addEventListener('submit',()=>hideHomeLive());

  // Unified interaction layer: confirmations, search feedback, submit states and validation focus.
  function ensureConfirmDialog(){
    let root=qs('#interactiveConfirm');
    if(root)return root;
    root=document.createElement('div'); root.id='interactiveConfirm'; root.className='interactive-confirm'; root.hidden=true;
    root.innerHTML='<div class="interactive-confirm-backdrop" data-confirm-cancel></div><section class="interactive-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="interactiveConfirmTitle"><div class="interactive-confirm-mark">!</div><div class="interactive-confirm-copy"><strong id="interactiveConfirmTitle">تأكيد الإجراء</strong><p id="interactiveConfirmMessage"></p></div><div class="interactive-confirm-actions"><button type="button" class="ui-btn" data-confirm-cancel>إلغاء</button><button type="button" class="ui-btn ui-btn-primary" id="interactiveConfirmOk">متابعة</button></div></section>';
    document.body.appendChild(root); return root;
  }
  let pendingConfirm=null;
  function askConfirm(el){
    const root=ensureConfirmDialog(); qs('#interactiveConfirmMessage',root).textContent=el.dataset.confirm||'هل تريد متابعة هذا الإجراء؟';
    root.hidden=false; document.body.classList.add('interactive-confirm-open'); pendingConfirm=el; qs('#interactiveConfirmOk',root)?.focus();
  }
  function closeConfirm(){const root=qs('#interactiveConfirm');if(!root)return;root.hidden=true;document.body.classList.remove('interactive-confirm-open');pendingConfirm=null;}
  document.addEventListener('click',e=>{
    const cancel=e.target.closest('[data-confirm-cancel]'); if(cancel){closeConfirm();return;}
    const ok=e.target.closest('#interactiveConfirmOk');
    if(ok&&pendingConfirm){const el=pendingConfirm;closeConfirm();if(el.form){el.dataset.confirmApproved='1';el.form.requestSubmit(el);delete el.dataset.confirmApproved;}else if(el.href){window.location.href=el.href;}return;}
    const target=e.target.closest('[data-confirm]');
    if(target&&target.dataset.confirmApproved!=='1'){e.preventDefault();e.stopImmediatePropagation();askConfirm(target);}
  },true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!qs('#interactiveConfirm')?.hidden)closeConfirm();});

  qsa('[data-auto-search]').forEach(input=>{
    const target=input.dataset.autoSearch;
    const table=target?qs(target):null;
    if(!table)return;
    const body=table.tBodies?.[0]; if(!body)return;
    const rows=[...body.rows].filter(row=>!row.classList.contains('ui-empty')&&!row.querySelector('th'));
    let status=input.parentElement?.querySelector('.interactive-search-count');
    if(!status){status=document.createElement('span');status.className='interactive-search-count';input.insertAdjacentElement('afterend',status);}
    let empty=table.parentElement?.querySelector('.search-filter-empty');
    if(!empty){empty=document.createElement('div');empty.className='search-filter-empty ui-empty';empty.hidden=true;empty.textContent='لا توجد نتائج مطابقة للبحث.';table.insertAdjacentElement('afterend',empty);}
    const normalize=window.normalizeEmployeeSearchText||((v)=>String(v||'').toLocaleLowerCase('ar').trim());
    const sourceRows=[...rows];
    const rowSearchText=row=>window.getEmployeeSearchableRowText?window.getEmployeeSearchableRowText(row,table):(row.textContent||'');
    const pageSize=Math.max(5,Math.min(50,Number.parseInt(table.dataset.pageSize||'10',10)||10));
    let expanded=false;
    let previousQuery='';
    let more=table.parentElement?.querySelector(':scope > .smart-data-more');
    if(!more){more=document.createElement('button');more.type='button';more.className='ui-btn ui-btn-secondary ui-btn-mini smart-data-more';more.hidden=true;more.setAttribute('aria-controls',table.id);table.insertAdjacentElement('afterend',more);}
    input.maxLength=120;
    function render(){
      const q=normalize(input.value);if(q!==previousQuery){expanded=false;previousQuery=q;}
      const matches=sourceRows.filter(row=>!q||window.employeeSearchMatches(q,rowSearchText(row)));
      const visibleLimit=expanded?matches.length:pageSize;
      const visibleSet=new Set(matches.slice(0,visibleLimit));
      sourceRows.forEach(row=>{row.hidden=!visibleSet.has(row);});
      const blank=body.querySelector('.ui-empty');if(blank)blank.hidden=!!q;
      const shown=Math.min(visibleLimit,matches.length);
      status.textContent=q?`عرض ${shown} من ${matches.length} نتيجة`:`عرض ${shown} من ${sourceRows.length} سجل`;
      more.hidden=matches.length<=pageSize;
      more.textContent=expanded?'عرض أقل':`عرض المزيد (${Math.max(0,matches.length-pageSize)})`;
      more.setAttribute('aria-expanded',String(expanded));
      empty.hidden=!q||matches.length>0;
      input.setAttribute('aria-controls',table.id);
      if(!empty.id)empty.id=table.id+'-search-empty';
      input.setAttribute('aria-describedby',empty.id);
    }
    input.addEventListener('input',render);more.addEventListener('click',()=>{expanded=!expanded;render();});render();
  });

  qsa('form').forEach(form=>form.addEventListener('submit',()=>{
    if(form.dataset.noBusy==='1')return;
    qsa('button[type=submit],input[type=submit]',form).filter(x=>!x.disabled).forEach(btn=>{btn.disabled=true;btn.setAttribute('aria-busy','true');if(btn.tagName==='BUTTON'){btn.dataset.originalLabel=btn.innerHTML;btn.innerHTML='<span class="interactive-spinner" aria-hidden="true"></span> جارٍ التنفيذ…';}});
  }));
  document.addEventListener('invalid',e=>{const field=e.target;if(field&&typeof field.focus==='function')setTimeout(()=>field.focus({preventScroll:false}),0);},true);

  // Filter branch dropdown by governorate on employee list.
  const fg=qs('#employee_governorate_filter'), fb=qs('#employee_branch_filter'); if(fg&&fb){const sync=()=>{[...fb.options].forEach(o=>{if(!o.value)return;const ok=!fg.value||o.dataset.governorate===fg.value;o.hidden=!ok;o.disabled=!ok});if(fb.value&&fb.selectedOptions[0]?.disabled)fb.value='';};fg.addEventListener('change',sync);sync();}
  // Smart employee profile: instant movement filtering without a reload.
  const historyRoot=qs('#employee_history_table'), historySearch=qs('#employee_history_search'), historyNo=qs('#history_no_match'), historyCount=qs('#history_search_count');
  if(historyRoot){
    const historyRows=qsa('.smart-history-row',historyRoot), historyButtons=qsa('[data-history-filter]');
    let historyFilter='all';
    const applyHistory=()=>{
      const norm=window.normalizeEmployeeSearchText||((v)=>String(v||'').toLowerCase().trim()); const q=norm(historySearch?.value); let shown=0;
      historyRows.forEach(row=>{
        const okType=historyFilter==='all'||row.dataset.movementType===historyFilter;
        const okText=!q||window.employeeSearchMatches(q,row.innerText);
        row.hidden=!(okType&&okText); if(okType&&okText)shown++;
      });
      if(historyNo) historyNo.hidden=shown!==0;
      if(historyCount)historyCount.textContent=`${shown} من ${historyRows.length} حركة`;
    };
    historyButtons.forEach(btn=>btn.addEventListener('click',()=>{historyFilter=btn.dataset.historyFilter;historyButtons.forEach(x=>{x.classList.toggle('is-active',x===btn);x.setAttribute('aria-pressed',String(x===btn));});applyHistory();}));
    historySearch?.addEventListener('input',applyHistory);
    applyHistory();
  }
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
      if(!c.querySelector(':scope > .widget-tools')){const t=document.createElement('div');t.className='widget-tools';t.innerHTML='<span class="widget-drag" title="سحب البطاقة" aria-label="سحب البطاقة"><svg class="ui-icon" viewBox="0 0 24 24"><path d="M8 5h.01M8 12h.01M8 19h.01M16 5h.01M16 12h.01M16 19h.01"></path></svg></span>';c.appendChild(t)}
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



// v67.7 — smart data surfaces: search, counts and focus without changing server-side workflows.
(function(){
  const norm=window.normalizeEmployeeSearchText||((v)=>String(v||'').toLocaleLowerCase('ar').trim());
  let generatedSmartTableId=0;
  document.querySelectorAll('table[data-smart-table]').forEach(table=>{
    if(table.closest('[data-report-employee]')) return;
    if(table.dataset.smartReady==='1') return;
    const body=table.tBodies?.[0]; if(!body) return;
    const rows=[...body.rows].filter(r=>!r.classList.contains('ui-empty')&&!r.querySelector('th'));
    if(!rows.length) return;
    table.dataset.smartReady='1';
    const scrollSurface=table.closest('.ui-overflow-auto');
    const wrap=table.closest('.ui-table-wrap') || scrollSurface?.parentElement || table.parentElement;
    if(!wrap) return;
    const surface=scrollSurface || table;
    const head=table.tHead;
    const title=(wrap.querySelector('.ui-section-title h3')||wrap.querySelector('h2,h3'))?.textContent?.trim() || 'البيانات';
    const serverPaginated=table.dataset.smartServerPage === 'true';
    let bar=wrap.querySelector(':scope > .smart-data-toolbar');
    if(!bar){
      bar=document.createElement('div'); bar.className='smart-data-toolbar';
      const searchScopeLabel=serverPaginated?'الصفحة الحالية فقط':'البيانات المعروضة';
      const searchTitle=serverPaginated?'البحث محلي داخل صفحة الخادم الحالية فقط':'تصفية محلية للبيانات المعروضة';
      bar.innerHTML=`<div class="smart-data-summary"><strong>${title}</strong><span data-smart-count></span></div><label class="smart-data-search"><span class="sr-only">بحث داخل ${searchScopeLabel}</span><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"></circle><path d="m16 16 4 4"></path></svg><input type="search" data-smart-table-search placeholder="${table.dataset.smartSearchPlaceholder || 'بحث داخل البيانات…'}" title="${searchTitle}" aria-label="بحث داخل ${searchScopeLabel}" autocomplete="off"></label>`;
      wrap.insertBefore(bar,surface);
    }
    const input=bar.querySelector('[data-smart-table-search]');
    if(input){
      input.maxLength=120;
      if(!table.id){
        let candidate='';
        do { candidate='smart-table-search-'+(++generatedSmartTableId); }
        while(document.getElementById(candidate));
        table.id=candidate;
      }
    }
    const count=bar.querySelector('[data-smart-count]');
    let empty=wrap.querySelector(':scope > .search-filter-empty');
    if(!empty){empty=document.createElement('div');empty.className='search-filter-empty ui-empty';empty.hidden=true;empty.textContent='لا توجد نتائج مطابقة للبحث.';surface.insertAdjacentElement('afterend',empty);}
    const existingSearch=wrap.querySelector('[data-auto-search]');
    if(existingSearch){ bar.hidden=true; return; }
    const pageSize=Math.max(5,Math.min(50,Number.parseInt(table.dataset.pageSize||'10',10)||10));
    let expanded=false,previousQuery='';
    let more=wrap.querySelector(':scope > .smart-data-more');
    if(!more){more=document.createElement('button');more.type='button';more.className='ui-btn ui-btn-secondary ui-btn-mini smart-data-more';more.hidden=true;surface.insertAdjacentElement('afterend',more);}
    const rowSearchText=row=>window.getEmployeeSearchableRowText?window.getEmployeeSearchableRowText(row,table):(row.textContent||'');
    function render(){
      const q=norm(input?.value);if(q!==previousQuery){expanded=false;previousQuery=q;}
      const matches=rows.filter(row=>!q||window.employeeSearchMatches(q,rowSearchText(row)));
      const visibleLimit=expanded?matches.length:pageSize;
      const visibleSet=new Set(matches.slice(0,visibleLimit));
      rows.forEach(row=>{row.hidden=!visibleSet.has(row)});
      const visible=Math.min(visibleLimit,matches.length);
      if(count) count.textContent=serverPaginated ? `عرض ${visible} من ${matches.length} في الصفحة الحالية` : `عرض ${visible} من ${matches.length}`;
      more.hidden=matches.length<=pageSize;
      more.textContent=expanded?'عرض أقل':`عرض المزيد (${Math.max(0,matches.length-pageSize)})`;
      more.setAttribute('aria-controls',table.id);more.setAttribute('aria-expanded',String(expanded));
      empty.hidden=!q||matches.length>0;
      if(input){input.setAttribute('aria-controls',table.id);if(!empty.id)empty.id=table.id+'-search-empty';input.setAttribute('aria-describedby',empty.id);}
      table.classList.toggle('has-smart-filter',!!q);
    }
    input?.addEventListener('input',render);more.addEventListener('click',()=>{expanded=!expanded;render();});
    // Print every row matching the current local search, not just the first
    // progressive page. Remember and restore the user's expanded/collapsed UI
    // state after the print dialog closes.
    let expandedBeforePrint = null;
    window.addEventListener('beforeprint',()=>{
      if(expandedBeforePrint !== null)return;
      expandedBeforePrint = expanded;
      expanded = true;
      render();
    });
    window.addEventListener('afterprint',()=>{
      if(expandedBeforePrint === null)return;
      expanded = expandedBeforePrint;
      expandedBeforePrint = null;
      render();
    });
    render();
    if(head) head.classList.add('smart-table-head');
  });
  document.querySelectorAll('[data-report-search-root]').forEach(root=>{
    const input=root.querySelector('[data-report-search]');
    const groups=[...root.querySelectorAll('[data-report-employee]')];
    const count=root.querySelector('[data-report-search-count]');
    const empty=root.querySelector('[data-report-search-empty]');
    if(!input||!groups.length)return;
    const norm=window.normalizeEmployeeSearchText||((v)=>String(v||'').toLocaleLowerCase('ar').trim());
    const pageSize=8;let expanded=false,previousQuery='';
    let more=root.querySelector('[data-report-search-more]');
    if(!more){more=document.createElement('button');more.type='button';more.className='ui-btn ui-btn-secondary ui-btn-mini smart-data-more';more.dataset.reportSearchMore='';groups[groups.length-1].insertAdjacentElement('afterend',more);}
    input.maxLength=120;
    function render(){
      const q=norm(input.value);if(q!==previousQuery){expanded=false;previousQuery=q;}
      const matches=[];let totalMatchedRows=0;
      groups.forEach(group=>{
        const identity=norm(group.dataset.employeeSearch||'');
        const table=group.querySelector('table');
        const rows=[...(table?.tBodies?.[0]?.rows||[])].filter(row=>!row.classList.contains('ui-empty')&&!row.querySelector('th'));
        const identityMatch=!q||window.employeeSearchMatches(q,identity);let matchedRows=0;
        rows.forEach(row=>{
          const rowText=window.getEmployeeSearchableRowText?window.getEmployeeSearchableRowText(row,table):(row.textContent||'');
          const match=!q||identityMatch||window.employeeSearchMatches(q,rowText);row.hidden=!match;if(match)matchedRows++;
        });
        const matchGroup=!q||identityMatch||matchedRows>0;
        if(matchGroup){matches.push({group,matchedRows});totalMatchedRows+=matchedRows;}
      });
      const shownGroups=expanded?matches:matches.slice(0,pageSize);
      const visibleGroups=new Set(shownGroups.map(x=>x.group));
      groups.forEach(group=>{group.hidden=!visibleGroups.has(group);});
      const visibleRows=shownGroups.reduce((n,x)=>n+x.matchedRows,0);
      if(count)count.textContent=`عرض ${shownGroups.length} من ${matches.length} موظف · ${visibleRows} حركة ظاهرة`;
      if(empty)empty.hidden=matches.length>0;
      more.hidden=matches.length<=pageSize;
      more.textContent=expanded?'عرض أقل':`عرض المزيد (${Math.max(0,matches.length-pageSize)})`;
      more.setAttribute('aria-expanded',String(expanded));
      if(!root.id)root.id='report-search-groups';
      more.setAttribute('aria-controls',root.id);
    }
    input.addEventListener('input',render);more.addEventListener('click',()=>{expanded=!expanded;render();});render();
  });

  // v68.30 — progressive discovery for remaining card-based workspaces.
  document.querySelectorAll('[data-progressive-list]').forEach(root=>{
    const selector=root.dataset.progressiveItemSelector||'[data-progressive-item]';
    const items=[...root.querySelectorAll(selector)];
    const container=root.querySelector('[data-progressive-container]')||root.querySelector('.ui-person-control-grid,.interactive-notification-list');
    if(!items.length||!container)return;
    const search=root.querySelector('[data-progressive-search]');
    const count=root.querySelector('[data-progressive-count]');
    const pageSize=Math.max(4,Math.min(30,Number.parseInt(root.dataset.pageSize||'8',10)||8));
    let expanded=false,previousQuery='';
    let more=root.querySelector('[data-progressive-more]');
    if(!more){more=document.createElement('button');more.type='button';more.className='ui-btn ui-btn-secondary ui-btn-mini smart-data-more';more.dataset.progressiveMore='';more.hidden=true;container.insertAdjacentElement('afterend',more);}
    let empty=root.querySelector('[data-progressive-empty]');
    if(!empty){empty=document.createElement('div');empty.className='ui-empty';empty.dataset.progressiveEmpty='';empty.hidden=true;empty.textContent='لا توجد عناصر تطابق البحث.';container.insertAdjacentElement('afterend',empty);}
    const normalize=window.normalizeEmployeeSearchText||((v)=>String(v||'').toLocaleLowerCase('ar').trim());
    function render(){
      const q=normalize(search?.value||'');if(q!==previousQuery){expanded=false;previousQuery=q;}
      const matches=items.filter(item=>!q||window.employeeSearchMatches(q,item.dataset.search||item.textContent||''));
      const limit=expanded?matches.length:pageSize;
      const visibleSet=new Set(matches.slice(0,limit));
      items.forEach(item=>{item.hidden=!visibleSet.has(item);});
      if(count)count.textContent=`عرض ${Math.min(limit,matches.length)} من ${matches.length}`;
      more.hidden=matches.length<=pageSize;
      more.textContent=expanded?'عرض أقل':`عرض المزيد (${Math.max(0,matches.length-pageSize)})`;
      more.setAttribute('aria-expanded',String(expanded));
      if(search){search.maxLength=120;search.setAttribute('aria-controls',container.id||(container.id='progressive-list-'+Math.random().toString(36).slice(2,8)));}
      empty.hidden=matches.length>0;
    }
    search?.addEventListener('input',render);
    more.addEventListener('click',()=>{expanded=!expanded;render();});
    render();
  });
})();


// v68.78.0 — dismissible server feedback with predictable focus handling.
(function () {
  document.addEventListener('click', function (event) {
    const trigger = event.target.closest('[data-dismiss-alert]');
    if (!trigger) return;
    const alert = trigger.closest('.enterprise-alert, .ui-alert, .alert');
    if (!alert) return;
    const remaining = Array.from(document.querySelectorAll('[data-dismiss-alert]'))
      .filter((button) => button !== trigger && !button.closest('[hidden]'))
      .find((button) => button.isConnected);
    alert.remove();
    if (remaining) {
      remaining.focus({ preventScroll: true });
      return;
    }
    const main = document.getElementById('main');
    if (main) {
      const addedTabIndex = !main.hasAttribute('tabindex');
      if (addedTabIndex) main.setAttribute('tabindex', '-1');
      main.focus({ preventScroll: true });
      if (addedTabIndex) main.addEventListener('blur', () => main.removeAttribute('tabindex'), { once: true });
    }
  });
})();

// v68.78.0 — keep employee-profile movement menus keyboard and pointer friendly.
(function () {
  const selector = '[data-employee-movement-menu]';
  const openSelector = '[data-employee-movement-menu][open]';
  document.addEventListener('click', function (event) {
    document.querySelectorAll(openSelector).forEach((menu) => {
      if (!menu.contains(event.target)) menu.open = false;
      else if (event.target.closest('.smart-employee-register-options a')) menu.open = false;
    });
  });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    const menus = Array.from(document.querySelectorAll(openSelector));
    if (!menus.length) return;
    const activeMenu = menus.find((menu) => menu.contains(document.activeElement)) || menus[0];
    menus.forEach((menu) => { menu.open = false; });
    const summary = activeMenu.querySelector(':scope > summary');
    if (summary) {
      event.preventDefault();
      summary.focus({ preventScroll: true });
    }
  });
})();
