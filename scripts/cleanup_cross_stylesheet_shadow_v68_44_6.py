"""Remove declarations proven overridden by the global stylesheet loaded later.

This complements cleanup_shadowed_declarations_v68_44_5.py by checking across
stylesheets that base.html always loads in this order:
  app.css -> route-specific page CSS -> design-system-cyan.css.
Only declarations from pre-design-system stylesheets are candidates. The target
must be an exact single selector in the exact same conditional context, with the
same property and equal-or-higher !important priority. Rules with comments,
parse errors, grouped selectors, nested rules, and duplicate declarations inside
one rule are excluded. CSS files loaded conditionally *after* the design system
are never used as global proof.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from pathlib import Path
import json, sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.cleanup_shadowed_declarations_v68_44_5 import collect_rules, property_key

CSS_ROOT = ROOT / "employee_movements" / "static" / "css"
CANONICAL = CSS_ROOT / "design-system-cyan.css"
SOURCES = [
    CSS_ROOT / "app.css",
    CSS_ROOT / "pages" / "home.css",
    CSS_ROOT / "pages" / "employee-directory.css",
    CSS_ROOT / "pages" / "movement-forms.css",
    CSS_ROOT / "pages" / "management.css",
    CSS_ROOT / "pages" / "workspace-pages.css",
]
REPORT = ROOT / "docs" / "design" / "CSS_CROSS_STYLESHEET_SHADOWS_v68.44.6.json"


def safe_rules(path: Path):
    text = path.read_text(encoding="utf-8")
    rules = collect_rules(text, path)
    return text, [r for r in rules if r.get("eligible")]


def canonical_index(path: Path):
    _, rules = safe_rules(path)
    index = defaultdict(list)
    for ri, rule in enumerate(rules):
        for seg in rule["segments"]:
            if seg["duplicate_in_rule"]:
                continue
            sig = seg["sig"]
            key = (rule["selector"], tuple(rule["ctx"]), sig["name"])
            index[key].append({"rule_index": ri, "important": sig["important"], "line": rule["line"], "value": sig["value"]})
    return index


def plan(path: Path, winners):
    text, rules = safe_rules(path)
    edits=[]
    removed=[]
    for ri, rule in enumerate(rules):
        to_remove=[]
        for seg in rule["segments"]:
            if seg["duplicate_in_rule"]:
                continue
            sig=seg["sig"]
            key=(rule["selector"], tuple(rule["ctx"]), sig["name"])
            candidates=[w for w in winners.get(key,[]) if (not sig["important"] or w["important"])]
            if not candidates:
                continue
            to_remove.append(seg)
            removed.append({
                "file": path.relative_to(ROOT).as_posix(),
                "line": rule["line"],
                "selector": rule["selector"],
                "property": sig["raw_name"],
                "value": sig["value"],
                "canonical_file": CANONICAL.relative_to(ROOT).as_posix(),
                "canonical_line": candidates[-1]["line"],
                "canonical_value": candidates[-1]["value"],
                "context": list(rule["ctx"]),
            })
        if not to_remove:
            continue
        count=len([n for n in rule["nodes"] if n.type=='declaration'])
        if len(to_remove) == count and not rule.get("has_comments"):
            edits.append((rule["start"], rule["close"]+1, ""))
        else:
            edits.extend((s["start"], s["end"], "") for s in to_remove)
    result=text
    for a,b,repl in sorted(edits, reverse=True):
        result=result[:a]+repl+result[b:]
    return result, removed


def main():
    apply="--apply" in sys.argv
    winners=canonical_index(CANONICAL)
    total=[]; changed=[]
    for path in SOURCES:
        output, notes=plan(path,winners)
        if notes:
            total.extend(notes)
            changed.append((path,output,len(notes)))
    counts=Counter(n["file"] for n in total)
    print(f"{'Applied' if apply else 'Dry run'} cross-stylesheet shadowed declarations: {len(total)}")
    for f,n in sorted(counts.items()): print(f"  {f}: {n}")
    # Preserve the applied audit when the cleanup is rerun on an already-clean tree.
    # Use --json to explicitly overwrite the report with the current dry-run state.
    write_report = bool(total) or "--json" in sys.argv
    if write_report:
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps({"count":len(total),"by_file":dict(counts),"canonical_file":CANONICAL.relative_to(ROOT).as_posix(),"removed":total},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(f"Report: {REPORT.relative_to(ROOT)}")
    if apply:
        for path,output,_ in changed: path.write_text(output,encoding="utf-8")
    if not total: print("CSS_CROSS_STYLESHEET_CLEANUP=NO_CANDIDATES")
    return 0

if __name__ == '__main__': raise SystemExit(main())
