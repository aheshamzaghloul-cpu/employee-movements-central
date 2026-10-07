/* Unified application shell: sidebar only. */
(function(){
  function boot(){
    const sidebar=document.getElementById('appSidebar');
    const toggle=document.getElementById('sidebarToggle');
    const collapse=document.getElementById('sidebarCollapse');
    toggle?.addEventListener('click',()=>sidebar?.classList.toggle('open'));
    const saved=window.localStorage?.getItem('emc-sidebar-collapsed');
    if(saved==='1') document.body.classList.add('ui-sidebar-collapsed');
    collapse?.addEventListener('click',()=>{
      const collapsed=document.body.classList.toggle('ui-sidebar-collapsed');
      try{window.localStorage?.setItem('emc-sidebar-collapsed',collapsed?'1':'0')}catch(e){}
    });
    sidebar?.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>sidebar.classList.remove('is-open')));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

// Unified interaction layer is loaded once for the whole application.


// Context-aware navigation hinting: keep the shell aware of the current workspace.
(function(){
  function bootContext(){
    const path=window.location.pathname;
    document.documentElement.dataset.workspace =
      path==='/'?'home':path.startsWith('/employees')?'employees':
      (path.startsWith('/reports')||path.startsWith('/mission'))?'reports':
      path.startsWith('/delegations')?'delegations':
      (path.startsWith('/structure')||path.startsWith('/users')||path.startsWith('/branches')||path.startsWith('/governorates')||path.startsWith('/audit')||path.startsWith('/lookups')||path.startsWith('/excel-import')||path.startsWith('/replacement'))?'admin':
      path.startsWith('/change-password')?'account':'workspace';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bootContext,{once:true});else bootContext();
})();
