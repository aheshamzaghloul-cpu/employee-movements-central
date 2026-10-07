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
    list.innerHTML=shown.slice(0,8).map(x=>`<article class="interactive-notification-pop-item ${esc(x.level)}"><i></i><div><b>${esc(x.title)}</b><span>${esc(x.label)}</span><p>${esc(x.detail)}</p><small>${esc(x.branch)}${x.code?' · '+esc(x.code):''}</small><div class="interactive-notification-pop-actions"><a href="${esc(x.employee_url)}">ملف الموظف</a><a class="primary" href="${esc(x.action_url)}">${esc(x.action_label)}</a></div></div></article>`).join('');
  }
  async function load(){
    try{const r=await fetch('/api/notifications',{headers:{Accept:'application/json'},credentials:'same-origin'}); if(!r.ok) throw new Error(); const d=await r.json(); items=Array.isArray(d.items)?d.items:[]; paintBadge({count:items.length,urgent:items.filter(x=>x.level==='urgent').length}); paintList();}
    catch(e){if(!items.length) list.innerHTML='<div class="interactive-notification-pop-empty"><b>تعذر تحديث المتابعة</b><span>حاول مرة أخرى.</span></div>';}
  }
  function open(){pop.hidden=false; trigger.setAttribute('aria-expanded','true'); load();}
  function close(){pop.hidden=true; trigger.setAttribute('aria-expanded','false');}
  trigger.addEventListener('click',()=>pop.hidden?open():close());
  document.addEventListener('click',e=>{if(!pop.hidden&&!pop.contains(e.target)&&!trigger.contains(e.target))close();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!pop.hidden)close();});
  refresh?.addEventListener('click',load);
  pop.querySelectorAll('[data-notification-filter]').forEach(btn=>btn.addEventListener('click',()=>{filter=btn.dataset.notificationFilter;pop.querySelectorAll('[data-notification-filter]').forEach(x=>x.classList.toggle('active',x===btn));paintList();}));
  load();
})();