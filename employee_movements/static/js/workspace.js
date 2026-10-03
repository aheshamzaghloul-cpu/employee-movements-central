(function(){
  function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn,{once:true});else fn();}
  ready(function(){
    const target=window.location.hash;
    if(target){const el=document.querySelector(target);if(el)setTimeout(()=>el.scrollIntoView({behavior:'smooth',block:'start'}),120);}
    const focusAssistant=()=>{if(window.__focusAssistant){window.__focusAssistant();return;}const input=document.getElementById('assistantDockInput');if(input){input.scrollIntoView({behavior:'smooth',block:'center'});setTimeout(()=>input.focus(),180);}};
    document.getElementById('assistantFocus')?.addEventListener('click',focusAssistant);
    document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='j'){e.preventDefault();focusAssistant();}});
  });
})();
