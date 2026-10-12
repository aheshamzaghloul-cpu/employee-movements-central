# QA review — v68.22.22

- Normalized Excel lookup keys for Arabic-Indic/Persian digits and float-like numeric codes.
- Added a static contract test for digit/code normalization and SVG fill opt-in.
- Applied outline-only SVG fill suppression to common controls/icons; intentionally filled SVGs must opt in with `data-icon-fill`.
- Browser visual testing: not performed.
- Flask runtime/integration tests: unavailable in this environment.
- Production database changed: no. Deployment: no.
