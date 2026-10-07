(function(){
  'use strict';
  const qs=(s,r=document)=>r.querySelector(s), qsa=(s,r=document)=>[...r.querySelectorAll(s)];
  const esc=v=>String(v??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

  const palette=qs('#commandPalette'), input=qs('#paletteInput'), results=qs('#paletteResults');
  const trigger=qs('#commandPaletteOpen'); let paletteItems=[], activeIndex=0, searchTimer=null, seq=0;
  const baseActions=[
    {label:'الرئيسية',hint:'العمل اليومي والبحث وتسجيل الحركة',icon:'⌂',href:'/',keywords:'رئيسية home'},
    {label:'بحث عن موظف',hint:'الوصول السريع إلى الموظف وملفه',icon:'⌕',href:'/#employee-search',keywords:'بحث موظف كود اسم ملف'},
    {label:'الموظفون',hint:'دليل الموظفين وبياناتهم الأساسية',icon:'♙',href:'/employees',keywords:'موظفين بيانات ملفات'},
    {label:'التقارير والمأموريات',hint:'التقارير والطباعة والمتابعة',icon:'▤',href:'/reports-missions',keywords:'تقارير مأموريات طباعة'},
    {label:'الإشعارات',hint:'ما يحتاج انتباهك الآن',icon:'◉',href:'/notifications',keywords:'إشعارات متابعة عاجل قريب'},
    {label:'المساعد الذكي',hint:'اسأل بسيوني أو اطلب تنفيذ إجراء',icon:'✦',href:'/assistant',keywords:'بسيوني مساعد ذكاء Gemini تنفيذ'},
    {label:'حسابي',hint:'الحساب وكلمة المرور',icon:'◎',href:'/change-password',keywords:'حساب كلمة مرور'}
  ];
  const pageContext=()=>{
    const path=location.pathname;
    if(path==='/') return {key:'home',label:'الرئيسية',actions:[{label:'تسجيل حركة',hint:'إجازة · انتداب · إذن',icon:'＋',href:'/#movement-register',keywords:'حركة إجازة انتداب إذن'},{label:'حالة الموظفين الآن',hint:'الحركات الحالية فقط',icon:'◌',href:'#current-status',keywords:'حالة إجازة انتداب إذن'}]};
    if(path.startsWith('/employees')) return {key:'employees',label:'الموظفون',actions:[{label:'إضافة موظف',hint:'إضافة سجل أساسي جديد',icon:'＋',href:'/employees#employee-add',keywords:'إضافة موظف جديد'}]};
    if(path.startsWith('/reports')||path.startsWith('/mission')) return {key:'reports',label:'التقارير والمأموريات',actions:[{label:'مركز المأموريات',hint:'مراجعة وطباعة وإغلاق المأموريات',icon:'▣',href:'/reports-missions#missions-center',keywords:'مأموريات طباعة إغلاق'}]};
    if(path.startsWith('/delegations')) return {key:'delegations',label:'التفويض',actions:[{label:'التفويضات الحالية',hint:'مراجعة التفويضات السارية',icon:'↔',href:'#delegation-list',keywords:'تفويض مشرف ساري'}]};
    if(path.startsWith('/structure')) return {key:'admin',label:'الإدارة',actions:[{label:'صحة النظام',hint:'الإشارات الهيكلية والبيانات والصلاحيات',icon:'◇',href:'#admin-intelligence',keywords:'إدارة صحة هيكل صلاحيات بيانات'}]};
    if(path.startsWith('/users')) return {key:'users',label:'المستخدمون والصلاحيات',actions:[{label:'إضافة مستخدم',hint:'إدارة حسابات النظام',icon:'＋',href:'/users#user-add',keywords:'مستخدم حساب صلاحية'}]};
    if(path.startsWith('/notifications')) return {key:'notifications',label:'مركز المتابعة',actions:[{label:'تحديث المتابعة',hint:'إعادة تحميل التنبيهات التشغيلية',icon:'↻',href:'/notifications',keywords:'إشعارات تحديث متابعة'}]};
    return {key:'workspace',label:'مساحة العمل',actions:[]};
  };
  const contextualActions=()=>{
    const ctx=pageContext();
    const role=document.body.dataset.activeRole||'';
    const actions=[...ctx.actions];
    // Administration is governance-only: never expose an operational mutation shortcut here.
    if(ctx.key==='admin') return [...actions, ...baseActions.filter(x=>!['تسجيل حركة','إضافة موظف'].includes(x.label))];
    // Manager/supervisor navigation remains page-oriented; operational actions stay on Home.
    if(ctx.key!=='home') return [...actions,...baseActions];
    return [...actions,...baseActions.filter(x=>!['الرئيسية'].includes(x.label))];
  };

  function render(items){
    paletteItems=items; activeIndex=Math.min(activeIndex,Math.max(items.length-1,0));
    if(!results)return;
    if(!items.length){results.innerHTML='<div class="interactive-empty">لا توجد نتيجة مطابقة.</div>';return;}
    results.innerHTML=items.map((x,i)=>`<button type="button" class="interactive-result ${i===activeIndex?'is-active':''}" data-index="${i}"><span class="interactive-result-icon">${x.icon||'•'}</span><span class="interactive-result-copy"><strong>${esc(x.label)}</strong><small>${esc(x.hint||'')}</small></span><span class="interactive-result-arrow">↵</span></button>`).join('');
    qsa('.interactive-result',results).forEach(b=>b.addEventListener('mouseenter',()=>setActive(Number(b.dataset.index))));
    qsa('.interactive-result',results).forEach(b=>b.addEventListener('click',()=>choose(Number(b.dataset.index))));
  }
  function setActive(i){if(!paletteItems.length)return;activeIndex=(i+paletteItems.length)%paletteItems.length;qsa('.interactive-result',results).forEach((b,n)=>b.classList.toggle('is-active',n===activeIndex));qsa('.interactive-result',results)[activeIndex]?.scrollIntoView({block:'nearest'});}
  function choose(i){const item=paletteItems[i];if(!item)return;if(item.href)location.href=item.href;}
  function open(){if(!palette)return;palette.hidden=false;palette.setAttribute('aria-hidden','false');document.body.classList.add('interactive-palette-open');activeIndex=0;if(input){input.value='';input.placeholder='في '+(pageContext().label||'مساحة العمل')+'… اكتب أمرًا أو صفحة';input.focus();}render(contextualActions());}
  function close(){if(!palette)return;palette.hidden=true;palette.setAttribute('aria-hidden','true');document.body.classList.remove('interactive-palette-open');trigger?.focus();}
  function searchActions(q){
    const needle=(q||'').toLowerCase();
    const actions=contextualActions(); const filtered=actions.filter(x=>(x.label+' '+x.hint+' '+x.keywords).toLowerCase().includes(needle));
    render(filtered);
  }
  trigger?.addEventListener('click',open);
  qsa('[data-palette-close]').forEach(x=>x.addEventListener('click',close));
  input?.addEventListener('input',()=>searchActions(input.value.trim()));
  input?.addEventListener('keydown',e=>{if(e.key==='ArrowDown'){e.preventDefault();setActive(activeIndex+1);}else if(e.key==='ArrowUp'){e.preventDefault();setActive(activeIndex-1);}else if(e.key==='Enter'){e.preventDefault();choose(activeIndex);}else if(e.key==='Escape'){e.preventDefault();close();}});
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();open();}else if(e.key==='Escape'&&!palette?.hidden)close();});

  window.toast=function(message,type='info',duration=3200){const region=qs('#toastRegion');if(!region)return;const el=document.createElement('div');el.className='interactive-toast interactive-toast-'+type;el.textContent=message;region.appendChild(el);requestAnimationFrame(()=>el.classList.add('is-visible'));setTimeout(()=>{el.classList.remove('is-visible');setTimeout(()=>el.remove(),220)},duration);};

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
