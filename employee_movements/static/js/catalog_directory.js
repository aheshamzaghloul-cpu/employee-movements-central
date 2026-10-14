(function () {
  'use strict';
  const root = document.querySelector('[data-catalog-root]');
  if (!root) return;
  const items = [...root.querySelectorAll('[data-catalog-item]')];
  const search = root.querySelector('[data-catalog-search]');
  const status = root.querySelector('[data-catalog-status]');
  const governorate = root.querySelector('[data-catalog-governorate]');
  const count = root.querySelector('[data-catalog-count]');
  const empty = root.querySelector('[data-catalog-empty]');
  const normalize = value => (value || '').normalize('NFKC').toLocaleLowerCase('ar-EG').replace(/[\u064B-\u065F\u0670\u0640]/g, '').replace(/[أإآ]/g, 'ا').replace(/ى/g, 'ي').replace(/\s+/g, ' ').trim();
  const more = root.querySelector('[data-catalog-more]');
  const PAGE_SIZE = 12;
  let visibleLimit = PAGE_SIZE;
  function applyFilters() {
    const q = normalize(search?.value);
    const wantedStatus = status?.value || 'all';
    const wantedGovernorate = governorate?.value || 'all';
    const matched = items.filter(item => (!q || window.employeeSearchMatches(q, item.dataset.search))
      && (wantedStatus === 'all' || item.dataset.status === wantedStatus)
      && (wantedGovernorate === 'all' || item.dataset.governorate === wantedGovernorate));
    const shown = new Set(matched.slice(0, visibleLimit));
    items.forEach(item => { item.hidden = !shown.has(item); });
    if (count) count.textContent = String(matched.length);
    if (empty) empty.hidden = items.length === 0 || matched.length !== 0;
    if (more) {
      more.hidden = matched.length <= visibleLimit;
      more.textContent = `عرض المزيد (${Math.min(PAGE_SIZE, matched.length - visibleLimit)} من ${matched.length})`;
      more.setAttribute('aria-label', `عرض مزيد من النتائج؛ المعروض ${Math.min(visibleLimit, matched.length)} من ${matched.length}`);
    }
  }
  const resetLimit = () => { visibleLimit = PAGE_SIZE; applyFilters(); };
  search?.addEventListener('input', resetLimit);
  status?.addEventListener('change', resetLimit);
  governorate?.addEventListener('change', resetLimit);
  more?.addEventListener('click', () => { visibleLimit += PAGE_SIZE; applyFilters(); });
  root.querySelector('[data-catalog-reset]')?.addEventListener('click', () => {
    if (search) search.value = '';
    if (status) status.value = 'all';
    if (governorate) governorate.value = 'all';
    visibleLimit = PAGE_SIZE;
    root.querySelector('.catalog-advanced-filters')?.removeAttribute('open');
    applyFilters();
    search?.focus();
  });
  root.querySelectorAll('.catalog-edit-disclosure').forEach(details => details.addEventListener('toggle', () => {
    if (!details.open) return;
    const input = details.querySelector('input,select');
    input?.focus({ preventScroll: true });
  }));
  const addPanel = root.querySelector('#branch-add, #governorate-add');
  if (addPanel && window.location.hash === `#${addPanel.id}`) {
    addPanel.open = true;
    requestAnimationFrame(() => addPanel.scrollIntoView({ block: 'center', behavior: 'smooth' }));
  }
  applyFilters();
})();
