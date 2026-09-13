(function(){
  function qs(s){return document.querySelector(s)}
  const type=qs('input[name=movement_type]:checked');
  function syncMovement(){
    const type=qs('input[name=movement_type]:checked');
    if(!type) return;
    const v=type.value;
    const hidden=qs('#movement_type_hidden'); if(hidden) hidden.value=v;
    document.querySelectorAll('[data-movement]').forEach(el=>{const a=[el.dataset.movement,el.dataset.movement2].filter(Boolean); el.hidden=!a.includes(v)});
    document.querySelectorAll('.smart-fields input,.smart-fields select').forEach(el=>{const wrap=el.closest('[data-movement]'); if(wrap && wrap.hidden){el.required=false; if(el.tagName==='SELECT') el.value=''; else el.value='';}});
    const leave=qs('#leave_type'), dest=qs('#destination_branch_id'), fd=qs('#from_date'), td=qs('#to_date'), pd=qs('#permission_date');
    if(leave) leave.required=v==='إجازة';
    if(dest) dest.required=v==='انتداب';
    if(fd) fd.required=v!=='إذن';
    if(td) td.required=v!=='إذن';
    if(pd) pd.required=v==='إذن';
    const days=qs('#movement_days');
    if(days){
      if(v==='إذن'){days.textContent='—';return}
      const a=fd&&fd.value?new Date(fd.value):null,b=td&&td.value?new Date(td.value):null;
      days.textContent=(a&&b&&b>=a)?Math.floor((b-a)/86400000)+1:'—';
    }
  }
  ['change','input'].forEach(ev=>document.addEventListener(ev,function(e){if(e.target.matches('input[name=movement_type],#from_date,#to_date')) syncMovement()}));
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
  const empSearch=qs('#movement_employee_search'), empSelect=qs('#movement_employee'), empCount=qs('#employee_match_count'), empCard=qs('#open_employee_card'), empSummary=qs('#selected_employee_summary'), empName=qs('#selected_employee_name'), empMeta=qs('#selected_employee_meta'), moveHint=qs('#movement_hint');
  if(empSearch && empSelect){
    const opts=[...empSelect.options].filter(o=>o.value);
    function filterEmployees(){
      const q=empSearch.value.trim().toLowerCase(); let n=0;
      opts.forEach(o=>{const ok=!q || (o.dataset.search||o.textContent).toLowerCase().includes(q); o.hidden=!ok; if(ok)n++;});
      empCount.textContent=q ? `${n} نتيجة مطابقة` : `${opts.length} موظف متاح`;
      const selected=empSelect.value; if(selected){const o=empSelect.querySelector(`option[value="${selected}"]`); if(o && o.hidden) empSelect.value='';}
      updateEmployeeCard();
    }
    function updateEmployeeCard(){
      const o=empSelect.value ? empSelect.querySelector(`option[value="${empSelect.value}"]`) : null;
      const show=!!o;
      if(empSummary) empSummary.hidden=!show;
      if(empCard){empCard.hidden=!show; if(show) empCard.href='/employee/'+empSelect.value;}
      if(show){
        const parts=o.textContent.split('—').map(x=>x.trim());
        if(empName) empName.textContent=parts[0]||'';
        if(empMeta) empMeta.textContent=parts.slice(1).join(' — ');
      }
    }
    empSearch.addEventListener('input',filterEmployees); empSelect.addEventListener('change',updateEmployeeCard); filterEmployees(); updateEmployeeCard();
  }
  const hints={'إجازة':'سجّل نوع الإجازة وفترة الإجازة.','انتداب':'اختر الفرع المنتدب إليه وحدد فترة الانتداب.','إذن':'اختر تاريخ الإذن فقط.'};
  function updateMoveHint(){const r=qs('input[name=movement_type]:checked');if(moveHint&&r)moveHint.textContent=hints[r.value]||'';}
  document.addEventListener('change',function(e){if(e.target.matches('input[name=movement_type]'))updateMoveHint()}); updateMoveHint();
})();
