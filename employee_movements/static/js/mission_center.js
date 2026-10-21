/* Unified mission workflow: select one record, then run one authorized action. */
(function () {
  'use strict';

  function initMissionDateRangeFilter() {
    const form = document.getElementById('missionFilterForm');
    const from = document.getElementById('missionDateFrom');
    const to = document.getElementById('missionDateTo');
    const clientError = document.getElementById('missionDateRangeClientError');
    const serverError = document.getElementById('missionDateRangeError');
    if (!form || !from || !to || !clientError) return;

    const message = 'تاريخ النهاية لا يجوز أن يسبق تاريخ البداية. صحّح التاريخين قبل عرض النتائج.';

    function updateRangeState() {
      const invalid = Boolean(from.value && to.value && from.value > to.value);
      const visibleError = serverError || clientError;

      to.setCustomValidity(invalid ? message : '');
      from.setAttribute('max', to.value || '');
      to.setAttribute('min', from.value || '');

      if (serverError) serverError.hidden = !invalid;
      clientError.hidden = !invalid || Boolean(serverError);

      [from, to].forEach((field) => {
        if (invalid) field.setAttribute('aria-invalid', 'true');
        else field.removeAttribute('aria-invalid');

        const descriptions = new Set(
          (field.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean)
        );
        if (invalid && visibleError?.id) descriptions.add(visibleError.id);
        else {
          descriptions.delete('missionDateRangeClientError');
          descriptions.delete('missionDateRangeError');
        }
        if (descriptions.size) field.setAttribute('aria-describedby', [...descriptions].join(' '));
        else field.removeAttribute('aria-describedby');
      });
      return invalid;
    }

    from.addEventListener('input', updateRangeState);
    from.addEventListener('change', updateRangeState);
    to.addEventListener('input', updateRangeState);
    to.addEventListener('change', updateRangeState);
    form.addEventListener('submit', (event) => {
      if (!updateRangeState()) return;
      event.preventDefault();
      to.focus();
      to.reportValidity();
    });
    updateRangeState();
  }

  function initMissionEmployeeSearch() {
    const input = document.getElementById('missionEmployeeLookup');
    const hidden = document.getElementById('missionEmployeeId');
    const results = document.getElementById('missionEmployeeOptions');
    const form = input?.closest('form');
    if (!input || !hidden || !results || !form) return;

    let timer = null;
    let controller = null;
    let sequence = 0;
    const closeResults = () => {
      results.hidden = true;
      results.replaceChildren();
      input.setAttribute('aria-expanded', 'false');
    };

    input.addEventListener('input', () => {
      const currentSequence = ++sequence;
      hidden.value = '';
      input.setCustomValidity('');
      if (timer) window.clearTimeout(timer);
      if (controller) controller.abort();
      closeResults();
      const query = input.value.trim();
      if (query.length < 2) return;
      timer = window.setTimeout(async () => {
        controller = new AbortController();
        try {
          const response = await fetch(`/employee-search?q=${encodeURIComponent(query)}`, {
            headers: { Accept: 'application/json' },
            signal: controller.signal,
          });
          if (!response.ok) throw new Error('employee_search_failed');
          const payload = await response.json();
          if (currentSequence !== sequence) return;
          const items = (payload.results || []).slice(0, 12);
          if (!items.length) {
            const empty = document.createElement('div');
            empty.className = 'mission-employee-search-empty';
            empty.textContent = 'لا توجد نتيجة؛ جرّب جزءًا آخر من الاسم أو الكود.';
            results.append(empty);
          } else {
            items.forEach((item) => {
              const option = document.createElement('button');
              option.type = 'button';
              option.className = 'mission-employee-search-option';
              option.setAttribute('role', 'option');
              const code = item.code || 'بدون كود';
              const branch = item.branch || 'فرع غير محدد';
              const governorate = item.governorate || 'محافظة غير محددة';
              const approximate = item.match_kind === 'approximate';
              option.textContent = `${item.name} — ${code} · ${branch} · ${governorate}${approximate ? ' · اقتراح تقريبي يحتاج تأكيدًا' : ''}`;
              option.addEventListener('click', () => {
                hidden.value = String(item.id);
                input.value = option.textContent;
                input.setCustomValidity('');
                closeResults();
              });
              results.append(option);
            });
          }
          results.hidden = false;
          input.setAttribute('aria-expanded', 'true');
        } catch (error) {
          if (error?.name !== 'AbortError' && currentSequence === sequence) {
            const message = document.createElement('div');
            message.className = 'mission-employee-search-empty';
            message.textContent = 'تعذر البحث الآن. أعد المحاولة أو استخدم صفحة الموظفين.';
            results.replaceChildren(message);
            results.hidden = false;
            input.setAttribute('aria-expanded', 'true');
          }
        }
      }, 180);
    });

    form.addEventListener('submit', (event) => {
      if (input.value.trim() && !hidden.value) {
        event.preventDefault();
        input.setCustomValidity('اختر موظفًا من قائمة نتائج البحث أو امسح نص البحث لعرض جميع الموظفين.');
        input.reportValidity();
      } else {
        input.setCustomValidity('');
      }
    });
    document.addEventListener('click', (event) => {
      if (!results.contains(event.target) && event.target !== input) closeResults();
    });
  }

  function initMissionCenter() {
    initMissionDateRangeFilter();
    initMissionEmployeeSearch();
    const workspace = document.querySelector('[data-mission-selection]');
    const table = document.querySelector('.mission-center-table');
    if (!workspace || !table) return;

    const selectors = [...table.querySelectorAll('[data-mission-select]')];
    if (!selectors.length) return;

    const label = workspace.querySelector('[data-selected-mission-label]');
    const hint = workspace.querySelector('[data-selected-mission-hint]');
    const printLink = workspace.querySelector('[data-selected-print]');
    const editLink = workspace.querySelector('[data-selected-edit]');
    const closeForm = workspace.querySelector('[data-selected-close-form]');
    const closeButton = workspace.querySelector('[data-selected-close]');
    const reopenForm = workspace.querySelector('[data-selected-reopen-form]');
    const requestForm = workspace.querySelector('[data-selected-request-form]');
    const requestReason = workspace.querySelector('[data-selected-request-reason]');
    const requestButton = workspace.querySelector('[data-selected-request]');

    function setLink(link, enabled, href) {
      if (!link) return;
      link.href = enabled && href ? href : '#';
      link.setAttribute('aria-disabled', String(!enabled));
      link.tabIndex = enabled ? 0 : -1;
      link.classList.toggle('is-disabled', !enabled);
    }

    function setForm(form, button, enabled, action) {
      if (form && enabled && action) {
        form.action = action;
        const returnTo = form.querySelector('input[name="return_to"]');
        if (returnTo) returnTo.value = `${window.location.pathname}${window.location.search}`;
      } else if (form) form.action = '#';
      if (button) button.disabled = !enabled;
    }

    function clearSelection() {
      selectors.forEach((radio) => {
        radio.checked = false;
        radio.closest('[data-mission-row]')?.classList.remove('is-selected');
      });
      if (label) label.textContent = 'لم يتم اختيار مأمورية';
      if (hint) hint.textContent = 'اختر صفًا واحدًا من الجدول لتفعيل أوامر الطباعة أو التعديل أو الإغلاق المتاحة لك.';
      setLink(printLink, false, '');
      setLink(editLink, false, '');
      setForm(closeForm, closeButton, false, '');
      setForm(requestForm, requestButton, false, '');
      if (requestReason) requestReason.disabled = true;
    }

    function selectMission(radio) {
      const row = radio?.closest('[data-mission-row]');
      if (!row) {
        clearSelection();
        return;
      }

      selectors.forEach((item) => {
        const itemRow = item.closest('[data-mission-row]');
        const isSelected = item === radio;
        item.checked = isSelected;
        itemRow?.classList.toggle('is-selected', isSelected);
      });

      const id = row.dataset.missionId;
      const state = row.dataset.missionState;
      const hasDates = row.dataset.hasDates === '1';
      const canPrint = row.dataset.canPrint === '1';
      const canManage = row.dataset.canManage === '1';
      const canRequestEdit = row.dataset.canRequestEdit === '1';
      const hasPendingEditRequest = row.dataset.hasPendingEditRequest === '1';
      const closed = state === 'مغلقة';
      const canEdit = canManage && !closed;
      const canClose = canManage && !closed && hasDates;
      const printUrl = row.dataset.printUrl;
      const editUrl = row.dataset.editUrl;

      if (label) label.textContent = `${row.dataset.missionLabel || 'المأمورية'} · سجل #${id}`;
      setLink(printLink, canPrint, printUrl);
      setLink(editLink, canEdit, editUrl);
      setForm(closeForm, closeButton, canClose, `/reports/assignments/mission-close/${id}`);
      setForm(requestForm, requestButton, canRequestEdit, `/reports/assignments/mission-edit-request/${id}`);
      if (requestReason) {
        requestReason.disabled = !canRequestEdit;
        if (!canRequestEdit) requestReason.value = '';
      }

      const messages = [];
      if (!canPrint) messages.push('لا تتوفر لك صلاحية الطباعة لهذا السجل.');
      if (canEdit) messages.push('يمكنك تعديل بيانات المأمورية.');
      if (!closed && canManage && !hasDates) messages.push('أدخل تاريخ البداية والنهاية من «تعديل البيانات» قبل الإغلاق.');
      if (canClose) messages.push('يمكن إغلاق المأمورية بعد تأكيد العملية.');
      if (canRequestEdit) messages.push('اكتب سببًا واضحًا لا يقل عن 5 أحرف ثم أرسل طلب التعديل.');
      if (hasPendingEditRequest) messages.push('يوجد بالفعل طلب تعديل قيد المراجعة لهذه المأمورية؛ لن يُسمح بإنشاء طلب مكرر.');
      if (!canManage && !canRequestEdit && !hasPendingEditRequest) messages.push('المأمورية للعرض والطباعة فقط ضمن صلاحيات حسابك.');
      if (hint) hint.textContent = messages.join(' ');
    }

    selectors.forEach((radio) => {
      radio.addEventListener('change', () => selectMission(radio));
      radio.closest('[data-mission-row]')?.addEventListener('click', (event) => {
        if (event.target.closest('a, button, input, select, textarea, form, label')) return;
        radio.checked = true;
        selectMission(radio);
      });
    });

    // Clear selection whenever a selected row is hidden by the local table
    // search or the show-more/show-less control. Otherwise actions could still
    // target a record that is no longer visible to the user.
    const showMore = table.closest('.ui-table-wrap')?.querySelector(':scope > .smart-data-more');
    showMore?.addEventListener('click', () => {
      const selected = table.querySelector('[data-mission-row].is-selected');
      if (selected && selected.hidden) clearSelection();
    });
    if (window.MutationObserver) {
      const rowVisibilityObserver = new MutationObserver((changes) => {
        if (changes.some((change) => change.attributeName === 'hidden')) {
          const selected = table.querySelector('[data-mission-row].is-selected');
          if (selected && selected.hidden) clearSelection();
        }
      });
      rowVisibilityObserver.observe(table.tBodies[0], {
        subtree: true,
        attributes: true,
        attributeFilter: ['hidden'],
      });
    }

    printLink?.addEventListener('click', (event) => {
      if (printLink.getAttribute('aria-disabled') === 'true') event.preventDefault();
    });
    editLink?.addEventListener('click', (event) => {
      if (editLink.getAttribute('aria-disabled') === 'true') event.preventDefault();
    });
    closeForm?.addEventListener('submit', (event) => {
      if (!window.confirm('هل تريد إغلاق المأمورية المختارة؟ لن يتم تنفيذ الإغلاق إلا بعد تحقق الخادم من التواريخ والتعارضات والصلاحيات.')) event.preventDefault();
    });
    // Optional for templates that expose a reopen action. Resolve it first so
    // pages without that control do not throw a ReferenceError during setup.
    reopenForm?.addEventListener('submit', (event) => {
      if (!window.confirm('هل تريد إعادة فتح المأمورية المختارة؟')) event.preventDefault();
    });

    clearSelection();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initMissionCenter, { once: true });
  else initMissionCenter();
})();
