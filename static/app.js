(function(){
  function qs(s){return document.querySelector(s)}
  const type=qs('input[name=movement_type]:checked');
  function checkedValue(name){const x=document.querySelector('input[name="'+name+'"]:checked'); return x?x.value:'';}
  function syncMovement(){
    const type=qs('input[name=movement_type]:checked');
    if(!type) return;
    const v=type.value;
    document.querySelectorAll('[data-movement]').forEach(el=>{const a=[el.dataset.movement,el.dataset.movement2].filter(Boolean); el.hidden=!a.includes(v)});
    document.querySelectorAll('.smart-fields input,.smart-fields select').forEach(el=>{const wrap=el.closest('[data-movement]'); if(wrap && wrap.hidden){el.required=false; if(el.tagName==='SELECT') el.value=''; else if(el.type!=='checkbox') el.value='';}});
    const leave=checkedValue('leave_type'), dest=checkedValue('destination_branch_id'), fd=qs('#from_date'), td=qs('#to_date'), pd=qs('#permission_date');
    const leaveGroup=document.querySelector('[data-choice-group="leave_type"]');
    const destGroup=document.querySelector('[data-choice-group="destination_branch_id"]');
    if(leaveGroup) leaveGroup.dataset.required=v==='إجازة'?'1':'0';
    if(destGroup) destGroup.dataset.required=v==='انتداب'?'1':'0';
    if(fd) fd.required=(v==='إجازة'||v==='انتداب');
    if(td) td.required=(v==='إجازة'||v==='انتداب');
    if(pd) pd.required=(v==='إذن');
    const days=qs('#movement_days'), durationHint=qs('#movement_duration_hint');
    if(days){
      if(v==='إذن'){days.textContent='—'; if(durationHint) durationHint.textContent='الإذن يُسجل بتاريخ واحد.'; return}
      const a=fd&&fd.value?new Date(fd.value):null,b=td&&td.value?new Date(td.value):null;
      days.textContent=(a&&b&&b>=a)?Math.floor((b-a)/86400000)+1:'—';
      if(durationHint) durationHint.textContent=v==='انتداب'?'تحسب تلقائيًا من تاريخ البداية حتى النهاية.':'تحسب تلقائيًا من تاريخ البداية حتى النهاية.';
    }
  }
  ['change','input'].forEach(ev=>document.addEventListener(ev,function(e){if(e.target.matches('input[name=movement_type],input[name=leave_type],input[name=destination_branch_id],#from_date,#to_date')) syncMovement()}));
  syncMovement();
  const homeSearch=qs('#home_employee_search'), homeResults=qs('#home_search_results'), homeEmpty=qs('#home_search_empty');
  let searchTimer=null, searchSeq=0;
  function hideHomeSearch(){ if(homeResults){homeResults.hidden=true; homeResults.innerHTML='';} if(homeEmpty) homeEmpty.hidden=true; }
  function renderHomeResults(items){
    if(!homeResults || !homeEmpty) return;
    homeEmpty.hidden=items.length!==0;
    if(!items.length){homeResults.hidden=true; return;}
    const movementCard=(title,item,cls)=>item?`<div class="search-movement ${cls}"><span>${title}</span><b>${escapeHtml(item.label)}</b><small>${escapeHtml(item.detail||'—')}</small></div>`:`<div class="search-movement ${cls} muted"><span>${title}</span><b>لا توجد بيانات</b><small>—</small></div>`;
    homeResults.innerHTML=items.map(x=>`<a class="search-result" href="/employee/${x.id}"><div class="search-person"><strong>${escapeHtml(x.name)}</strong><small>كود: ${escapeHtml(x.code)} — ${escapeHtml(x.branch)}</small></div><div class="search-movements">${movementCard('آخر إجازة',x.last_leave,'leave')}${movementCard('آخر انتداب',x.last_assignment,'assign')}${movementCard('آخر إذن',x.last_permission,'permit')}</div><span class="search-code">فتح البطاقة ←</span></a>`).join('');
    homeResults.hidden=false;
  }
  function escapeHtml(v){return String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','\"':'&quot;'}[c]));}
  async function doHomeSearch(){
    const q=(homeSearch?.value||'').trim();
    if(q.length<2){hideHomeSearch();return;}
    const seq=++searchSeq;
    if(homeResults){homeResults.hidden=false;homeResults.innerHTML='<div class="search-loading">جاري البحث…</div>';}
    try{const r=await fetch('/employee-search?q='+encodeURIComponent(q),{headers:{'Accept':'application/json'}}); const data=await r.json(); if(seq===searchSeq) renderHomeResults(data.results||[]);}
    catch(e){if(seq===searchSeq){homeResults.hidden=false;homeResults.innerHTML='<div class="search-loading">تعذر تنفيذ البحث. حاول مرة أخرى.</div>';}}
  }
  if(homeSearch){
    homeSearch.addEventListener('input',function(){clearTimeout(searchTimer); searchTimer=setTimeout(doHomeSearch,220);});
    homeSearch.addEventListener('keydown',function(e){if(e.key==='Escape') hideHomeSearch();});
    document.addEventListener('click',function(e){if(!e.target.closest('.employee-search-wrap')) hideHomeSearch();});
  }
  document.querySelectorAll('[data-confirm]').forEach(el=>el.addEventListener('click',function(e){if(!confirm(this.dataset.confirm))e.preventDefault()}));
  document.querySelectorAll('[data-auto-search]').forEach(input=>input.addEventListener('input',function(){
    const q=this.value.trim().toLowerCase(); const target=this.dataset.autoSearch;
    document.querySelectorAll(target+' tbody tr').forEach(tr=>tr.style.display=!q||tr.innerText.toLowerCase().includes(q)?'':'none');
  }));
})();

// v16 employee history filters
(function(){
  const table=document.querySelector('#employee_history_table');
  if(!table) return;
  const rows=[...table.querySelectorAll('tbody tr[data-movement-type]')];
  const buttons=[...document.querySelectorAll('[data-history-filter]')];
  const search=document.querySelector('#employee_history_search');
  const noMatch=document.querySelector('#history_no_match');
  let filter='all';
  function apply(){
    const q=(search?.value||'').trim().toLowerCase(); let shown=0;
    rows.forEach(tr=>{const okType=filter==='all'||tr.dataset.movementType===filter; const okText=!q||tr.innerText.toLowerCase().includes(q); const show=okType&&okText; tr.hidden=!show; if(show) shown++;});
    if(noMatch) noMatch.hidden=shown!==0;
  }
  buttons.forEach(b=>b.addEventListener('click',()=>{filter=b.dataset.historyFilter; buttons.forEach(x=>x.classList.toggle('active',x===b)); apply();}));
  search?.addEventListener('input',apply);

  // v17 smart movement entry
  const empSearch=qs('#movement_employee_search'), empHidden=qs('#movement_employee'), empChoices=qs('#movement_employee_choices'), empCount=qs('#employee_match_count'), empCard=qs('#open_employee_card'), empSummary=qs('#selected_employee_summary'), empName=qs('#selected_employee_name'), empMeta=qs('#selected_employee_meta'), moveHint=qs('#movement_hint');
  if(empSearch && empChoices && empHidden){
    const opts=[...empChoices.querySelectorAll('label.choice-item')];
    function updateEmployee(){
      const checked=empChoices.querySelector('input[name=employee_choice]:checked');
      empHidden.value=checked?checked.value:'';
      const show=!!checked;
      if(empSummary) empSummary.hidden=!show;
      if(empCard){empCard.hidden=!show; if(show) empCard.href='/employee/'+checked.value;}
      if(show){if(empName) empName.textContent=checked.dataset.name||''; if(empMeta) empMeta.textContent=checked.dataset.meta||'';}
    }
    function filterEmployees(){
      const q=empSearch.value.trim().toLowerCase(); let n=0;
      opts.forEach(o=>{const ok=!q||(o.dataset.search||o.textContent).toLowerCase().includes(q); o.hidden=!ok; if(ok)n++;});
      if(empCount) empCount.textContent=q?`${n} نتيجة مطابقة`:`${opts.length} موظف متاح`;
    }
    empSearch.addEventListener('input',filterEmployees);
    empChoices.addEventListener('change',e=>{if(e.target.matches('input[name=employee_choice]')) updateEmployee();});
    empChoices.closest('form')?.addEventListener('submit',e=>{if(!empHidden.value){e.preventDefault();alert('يجب اختيار موظف واحد.');}});
    filterEmployees(); updateEmployee();
  }
  const hints={'إجازة':'سجّل نوع الإجازة وفترة الإجازة.','انتداب':'اختر الفرع المنتدب إليه وحدد فترة الانتداب.','إذن':'اختر تاريخ الإذن فقط.'};
  function updateMoveHint(){const r=qs('input[name=movement_type]:checked');if(moveHint&&r)moveHint.textContent=hints[r.value]||'';}
  document.addEventListener('change',function(e){if(e.target.matches('input[name=movement_type]'))updateMoveHint()}); updateMoveHint();
})();


// v27 governorate -> branch dependent selectors
(function(){
  function bind(gid, bid){
    const g=document.getElementById(gid), b=document.getElementById(bid); if(!g||!b)return;
    const opts=[...b.options];
    function sync(){const v=g.value; let valid=0; opts.forEach(o=>{if(!o.value)return; const ok=!v||o.dataset.governorate===v; o.hidden=!ok; if(ok)valid++;}); if(b.value && b.selectedOptions[0]?.hidden)b.value='';}
    g.addEventListener('change',sync); sync();
  }
  bind('employee_governorate','employee_branch');
  bind('new_employee_governorate','new_employee_branch');
})();

// v31.0 role-aware account editor: show only the scope groups required by selected roles.
(function(){
  function syncRoleScopes(root){
    const roles=[...root.querySelectorAll('input[type=checkbox][name="roles"]:checked')].map(x=>x.value);
    root.querySelectorAll('[data-role-scope="supervisor"]').forEach(x=>x.hidden=!roles.includes('مشرف محافظة'));
    root.querySelectorAll('[data-role-scope="entry"]').forEach(x=>x.hidden=!roles.includes('المدخل الأول'));
  }
  document.querySelectorAll('input[type=checkbox][name="roles"]').forEach(x=>x.addEventListener('change',()=>syncRoleScopes(x.closest('form')||document)));
  document.querySelectorAll('form').forEach(f=>{if(f.querySelector('input[type=checkbox][name="roles"]')) syncRoleScopes(f);});
})();

// v30.5 unified choice controls: checkbox lists for every choice field.
(function(){
  function boxes(name, root=document){
    return [...root.querySelectorAll('input[type="checkbox"][name="'+CSS.escape(name)+'"]')];
  }
  document.querySelectorAll('[data-choice-all]').forEach(btn=>btn.addEventListener('click',()=>{
    const root=btn.closest('form')||document;
    boxes(btn.dataset.choiceAll,root).forEach(x=>x.checked=true);
  }));
  document.querySelectorAll('[data-choice-none]').forEach(btn=>btn.addEventListener('click',()=>{
    const root=btn.closest('form')||document;
    boxes(btn.dataset.choiceNone,root).forEach(x=>x.checked=false);
  }));
  document.querySelectorAll('[data-choice-group][data-required="1"]').forEach(group=>group.closest('form')?.addEventListener('submit',function(e){
    const name=group.dataset.choiceGroup;
    if(!boxes(name,group.closest('form')).some(x=>x.checked)){e.preventDefault();alert('يجب اختيار عنصر واحد على الأقل.');}
  }));
  // Single-choice fields keep the same checkbox appearance while submitting one value.
  document.querySelectorAll('[data-single-choice]').forEach(group=>group.addEventListener('change',e=>{
    if(!e.target.matches('input[type="checkbox"]')) return;
    if(e.target.checked) group.querySelectorAll('input[type="checkbox"]').forEach(x=>{if(x!==e.target)x.checked=false;});
  }));

  // Dependent checkbox lists: multiple governorates -> their branches.
  document.querySelectorAll('[data-branch-choice]').forEach(branchGroup=>{
    const form=branchGroup.closest('form');
    if(!form) return;
    const govName=branchGroup.dataset.governorateName||'governorate_id';
    const govGroup=form.querySelector('[data-governorate-choice]') || form.querySelector('[data-choice-group="'+govName+'"]');
    const branchItems=[...branchGroup.querySelectorAll('.choice-item[data-governorate]')];
    function sync(){
      const selected=govGroup ? [...govGroup.querySelectorAll('input[type="checkbox"]:checked')].map(x=>x.value) : [];
      branchItems.forEach(item=>{
        const ok=!selected.length || selected.includes(item.dataset.governorate);
        item.hidden=!ok;
        if(!ok){const cb=item.querySelector('input[type="checkbox"]'); if(cb) cb.checked=false;}
      });
    }
    govGroup?.addEventListener('change',sync); sync();
  });

  // Filter checkbox lists by a selected governorate, while preserving the checkbox UX.
  document.querySelectorAll('[data-filter-group="employee_governorate"]').forEach(govGroup=>{
    const form=govGroup.closest('form');
    const branchGroup=form?.querySelector('[data-filter-group="employee_branch"]');
    if(!branchGroup) return;
    const items=[...branchGroup.querySelectorAll('.choice-item')];
    function sync(){
      const selected=govGroup.querySelector('input[type="checkbox"]:checked')?.value||'';
      items.forEach(item=>{
        const gid=item.dataset.governorate||'';
        const branchInput=item.querySelector('input');
        const branchId=branchInput?.value||'';
        // Branch filter items carry their governorate through a data attribute when available.
        const ok=!selected || !item.dataset.governorate || item.dataset.governorate===selected;
        item.hidden=!ok;
        if(!ok && branchInput) branchInput.checked=false;
      });
    }
    govGroup.addEventListener('change',sync); sync();
  });
})();
