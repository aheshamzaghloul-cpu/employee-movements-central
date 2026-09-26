# v35.83

Mission PDF precision fix:
- Register the exact source Arabic font before rendering variable data, so Arabic text stays connected and shaped correctly.
- Preserve the original form borders by redacting only the source variable text regions.
- Keep employee name, basic branch, mission destination, dates, and approval destination inside their original boxes.
- Render the upper-right mission number/status visually as `40873 مغلقة` or `40873 تحت التحرير` without splitting the Arabic status.
- Preserve the open-assignment print-only end-date behavior from v35.82.
