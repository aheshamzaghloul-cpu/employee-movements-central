(function(){
  function ready(fn){ if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',fn,{once:true}); else fn(); }
  ready(function(){
    const dock=document.getElementById('assistantDock');
    if(!dock) return;
    const toggle=document.getElementById('assistantDockToggle');
    const panel=document.getElementById('assistantDockPanel');
    const thread=document.getElementById('assistantDockThread');
    const form=document.getElementById('assistantDockForm');
    const input=document.getElementById('assistantDockInput');
    const contextInput=document.getElementById('assistantWorkspaceContext');
    let busy=false;
    const liveSelection={};

    function context(){
      const ctx={path:location.pathname||'/',hash:location.hash||'',title:document.title||'',heading:(document.querySelector('h1')?.innerText||'').trim().slice(0,160),selected:{}};
      const scope=document.querySelector('select[name="governorate_id"]');
      if(scope?.value) ctx.scope_governorate_id=Number(scope.value);
      const active=document.querySelector('[data-assistant-context-active="1"]');
      if(active){
        for(const k of ['employee','movement','branch','governorate','delegation','user']){
          const v=active.getAttribute('data-'+k+'-id'); if(v) ctx.selected[k+'_id']=Number(v);
        }
      }
      Object.assign(ctx.selected, liveSelection);
      document.querySelectorAll('select[name=employee_id],select[name=movement_id],select[name=branch_id],select[name=governorate_id]').forEach(sel=>{
        if(sel.value){ const key=sel.name.replace('_id','_id'); const n=Number(sel.value); if(Number.isFinite(n)) ctx.selected[key]=n; }
      });
      const m=location.pathname.match(/\/employees\/(\d+)/); if(m) ctx.selected.employee_id=Number(m[1]);
      const mm=location.pathname.match(/\/movements\/(\d+)/); if(mm) ctx.selected.movement_id=Number(mm[1]);
      return ctx;
    }
    function sync(){
      const c=context();
      if(contextInput) contextInput.value=JSON.stringify(c);
      const cbox=document.getElementById('assistantDockContext');
      if(cbox) cbox.textContent='السياق الحالي: '+(c.heading||document.title||'مساحة العمل')+(c.scope_governorate_id?' · نطاق محافظة محدد':'');
    }
    function setOpen(open){
      dock.dataset.open=open?'1':'0';
      if(panel) panel.hidden=!open;
      toggle?.setAttribute('aria-expanded',String(open));
      sync();
      if(open && !thread.dataset.loaded){ load(); }
      if(open) setTimeout(()=>input?.focus(),70);
    }
    async function load(){
      if(!thread||thread.dataset.loading) return;
      thread.dataset.loading='1'; sync();
      try{
        const r=await fetch('/assistant?panel=1',{credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});
        if(!r.ok) throw new Error('HTTP '+r.status);
        thread.innerHTML=await r.text();
        thread.dataset.loaded='1';
        wireThread(); scrollBottom();
      }catch(e){ thread.innerHTML='<div class="assistant-dock-empty">تعذر تحميل المحادثة. جرّب مرة أخرى.</div>'; }
      finally{ delete thread.dataset.loading; }
    }
    function scrollBottom(){ if(thread) requestAnimationFrame(()=>thread.scrollTop=thread.scrollHeight); }
    function wireThread(){
      thread.querySelectorAll('[data-assistant-prompt]').forEach(b=>b.addEventListener('click',()=>{input.value=b.dataset.assistantPrompt||'';sync();input.focus();}));
      thread.querySelectorAll('[data-assistant-url]').forEach(b=>b.addEventListener('click',()=>{location.href=b.dataset.assistantUrl||'/';}));
    }
    form?.addEventListener('submit',async (e)=>{
      e.preventDefault();
      const prompt=(input?.value||'').trim(); if(!prompt||busy) return;
      busy=true; setOpen(true); sync();
      const fd=new FormData(form); fd.set('prompt',prompt); fd.set('workspace_context',JSON.stringify(context()));
      if(thread){
        const u=document.createElement('div');u.className='chat-msg user-msg optimistic-user-msg';u.innerHTML='<div class="chat-bubble"></div><div class="chat-avatar user-avatar">أنت</div>';u.querySelector('.chat-bubble').textContent=prompt;thread.appendChild(u);scrollBottom();
      }
      input.value='';
      const send=form.querySelector('button[type="submit"]'); send?.classList.add('is-busy'); send && (send.disabled=true);
      try{
        const r=await fetch('/assistant?panel=1',{method:'POST',body:fd,credentials:'same-origin',headers:{'X-Requested-With':'fetch'}});
        if(!r.ok) throw new Error('HTTP '+r.status);
        const html=await r.text();
        thread.innerHTML=html; thread.dataset.loaded='1'; wireThread(); scrollBottom();
      }catch(e){
        const err=document.createElement('div');err.className='assistant-dock-empty';err.textContent='تعذر إكمال الرد الآن. راجع الاتصال أو إعدادات المساعد وحاول مرة أخرى.';thread.appendChild(err);
      }finally{busy=false;send?.classList.remove('is-busy');send && (send.disabled=false);input?.focus();}
    });
    document.addEventListener('keydown',e=>{
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='j'){e.preventDefault();setOpen(dock.dataset.open!=='1');}
      if(e.key==='Escape'&&dock.dataset.open==='1')setOpen(false);
    });
    window.__toggleAssistantDock=()=>setOpen(dock.dataset.open!=='1');
    toggle?.addEventListener('click',()=>setOpen(dock.dataset.open!=='1'));
    document.getElementById('assistantInlineOpen')?.addEventListener('click',()=>{setOpen(true); input?.focus();});
    window.__focusAssistant=()=>{setOpen(true); input?.focus();};
    sync();
  });
})();
