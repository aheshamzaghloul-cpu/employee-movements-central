(function(){
  'use strict';
  const qs=(s,r=document)=>r.querySelector(s), qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  const palette=qs('#commandPalette'), input=qs('#paletteInput'), results=qs('#paletteResults');
  const trigger=qs('#commandPaletteOpen'); let paletteItems=[], activeIndex=0, searchTimer=null, seq=0;
  const actions=[
    {label:'تسجيل حركة',hint:'إجازة · انتداب · إذن',icon:'＋',href:'/#movement-register',keywords:'حركة إجازة انتداب إذن'},
    {label:'الموظفون',hint:'إدارة الموظفين وملفاتهم',icon:'♙',href:'/employees',keywords:'موظفين بيانات ملفات'},
    {label:'الحركات',hint:'متابعة الحركات الحالية والسجل',icon:'↔',href:'/movements',keywords:'حركات سجل'},
    {label:'التقارير والمأموريات',hint:'التقارير والطباعة',icon:'▤',href:'/reports-missions',keywords:'تقارير مأموريات'},
    {label:'المساعد الذكي',hint:'اسأل النظام أو اطلب تنفيذ عملية',icon:'✦',href:'/assistant',keywords:'مساعد ذكاء اصطناعي Gemini'},
    {label:'حسابي',hint:'إعدادات الحساب وكلمة المرور',icon:'◎',href:'/change-password',keywords:'حساب كلمة مرور'}
  ];

  function render(items){
    paletteItems=items; activeIndex=Math.min(activeIndex,Math.max(items.length-1,0));
    if(!results)return;
    if(!items.length){results.innerHTML='<div class="v65-empty">لا توجد نتيجة مطابقة.</div>';return;}
    results.innerHTML=items.map((x,i)=>`<button type="button" class="v65-result ${i===activeIndex?'is-active':''}" data-index="${i}"><span class="v65-result-icon">${x.icon||'•'}</span><span class="v65-result-copy"><strong>${esc(x.label)}</strong><small>${esc(x.hint||'')}</small></span><span class="v65-result-arrow">↵</span></button>`).join('');
    qsa('.v65-result',results).forEach(b=>b.addEventListener('mouseenter',()=>setActive(Number(b.dataset.index))));
    qsa('.v65-result',results).forEach(b=>b.addEventListener('click',()=>choose(Number(b.dataset.index))));
  }
  function setActive(i){if(!paletteItems.length)return;activeIndex=(i+paletteItems.length)%paletteItems.length;qsa('.v65-result',results).forEach((b,n)=>b.classList.toggle('is-active',n===activeIndex));qsa('.v65-result',results)[activeIndex]?.scrollIntoView({block:'nearest'});}
  function choose(i){const item=paletteItems[i];if(!item)return;if(item.href)location.href=item.href;}
  function open(){if(!palette)return;palette.hidden=false;palette.setAttribute('aria-hidden','false');document.body.classList.add('v65-palette-open');activeIndex=0;if(input){input.value='';input.focus();}render(actions);}
  function close(){if(!palette)return;palette.hidden=true;palette.setAttribute('aria-hidden','true');document.body.classList.remove('v65-palette-open');trigger?.focus();}
  function searchActions(q){
    const needle=(q||'').toLowerCase();
    const filtered=actions.filter(x=>(x.label+' '+x.hint+' '+x.keywords).toLowerCase().includes(needle));
    render(filtered);
  }
  trigger?.addEventListener('click',open);
  qsa('[data-palette-close]').forEach(x=>x.addEventListener('click',close));
  input?.addEventListener('input',()=>searchActions(input.value.trim()));
  input?.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();setActive(activeIndex+1);}else if(e.key==='ArrowUp'){e.preventDefault();setActive(activeIndex-1);}else if(e.key==='Enter'){e.preventDefault();choose(activeIndex);}else if(e.key==='Escape'){e.preventDefault();close();}});
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();open();}else if(e.key==='Escape'&&!palette?.hidden)close();});

  window.toast=function(message,type='info',duration=3200){const region=qs('#toastRegion');if(!region)return;const el=document.createElement('div');el.className='v65-toast v65-toast-'+type;el.textContent=message;region.appendChild(el);requestAnimationFrame(()=>el.classList.add('is-visible'));setTimeout(()=>{el.classList.remove('is-visible');setTimeout(()=>el.remove(),220)},duration);};

  // Smart date validation for movement forms: never allow an impossible interval to reach the server.
  qsa('form').forEach(form=>{
    const from=qs('input[name="from_date"],#from_date',form), to=qs('input[name="to_date"],#to_date',form);
    if(!from||!to)return;
    const validate=()=>{to.setCustomValidity(from.value&&to.value&&to.value<from.value?'تاريخ النهاية يجب أن يكون مساويًا أو بعد تاريخ البداية.':'');};
    from.addEventListener('change',validate);to.addEventListener('change',validate);validate();
  });

  // First-letter navigation for native selects: type a letter/name and jump immediately, without Enter.
  qsa('select:not([multiple])').forEach(select=>{
    let buffer='', timer=null;
    select.addEventListener('keydown',e=>{
      if(e.ctrlKey||e.altKey||e.metaKey||['ArrowUp','ArrowDown','Enter','Escape','Tab'].includes(e.key))return;
      if(e.key.length!==1)return;
      buffer+=(buffer? '':'')+e.key.toLowerCase(); clearTimeout(timer); timer=setTimeout(()=>buffer='',550);
      const options=[...select.options].filter(o=>!o.disabled&&o.value);
      const hit=options.find(o=>(o.textContent||'').trim().toLowerCase().startsWith(buffer));
      if(hit){e.preventDefault();select.value=hit.value;select.dispatchEvent(new Event('change',{bubbles:true}));}
    });
  });
})();
