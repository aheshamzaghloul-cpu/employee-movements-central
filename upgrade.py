from pathlib import Path
p=Path('/mnt/data/v49.12work')
# Add canonical DS classes alongside semantic hooks.
f=p/'templates/employees.html'
s=f.read_text()
repls={
'class="employees-page-head"':'class="ds-page-head employees-page-head"',
'class="ds-module-card employee-dashboard-panel employee-add-panel"':'class="ds-module-card ds-employee-module employee-dashboard-panel employee-add-panel"',
'class="employee-panel-head"':'class="ds-module-head employee-panel-head"',
'class="employee-panel-icon"':'class="ds-icon-tile employee-panel-icon"',
'class="employee-add-grid"':'class="ds-form-grid ds-form-grid-employee employee-add-grid"',
'class="employee-add-actions"':'class="ds-form-actions employee-add-actions"',
'class="ds-module-card employee-dashboard-panel employee-tools-panel"':'class="ds-module-card ds-employee-module employee-dashboard-panel employee-tools-panel"',
'class="employee-tools-grid employee-tools-grid-clean"':'class="ds-card-grid ds-employee-tools employee-tools-grid employee-tools-grid-clean"',
'class="employee-tool-card"':'class="ds-tool-card employee-tool-card"',
'class="ds-module-card employee-dashboard-panel employee-list-panel"':'class="ds-module-card ds-employee-module employee-dashboard-panel employee-list-panel"',
'class="employee-list-head"':'class="ds-module-head employee-list-head"',
'class="employee-branch-groups"':'class="ds-group-list employee-branch-groups"',
'class="employee-gov-group"':'class="ds-group employee-gov-group"',
'class="employee-gov-head"':'class="ds-group-head employee-gov-head"',
'class="employee-branch-list"':'class="ds-branch-list employee-branch-list"',
'class="employee-branch-group ds-branch-group"':'class="ds-branch-group employee-branch-group"',
'class="employee-branch-title"':'class="ds-branch-title employee-branch-title"',
'class="employee-branch-icon"':'class="ds-branch-icon employee-branch-icon"',
'class="employee-branch-toggle"':'class="ds-branch-toggle employee-branch-toggle"',
'class="employee-cards-grid"':'class="ds-item-grid employee-cards-grid"',
'class="employee-dashboard-card ds-item-card"':'class="ds-item-card employee-dashboard-card"',
'class="employee-card-person"':'class="ds-item-person employee-card-person"',
'class="employee-card-avatar"':'class="ds-avatar employee-card-avatar"',
'class="employee-card-data"':'class="ds-item-data employee-card-data"',
'class="employee-card-actions"':'class="ds-item-actions employee-card-actions"',
'class="employee-empty"':'class="ds-empty employee-empty"',
}
for a,b in repls.items(): s=s.replace(a,b)
f.write_text(s)

f=p/'templates/employee.html'
s=f.read_text()
repls={
'class="employee-head"':'class="ds-employee-head employee-head"',
'class="ds-card employee-profile"':'class="ds-card ds-employee-profile employee-profile"',
'class="ds-card-grid employee-last-cards"':'class="ds-card-grid ds-employee-last-cards employee-last-cards"',
'class="ds-card last-card last-{{loop.index}}"':'class="ds-card ds-employee-last-card last-card last-{{loop.index}}"',
'class="last-card-head"':'class="ds-employee-last-head last-card-head"',
'class="last-badge"':'class="ds-badge last-badge"',
'class="last-main"':'class="ds-employee-last-main last-main"',
'class="last-footer"':'class="ds-employee-last-footer last-footer"',
'class="ds-card ds-table-wrap employee-history"':'class="ds-card ds-table-wrap ds-employee-history employee-history"',
'class="history-tools"':'class="ds-employee-history-tools history-tools"',
'class="history-filters"':'class="ds-filter-group history-filters"',
'class="history-search"':'class="ds-search-input history-search"',
}
for a,b in repls.items(): s=s.replace(a,b)
f.write_text(s)

