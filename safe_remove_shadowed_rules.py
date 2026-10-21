"""Remove whole CSS rules that are fully shadowed by a later identical selector/context.

Conservative rules:
- exact normalized selector text and identical at-rule context only;
- every declaration must be overwritten by the same property in one later rule;
- later declaration must preserve !important precedence;
- blocks with comments, parse errors, duplicate declarations, or empty bodies are skipped;
- edits are limited to application stylesheet source files.
"""
from __future__ import annotations
from collections import defaultdict, Counter
from pathlib import Path
import sys
import tinycss2
from dedupe_css_selectors import collect, norm

ROOT = Path(__file__).resolve().parent / "employee_movements" / "static" / "css"


def declarations(text: str, rule: dict):
    body = text[rule["open"] + 1:rule["close"]]
    nodes = tinycss2.parse_declaration_list(body, skip_whitespace=True, skip_comments=False)
    out = []
    for node in nodes:
        if node.type == "whitespace":
            continue
        if node.type != "declaration":
            return None
        if any(x.type == "comment" for x in getattr(node, "value", [])):
            return None
        name = node.name if node.name.startswith('--') else node.name.lower()
        out.append((name, norm(tinycss2.serialize(node.value)), bool(node.important)))
    if not out:
        return None
    counts = Counter(name for name, _, _ in out)
    if any(n > 1 for n in counts.values()):
        # Preserve intentionally repeated declarations and browser fallbacks.
        return None
    return out


def candidate_rules(path: Path):
    text = path.read_text(encoding="utf-8")
    rules = collect(text)
    parsed = [declarations(text, rule) for rule in rules]
    by_key = defaultdict(list)
    for i, rule in enumerate(rules):
        ds = parsed[i]
        if ds is None:
            continue
        by_key[(norm(rule["selector_text"]), rule["ctx"])].append(i)

    candidates = []
    removed_indexes = set()
    for (selector, context), indexes in by_key.items():
        for pos, i in enumerate(indexes[:-1]):
            old = parsed[i]
            for j in indexes[pos + 1:]:
                newer = parsed[j]
                latest = {name: (value, important) for name, value, important in newer}
                # Same property in a later identical selector/context wins. An
                # earlier important declaration requires a later important one.
                if all(name in latest and (not important or latest[name][1])
                       for name, _, important in old):
                    candidates.append({
                        "start": rules[i]["start"], "end": rules[i]["close"] + 1,
                        "selector": selector, "context": context,
                        "line": rules[i]["line"], "shadowed_by_line": rules[j]["line"],
                        "properties": [name for name, _, _ in old],
                        "rule_index": i,
                    })
                    removed_indexes.add(i)
                    break
    # If multiple shadowed earlier copies exist, remove each candidate. Do not
    # double-include one physical rule even if the key is repeated.
    uniq = {}
    for c in candidates:
        uniq[c["rule_index"]] = c
    return text, list(uniq.values())


def main():
    apply = "--apply" in sys.argv
    total = 0
    report = []
    changed = []
    for path in sorted(ROOT.rglob("*.css")):
        text, items = candidate_rules(path)
        if not items:
            continue
        total += len(items)
        changed.append((path, len(items)))
        for item in items:
            report.append((str(path.relative_to(ROOT)), item["line"], item["shadowed_by_line"], item["selector"], ",".join(item["properties"])))
        if apply:
            for item in sorted(items, key=lambda x: x["start"], reverse=True):
                text = text[:item["start"]] + text[item["end"]:]
            path.write_text(text, encoding="utf-8")
    print(("Applied" if apply else "Dry run"), f"fully shadowed exact-selector rules: {total}")
    for path, count in changed:
        print(f"{path}: {count}")
    for row in report:
        print(f"{row[0]}:{row[1]} -> {row[2]} | {row[3]} | {row[4]}")

if __name__ == "__main__":
    main()
