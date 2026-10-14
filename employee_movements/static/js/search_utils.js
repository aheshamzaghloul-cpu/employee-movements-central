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
      .replace(/ة/g, 'ه')
      .replace(/ئ/g, 'ي')
      .replace(/ؤ/g, 'و')
      .replace(/[\u0640]/g, '')
      .replace(arabicMarks, '')
      .replace(/[\u200e\u200f\u202a-\u202e]/g, '')
      .replace(/\s+/g, ' ')
      .trim()
      .toLocaleLowerCase('ar');
  };

  function tokenEditDistance(left, right, maxDistance) {
    if (left === right) return 0;
    if (!left || !right || Math.abs(left.length - right.length) > maxDistance) return maxDistance + 1;
    if (left.length > right.length) { const swap = left; left = right; right = swap; }
    let prev = Array.from({ length: left.length + 1 }, (_, i) => i);
    for (let j = 1; j <= right.length; j++) {
      const curr = [j]; let rowMin = curr[0];
      for (let i = 1; i <= left.length; i++) {
        const cost = left[i - 1] === right[j - 1] ? 0 : 1;
        curr[i] = Math.min(curr[i - 1] + 1, prev[i] + 1, prev[i - 1] + cost);
        rowMin = Math.min(rowMin, curr[i]);
      }
      if (rowMin > maxDistance) return maxDistance + 1;
      prev = curr;
    }
    return prev[left.length];
  }

  /* Conservative fuzzy matching for local filters. This only filters visible
     results; it never chooses or mutates a record. Numeric codes require at least
     five digits and tolerate one typo at most. */
  global.employeeSearchMatches = function (query, candidateText) {
    const needle = global.normalizeEmployeeSearchText(query);
    const haystack = global.normalizeEmployeeSearchText(candidateText);
    if (!needle) return true;
    const queryTokens = needle.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    const candidateTokens = haystack.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    // Short numeric fragments are too common to use as substring filters.
    // Accept exact numeric tokens and the known legacy 200-prefix variation,
    // but never let `123` match a different code like `81234` just by overlap.
    if (/^\d{1,2}$/.test(needle)) return candidateTokens.some(item => /^\d+$/.test(item) && item === needle);
    if (/^\d{3,4}$/.test(needle)) return candidateTokens.some(item => /^\d+$/.test(item) && (
      item === needle || (item.startsWith('200') && item.slice(3) === needle) || (needle.startsWith('200') && needle.slice(3) === item)
    ));
    if (haystack.includes(needle)) return true;
    if (!queryTokens.length || !candidateTokens.length) return false;
    return queryTokens.every(token => {
      if (candidateTokens.some(item => item === token || (item.length >= 3 && token.length >= 3 && (item.includes(token) || token.includes(item))))) return true;
      const isNumeric = /^\d+$/.test(token);
      const maxDistance = isNumeric ? (token.length >= 5 ? 1 : 0) : (token.length >= 7 ? 2 : token.length >= 4 ? 1 : 0);
      if (!maxDistance) return false;
      return candidateTokens.some(item => {
        if (isNumeric !== /^\d+$/.test(item)) return false;
        const longer = Math.max(item.length, token.length);
        if (longer > token.length + maxDistance || longer < token.length - maxDistance) return false;
        return tokenEditDistance(token, item, maxDistance) <= maxDistance;
      });
    });
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
