(function(){
  function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn,{once:true});else fn();}
  ready(function(){
    const target=window.location.hash;
    if(target){const el=document.querySelector(target);if(el)setTimeout(()=>el.scrollIntoView({behavior:'smooth',block:'start'}),120);}
    document.addEventListener('keydown',e=>{
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='j'){
        e.preventDefault();
        window.location.href='/assistant';
      }
    });
  });
})();
