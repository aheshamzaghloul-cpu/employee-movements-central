/* Unified application shell: sidebar only. */
(function(){
  function boot(){
    const sidebar=document.getElementById('appSidebar');
    const toggle=document.getElementById('sidebarToggle');
    const collapse=document.getElementById('sidebarCollapse');
    toggle?.addEventListener('click',()=>sidebar?.classList.toggle('open'));
    collapse?.addEventListener('click',()=>document.body.classList.toggle('ui-sidebar-collapsed'));
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();

// v65: smart interaction layer is loaded once for the whole application.
