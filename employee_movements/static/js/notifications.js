(function(){
  const trigger=document.getElementById('notificationTrigger');
  const badge=document.getElementById('notificationBadge');
  const pop=document.getElementById('notificationPopover');
  const list=document.getElementById('notificationPopList');
  const refresh=document.getElementById('notificationRefresh');
  if(!trigger||!badge||!pop||!list) return;
  let items=[]; let filter='all';
  const esc=(v)=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function paintBadge(data){const n=Number(data.count||0); badge.textContent=n>99?'99+':String(n); badge.hidden=n===0; badge.classList.toggle('urgent',Number(data.urgent||0)>0);}
  function paintList(){
    const shown=filter==='all'?items:items.filter(x=>x.level===filter);
    if(!shown.length){list.innerHTML='<div class="interactive-notification-pop-empty"><b>لا توجد عناصر هنا</b><span>لا توجد متابعة معلقة ضمن هذا التصنيف.</span></div>';return;}
    list.innerHTML=shown.slice(0,8).map(x=>`<article class="interactive-notification-pop-item ${esc(x.level)}"><i></i><div><b>${esc(x.title)}</b><span>${esc(x.label)}</span><p>${esc(x.detail)}</p><small>${esc(x.branch)}${x.code?' · '+esc(x.code):''}</small><div class="interactive-notification-pop-actions"><a href="${esc(x.employee_url)}" aria-label="فتح ملف الموظف ${esc(x.title)}">ملف الموظف</a><a class="primary" href="${esc(x.action_url)}" aria-label="${esc(x.action_label)}: ${esc(x.title)}">${esc(x.action_label)}</a></div></div></article>`).join('');
  }
  async function load(){
    try{const r=await fetch('/api/notifications',{headers:{Accept:'application/json'},credentials:'same-origin'}); if(!r.ok) throw new Error(); const d=await r.json(); items=Array.isArray(d.items)?d.items:[]; paintBadge({count:Number(d.total??items.length),urgent:Number(d.urgent??items.filter(x=>x.level==='urgent').length)}); paintList();}
    catch(e){if(!items.length) list.innerHTML='<div class="interactive-notification-pop-empty"><b>تعذر تحديث المتابعة</b><span>حاول مرة أخرى.</span></div>';}
  }
  async function loadSummary(){
    try{const r=await fetch('/api/notifications/summary',{headers:{Accept:'application/json'},credentials:'same-origin'}); if(!r.ok) throw new Error(); const d=await r.json(); paintBadge({count:Number(d.total||0),urgent:Number(d.urgent||0)});}
    catch(e){/* The full list will retry when the user opens the notification center. */}
  }
  function open(){pop.hidden=false; trigger.setAttribute('aria-expanded','true'); load();}
  function close(restoreFocus=false){pop.hidden=true; trigger.setAttribute('aria-expanded','false'); if(restoreFocus) trigger.focus({preventScroll:true});}
  trigger.addEventListener('click',()=>pop.hidden?open():close());
  document.addEventListener('click',e=>{if(!pop.hidden&&!pop.contains(e.target)&&!trigger.contains(e.target))close();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!pop.hidden){e.preventDefault();close(true);}});
  refresh?.addEventListener('click',load);
  pop.querySelectorAll('[data-notification-filter]').forEach(btn=>btn.addEventListener('click',()=>{filter=btn.dataset.notificationFilter;pop.querySelectorAll('[data-notification-filter]').forEach(x=>x.classList.toggle('active',x===btn));paintList();}));
  loadSummary();
})();