css=p/'static/design49.css'
s=css.read_text()
section=r'''
/* =========================================================
   v49.12 — Employee Module Canonical Visual Layer
   Semantic employee-* classes remain as behavior hooks.
   Visual ownership is centralized in ds-employee-* / ds-*.
   ========================================================= */
.ds-employee-module{padding:24px}
.ds-module-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-bottom:16px;margin-bottom:18px;border-bottom:1px solid var(--ds-line)}
.ds-module-head h2{margin:0;font-size:20px;font-weight:800;color:var(--ds-text)}
.ds-module-head p{margin:5px 0 0;color:var(--ds-muted);font-size:11px;line-height:1.8}
.ds-form-grid-employee{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.ds-form-grid-employee label{display:grid;gap:7px;color:#4e667e;font-size:12px;font-weight:800}
.ds-form-grid-employee input,.ds-form-grid-employee select{width:100%;min-width:0;height:46px;border:1px solid var(--ds-line);border-radius:12px;background:#fff;color:var(--ds-text);padding:0 12px;font:inherit;font-size:12px;outline:0}
.ds-form-grid-employee input:focus,.ds-form-grid-employee select:focus{border-color:#8fb5ea;box-shadow:0 0 0 3px rgba(62,122,214,.12)}
.ds-form-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ds-form-actions span{font-size:10px;color:var(--ds-muted)}
.ds-card-grid.ds-employee-tools{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.ds-tool-card{display:grid;grid-template-columns:42px 1fr auto;align-items:center;gap:12px;min-height:68px;padding:13px 14px;border:1px solid var(--ds-line);border-radius:13px;background:#fff;color:var(--ds-text);text-decoration:none;transition:.15s ease}
.ds-tool-card:hover{border-color:#b7cbe6;background:#fbfdff;box-shadow:var(--ds-shadow-sm)}
.ds-tool-card b{font-size:12px}.ds-tool-card small{display:block;margin-top:3px;color:var(--ds-muted);font-size:9px;line-height:1.6}.ds-tool-card>strong{font-size:10px;color:var(--ds-blue)}
.ds-group-list{display:grid;gap:16px}
.ds-group{border:1px solid var(--ds-line);border-radius:15px;background:#fff;overflow:hidden}
.ds-group-head{display:flex;align-items:center;gap:10px;padding:14px 16px;background:#f8fafc;border-bottom:1px solid var(--ds-line)}
.ds-group-head span{font-size:9px;color:var(--ds-muted)}.ds-group-head strong{font-size:12px;color:var(--ds-text)}.ds-group-head em{margin-inline-start:auto;font-style:normal;font-size:9px;color:var(--ds-muted)}
.ds-branch-list{padding:12px}
.ds-branch-group{border:1px solid var(--ds-line);border-radius:14px;background:#fbfcfe;margin:0 0 10px;overflow:hidden}
.ds-branch-group:last-child{margin-bottom:0}
.ds-branch-group>summary{display:flex;align-items:center;justify-content:space-between;min-height:56px;padding:0 14px;cursor:pointer;list-style:none}
.ds-branch-group>summary::-webkit-details-marker{display:none}
.ds-branch-title{display:flex;align-items:center;gap:10px}.ds-branch-title strong{font-size:12px;color:var(--ds-text)}.ds-branch-title small{display:block;margin-top:3px;color:var(--ds-muted);font-size:9px}
.ds-branch-icon{width:34px;height:34px;border-radius:10px;background:var(--ds-blue-soft);color:var(--ds-blue);display:grid;place-items:center}.ds-branch-toggle{display:grid;place-items:center;width:30px;height:30px;color:#6c8195;transition:transform .15s ease}.ds-branch-group[open] .ds-branch-toggle{transform:rotate(180deg)}
.ds-item-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;padding:12px;background:#fff}
.ds-item-card{border:1px solid var(--ds-line);border-radius:15px;background:#fff;box-shadow:var(--ds-shadow-sm);padding:15px;min-width:0}
.ds-item-person{display:flex;align-items:center;gap:10px;color:var(--ds-text);text-decoration:none;min-width:0}.ds-item-person>span:last-child{min-width:0}.ds-item-person strong{display:block;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.ds-item-person small{display:block;margin-top:3px;color:var(--ds-muted);font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ds-avatar{width:38px;height:38px;flex:0 0 38px;border-radius:12px;background:var(--ds-blue-soft);color:var(--ds-blue);display:grid;place-items:center;font-weight:800;font-size:13px}
.ds-item-data{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:13px;padding-top:12px;border-top:1px solid #edf2f7}.ds-item-data span{min-width:0}.ds-item-data small{display:block;color:var(--ds-muted);font-size:9px}.ds-item-data b{display:block;margin-top:3px;color:#3d5870;font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ds-item-actions{display:flex;justify-content:flex-end;margin-top:9px}.ds-item-actions:empty{display:none}
.ds-employee-head{display:flex;align-items:flex-start;gap:16px}.ds-employee-head h1{margin:0;font-size:27px;font-weight:800;color:var(--ds-text)}
.ds-employee-profile{padding:24px}.ds-employee-profile b{font-size:11px;color:#4e667e}.ds-employee-profile .ds-hint{margin-top:5px;font-size:11px;color:var(--ds-muted)}
.ds-employee-last-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:18px}
.ds-employee-last-card{padding:18px!important;margin:0!important}.ds-employee-last-head{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-bottom:12px;border-bottom:1px solid var(--ds-line)}.ds-employee-last-head h3{margin:0;font-size:14px}.ds-employee-last-main{margin:16px 0 8px;font-size:16px;font-weight:800;color:var(--ds-text)}.ds-employee-last-footer{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:16px;font-size:10px}.ds-employee-last-footer a{color:var(--ds-blue);font-weight:800;text-decoration:none}
.ds-employee-history{padding:22px!important}.ds-employee-history-tools{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.ds-filter-group{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.ds-search-input{height:40px;min-width:240px;border:1px solid var(--ds-line);border-radius:10px;background:#fff;padding:0 12px;color:var(--ds-text);font:inherit;font-size:11px;outline:0}.ds-search-input:focus{border-color:#8fb5ea;box-shadow:0 0 0 3px rgba(62,122,214,.12)}
@media(max-width:900px){.ds-form-grid-employee{grid-template-columns:repeat(2,minmax(0,1fr))}.ds-item-grid{grid-template-columns:1fr}.ds-employee-last-cards{grid-template-columns:1fr 1fr}.ds-card-grid.ds-employee-tools{grid-template-columns:1fr}}
@media(max-width:620px){.ds-form-grid-employee{grid-template-columns:1fr}.ds-employee-module{padding:16px}.ds-module-head{align-items:flex-start}.ds-employee-last-cards{grid-template-columns:1fr}.ds-employee-history-tools{align-items:stretch;flex-direction:column}.ds-search-input{min-width:0;width:100%}.ds-employee-head h1{font-size:23px}}
'''
if 'v49.12 — Employee Module Canonical Visual Layer' not in s:
    s += '\n'+section
css.write_text(s)

# version/readme
(p/'VERSION.md').write_text('v49.12 — توحيد وحدة الموظفين بصريًا ضمن Design System\n')
(p/'README_V49.12_AR.md').write_text('''# v49.12 — توحيد وحدة الموظفين\n\nتم توحيد قائمة الموظفين وملف الموظف ضمن طبقة Design System معيارية، مع إبقاء كلاسات employee-* اللازمة كسلوك/JavaScript فقط.\n\n## تم\n- نماذج الموظفين\n- بطاقات الموظفين\n- المحافظات والفروع\n- أدوات الموظفين\n- ملف الموظف\n- آخر إجازة/انتداب/إذن\n- سجل الحركات\n- حالات الهاتف والاستجابة\n''')
