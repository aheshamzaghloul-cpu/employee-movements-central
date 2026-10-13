/* Arabic-aware normalization shared by every client-side search surface. */
(function (global) {
  'use strict';
  const digitMap = Object.create(null);
  '٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹'.split('').forEach((digit, index) => {
    digitMap[digit] = String(index % 10);
  });
  const arabicMarks = /[\u064B-\u065F\u0670\u06D6-\u06ED]/g;
  global.normalizeEmployeeSearchText = function (value) {
    return String(value == null ? '' : value)
      .normalize('NFKC')
      .replace(/[٠-٩۰-۹]/g, digit => digitMap[digit] || digit)
      .replace(/[أإآٱ]/g, 'ا')
      .replace(/ى/g, 'ي')
      .replace(/[\u0640]/g, '')
      .replace(arabicMarks, '')
      .replace(/[\u200e\u200f\u202a-\u202e]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLocaleLowerCase('ar');
  };

  global.getEmployeeSearchableRowText = function (row, table) {
    if (!row) return '';
    const norm = global.normalizeEmployeeSearchText;
    let cells = Array.from(row.cells || []).filter(cell => !cell.hasAttribute('data-search-ignore'));
    const headerRow = table && (table.tHead?.rows?.[0] || Array.from(table.rows || []).find(candidate => candidate.querySelector('th')));
    const headers = Array.from(headerRow?.cells || []);
    if (cells.length > 1 && headers.length === (row.cells || []).length) {
      const lastHeader = norm(headers[headers.length - 1]?.textContent || '');
      if (/اجراء|خيارات|اوامر/.test(lastHeader)) cells = cells.slice(0, -1);
    }
    return cells.map(cell => {
      const clone = cell.cloneNode(true);
      const fieldValues = [];
      cell.querySelectorAll('input, textarea, select').forEach(field => {
        if (field.hasAttribute('data-search-ignore')) return;
        const tag = field.tagName.toLowerCase();
        if (tag === 'select') {
          const selected = Array.from(field.selectedOptions || []).map(option => option.textContent || '').filter(Boolean);
          fieldValues.push(...selected);
        } else if (tag === 'textarea') {
          if (!field.disabled && field.value) fieldValues.push(field.value);
        } else {
          const type = (field.type || 'text').toLowerCase();
          if (!['hidden', 'submit', 'button', 'reset', 'checkbox', 'radio', 'password', 'file', 'image'].includes(type) && !field.disabled && field.value) {
            fieldValues.push(field.value);
          }
        }
      });
      clone.querySelectorAll('button, input, textarea, select, [data-search-ignore], [data-confirm], svg, [type="hidden"], [type="submit"], [type="button"], [type="reset"], [type="checkbox"], [type="radio"], [type="password"], [type="file"]').forEach(node => node.remove());
      return [clone.textContent || '', ...fieldValues].join(' ');
    }).join(' ').replace(/\s+/g, ' ').trim();
  };
})(window);
