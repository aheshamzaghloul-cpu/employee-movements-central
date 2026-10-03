(function(){
  function ready(fn){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fn,{once:true});else fn();}
  ready(function(){
    const modal=document.getElementById('directActionModal');
    const openBtn=document.getElementById('directActionOpen');
    const closeBtn=document.getElementById('directActionClose');
    const search=document.getElementById('directActionSearch');
    const items=[...document.querySelectorAll('[data-direct-item]')];
    function close(){if(!modal)return;modal.hidden=true;document.body.classList.remove('v54-modal-open');}
    function open(){if(!modal)return;modal.hidden=false;document.body.classList.add('v54-modal-open');setTimeout(()=>search?.focus(),40);}
    openBtn?.addEventListener('click',open);
    closeBtn?.addEventListener('click',close);
    modal?.addEventListener('click',e=>{if(e.target===modal)close();});
    document.addEventListener('keydown',e=>{
      if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();modal?.hidden?open():close();}
      if(e.key==='Escape'&&!modal?.hidden)close();
    });
    search?.addEventListener('input',()=>{
      const q=(search.value||'').trim().toLocaleLowerCase('ar');
      items.forEach(x=>{x.hidden=!!q&&!x.innerText.toLocaleLowerCase('ar').includes(q);});
      document.querySelectorAll('[data-direct-group]').forEach(g=>{const visible=[...g.querySelectorAll('[data-direct-item]')].some(x=>!x.hidden);g.hidden=!visible;});
    });

    const target=window.location.hash;
    if(target){
      const el=document.querySelector(target);
      if(el){setTimeout(()=>el.scrollIntoView({behavior:'smooth',block:'start'}),120);}
    }

  });
})();
