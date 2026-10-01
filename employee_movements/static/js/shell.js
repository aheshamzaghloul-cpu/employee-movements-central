/* Application shell: sidebar, collapse and assistant window. */
(function(){
  function boot(){
    const sidebar=document.getElementById('appSidebar');
    const toggle=document.getElementById('sidebarToggle');
    const collapse=document.getElementById('sidebarCollapse');
    toggle?.addEventListener('click',()=>sidebar?.classList.toggle('open'));
    collapse?.addEventListener('click',()=>document.body.classList.toggle('ds-sidebar-collapsed'));
    const modal=document.getElementById('assistantModal');
    const fab=document.getElementById('assistantFab');
    const side=document.getElementById('sidebarAssistantOpen');
    const close=document.getElementById('assistantClose');
    const frame=document.getElementById('assistantFrame');
    window.__openAssistant=function(){
      if(!modal)return;
      modal.hidden=false; modal.style.display='block'; modal.classList.add('is-open'); modal.setAttribute('aria-hidden','false');
      if(fab)fab.hidden=true;
      if(frame && !frame.src) frame.src='/assistant?embed=1';
    };
    window.__closeAssistant=function(){
      if(!modal)return;
      modal.hidden=true; modal.style.display='none'; modal.classList.remove('is-open'); modal.setAttribute('aria-hidden','true');
      if(fab)fab.hidden=false;
    };
    [fab,side].forEach(el=>el?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();window.__openAssistant();}));
    close?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();window.__closeAssistant();});
    modal?.addEventListener('click',e=>{if(e.target===modal)window.__closeAssistant();});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal&&!modal.hidden)window.__closeAssistant();});
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
