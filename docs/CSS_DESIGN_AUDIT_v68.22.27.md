# CSS Design Audit — v68.22.27

## Scope
Static audit of `employee_movements/static/css/app.css`; no browser/runtime claim is made.

## Results
- CSS parser errors: **0**.
- Distinct selectors with multiple rule blocks: **285**.
- Highest repeated selector stacks include `.premium-topbar`, `.premium-page-intro`, `:root`, `html`, `.ui-main`, `.login-shell`, and `.premium-sidebar`.
- These repeats are not all safe deletion candidates: several are scoped to different responsive breakpoints, and later design layers intentionally override earlier tokens.
- Removed one redundant root-level `svg[data-icon-fill] { fill: currentColor; }` declaration because the earlier combined rule `svg[data-icon-fill], svg[data-icon-fill] * { fill: currentColor; }` already covers the root and descendants.

## Remaining review before launch
1. Visually inspect sidebar/topbar/page headers at desktop, tablet, and mobile widths.
2. Test line and filled SVGs, especially search/print icons and status icons.
3. Inspect form controls, table overflow, empty states, and print layouts in the actual browser.
4. Run Flask + database-backed workflow tests in the target environment.

## Limitations
This is a conservative static cleanup. No mass selector consolidation was performed because media-query context and cascade order can alter layout. Not deployed; production database unchanged.
