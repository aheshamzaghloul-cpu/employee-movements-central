/* Application shell: responsive sidebar + persistent assistant window. */
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
    const inline=document.getElementById('assistantInlineOpen');
    const close=document.getElementById('assistantClose');
    const frame=document.getElementById('assistantFrame');
    const win=document.getElementById('assistantWindow');
    const drag=document.getElementById('assistantDragBar');
    const STORE_KEY='employee_assistant_window_v53';

    function saveWindow(){
      if(!win)return;
      const rect=win.getBoundingClientRect();
      const state={left:Math.round(rect.left),bottom:Math.round(window.innerHeight-rect.bottom),width:Math.round(rect.width),height:Math.round(rect.height)};
      try{localStorage.setItem(STORE_KEY,JSON.stringify(state));}catch(e){}
    }
    function restoreWindow(){
      if(!win)return;
      try{
        const s=JSON.parse(localStorage.getItem(STORE_KEY)||'null');
        if(!s)return;
        const maxW=Math.max(330,window.innerWidth-30), maxH=Math.max(420,window.innerHeight-36);
        const w=Math.min(Math.max(330,s.width||455),maxW);
        const h=Math.min(Math.max(420,s.height||700),maxH);
        const left=Math.max(8,Math.min(s.left||24,window.innerWidth-w-8));
        const bottom=Math.max(8,Math.min(s.bottom||24,window.innerHeight-h-8));
        win.style.width=w+'px'; win.style.height=h+'px'; win.style.left=left+'px'; win.style.bottom=bottom+'px'; win.style.right='auto'; win.style.top='auto';
      }catch(e){}
    }
    function open(){
      if(!modal)return;
      modal.hidden=false; modal.style.display='block'; modal.classList.add('is-open'); modal.setAttribute('aria-hidden','false');
      if(fab)fab.hidden=true;
      restoreWindow();
      if(frame && !frame.src)frame.src='/assistant?embed=1';
    }
    function closeWindow(){
      if(!modal)return;
      saveWindow();
      modal.hidden=true; modal.style.display='none'; modal.classList.remove('is-open'); modal.setAttribute('aria-hidden','true');
      if(fab)fab.hidden=false;
    }
    window.__openAssistant=open;
    window.__closeAssistant=closeWindow;
    [fab,side,inline].forEach(el=>el?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();open();}));
    close?.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();closeWindow();});
    modal?.addEventListener('click',e=>{if(e.target===modal)closeWindow();});
    window.addEventListener('resize',()=>{if(modal&&!modal.hidden){restoreWindow();}});
    document.addEventListener('keydown',e=>{if(e.key==='Escape'&&modal&&!modal.hidden)closeWindow();});

    // Drag the window from its header. Resize remains native on desktop and is saved.
    if(drag&&win){
      let dragState=null;
      const end=()=>{if(!dragState)return;dragState=null;win.classList.remove('is-dragging');saveWindow();};
      drag.addEventListener('pointerdown',e=>{
        if(e.button!==0 || e.target.closest('button'))return;
        const rect=win.getBoundingClientRect();
        dragState={x:e.clientX,y:e.clientY,left:rect.left,top:rect.top,w:rect.width,h:rect.height};
        win.classList.add('is-dragging');
        drag.setPointerCapture?.(e.pointerId); e.preventDefault();
      });
      drag.addEventListener('pointermove',e=>{
        if(!dragState)return;
        const dx=e.clientX-dragState.x, dy=e.clientY-dragState.y;
        const left=Math.max(8,Math.min(dragState.left+dx,window.innerWidth-dragState.w-8));
        const top=Math.max(8,Math.min(dragState.top+dy,window.innerHeight-dragState.h-8));
        win.style.left=Math.round(left)+'px';
        win.style.top=Math.round(top)+'px';
        win.style.bottom='auto'; win.style.right='auto';
      });
      drag.addEventListener('pointerup',end);
      drag.addEventListener('pointercancel',end);
      window.addEventListener('mouseup',end);
      if(typeof ResizeObserver!=='undefined'){
        new ResizeObserver(()=>{if(modal&&!modal.hidden&&!win.classList.contains('is-dragging'))saveWindow();}).observe(win);
      }
    }
  }
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
