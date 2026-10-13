/* Unified application shell: responsive layout, accessible navigation, and resilient preferences. */
(function(){
  'use strict';
  function boot(){
    const sidebar=document.getElementById('appSidebar');
    const toggle=document.getElementById('sidebarToggle');
    const collapse=document.getElementById('sidebarCollapse');
    const backdrop=document.getElementById('sidebarBackdrop');
    if(!sidebar) return;

    const body=document.body;
    const mobileQuery=window.matchMedia('(max-width: 800px)');
    let desktopCollapsed=false;
    try{desktopCollapsed=window.localStorage.getItem('emc-sidebar-collapsed')==='1';}catch(_e){}

    sidebar.querySelectorAll('a').forEach(a=>{
      const label=a.querySelector('span')?.textContent?.trim();
      if(label && !a.hasAttribute('title')) a.title=label;
      if(a.closest('nav')){
        if(a.classList.contains('active')) a.setAttribute('aria-current','page');
        else a.removeAttribute('aria-current');
      }
    });

    function syncCollapsedState(){
      /* A saved desktop preference must never shrink the mobile navigation drawer. */
      body.classList.toggle('ui-sidebar-collapsed',!mobileQuery.matches&&desktopCollapsed);
      if(collapse){
        collapse.setAttribute('aria-expanded',String(!desktopCollapsed));
        collapse.setAttribute('aria-label',desktopCollapsed?'توسيع القائمة':'تصغير القائمة');
        collapse.title=desktopCollapsed?'توسيع القائمة':'تصغير القائمة';
      }
    }
    function setMobileOpen(open,restoreFocus){
      const shouldOpen=Boolean(open&&mobileQuery.matches);
      sidebar.classList.toggle('is-open',shouldOpen);
      body.classList.toggle('ui-sidebar-mobile-open',shouldOpen);
      if(backdrop) backdrop.hidden=!shouldOpen;
      if(toggle){
        toggle.setAttribute('aria-expanded',String(shouldOpen));
        toggle.setAttribute('aria-label',shouldOpen?'إغلاق القائمة':'فتح القائمة');
        toggle.title=shouldOpen?'إغلاق القائمة':'فتح القائمة';
        const icon=toggle.querySelector('svg');
        if(icon) icon.innerHTML=shouldOpen
          ? '<path d="m6 6 12 12M18 6 6 18" />'
          : '<path d="M4 7h16M4 12h16M4 17h16" />';
      }
      if(shouldOpen){
        const firstLink=sidebar.querySelector('nav a, .premium-side-footer a');
        firstLink?.focus({preventScroll:true});
      }else if(restoreFocus&&mobileQuery.matches){
        toggle?.focus({preventScroll:true});
      }
    }

    syncCollapsedState();
    toggle?.addEventListener('click',()=>setMobileOpen(!sidebar.classList.contains('is-open'),false));
    backdrop?.addEventListener('click',()=>setMobileOpen(false,true));
    sidebar.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>setMobileOpen(false,false)));
    document.addEventListener('keydown',e=>{
      if(e.key==='Escape'&&sidebar.classList.contains('is-open')){
        e.preventDefault();
        setMobileOpen(false,true);
      }
    });
    collapse?.addEventListener('click',()=>{
      if(mobileQuery.matches) return;
      desktopCollapsed=!desktopCollapsed;
      syncCollapsedState();
      try{window.localStorage.setItem('emc-sidebar-collapsed',desktopCollapsed?'1':'0');}catch(_e){}
    });
    const onViewportChange=()=>{
      if(!mobileQuery.matches) setMobileOpen(false,false);
      syncCollapsedState();
    };
    if(typeof mobileQuery.addEventListener==='function') mobileQuery.addEventListener('change',onViewportChange);
    else if(typeof mobileQuery.addListener==='function') mobileQuery.addListener(onViewportChange);
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

/* Context-aware navigation hinting: keep the shell aware of the current workspace. */
(function(){
  function bootContext(){
    const path=window.location.pathname;
    document.documentElement.dataset.workspace =
      path==='/'?'home':path.startsWith('/employees')?'employees':
      (path.startsWith('/reports')||path.startsWith('/mission'))?'reports':
      path.startsWith('/delegations')?'delegations':
      path.startsWith('/manager')?'manager':
      (path.startsWith('/structure')||path.startsWith('/users')||path.startsWith('/branches')||path.startsWith('/governorates')||path.startsWith('/audit')||path.startsWith('/lookups')||path.startsWith('/excel-import')||path.startsWith('/replacement'))?'admin':
      path.startsWith('/change-password')?'account':'workspace';
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bootContext,{once:true});else bootContext();
})();
