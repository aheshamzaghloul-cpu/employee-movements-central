"""Conservatively remove CSS declarations shadowed by later exact-selector rules.

This pass is intentionally stricter than generic duplicate-property removal:
- grouped selectors, nested rules, parse errors, and commented declaration blocks are skipped;
- duplicate properties in the same rule (including browser fallbacks) are protected;
- selector text and full at-rule context must match exactly after whitespace normalization;
- only later declarations with equal/higher !important priority can shadow an earlier one;
- custom property names remain case-sensitive;
- any remaining selector/context differences are left untouched for visual review.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re
import sys
import json
import tinycss2

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from trim_shadowed_declarations import records_for
from safe_trim_redundant_decl import split_segments
CSS_ROOT = ROOT / "employee_movements" / "static" / "css"
TARGET_FILES = {"app.css", "design-system-cyan.css"}


def property_key(name: str) -> str:
    # Custom property names are case-sensitive per CSS syntax.
    return name if name.startswith("--") else name.lower()


def parse_declaration_segment(segment: str):
    if not segment.strip():
        return "whitespace"
    nodes = tinycss2.parse_declaration_list(segment, skip_whitespace=True, skip_comments=False)
    meaningful = [node for node in nodes if node.type != "whitespace"]
    if len(meaningful) != 1 or meaningful[0].type != "declaration":
        return None
    node = meaningful[0]
    if any(tok.type == "comment" for tok in getattr(node, "value", [])):
        return None
    name = node.name
    # Keep legacy property hacks and underscore/star hacks untouched.
    if name.startswith(("*", "_")):
        return None
    value = re.sub(r"\s+", " ", tinycss2.serialize(node.value).strip())
    return {"name": property_key(name), "raw_name": name, "value": value, "important": bool(node.important)}


def collect_rules(text: str, path: Path):
    records = records_for(text, path)
    result = []
    for rule in records:
        # Only exact single-selector rules are safe for this transform.
        if len(rule.get("selector", "").split(",")) > 1:
            rule["eligible"] = False
            result.append(rule)
            continue
        body = text[rule["open"] + 1:rule["close"]]
        segments = split_segments(body)
        parsed_segments = []
        has_comments = False
        valid = True
        for seg_index, (start, end, chunk) in enumerate(segments):
            parsed = parse_declaration_segment(chunk)
            if parsed == "whitespace":
                continue
            if parsed is None:
                valid = False
                # Comment-only blocks and odd declarations are deliberately retained.
                has_comments = True
                continue
            parsed_segments.append({
                "segment_index": seg_index,
                "start": rule["open"] + 1 + start,
                "end": rule["open"] + 1 + end,
                "sig": parsed,
                "chunk": chunk,
            })
        declaration_nodes = [node for node in rule["nodes"] if node.type == "declaration"]
        # If we could not account for every declaration, protect the complete block.
        if len(parsed_segments) != len(declaration_nodes):
            valid = False
        # Any in-rule comments or parse oddities make offsets/semantics harder to prove.
        if any(node.type == "comment" for node in rule["nodes"]):
            valid = False
            has_comments = True
        counts = Counter(item["sig"]["name"] for item in parsed_segments)
        for item in parsed_segments:
            item["duplicate_in_rule"] = counts[item["sig"]["name"]] > 1
        rule["segments"] = parsed_segments
        rule["eligible"] = valid and bool(parsed_segments)
        rule["has_comments"] = has_comments
        rule["declaration_count"] = len(declaration_nodes)
        result.append(rule)
    return result


def plan_content(text: str, path: Path):
    """Return cleaned CSS and an audit list without writing to disk."""
    rules = collect_rules(text, path)
    future = defaultdict(list)

    # Index only clean later declarations. If a property is duplicated in one
    # rule, neither instance is a safe destination because it might be a fallback.
    for rule_index, rule in enumerate(rules):
        if not rule.get("eligible"):
            continue
        for segment in rule["segments"]:
            if segment["duplicate_in_rule"]:
                continue
            sig = segment["sig"]
            key = (rule["selector"], rule["ctx"], sig["name"])
            future[key].append((rule_index, sig["important"], segment))

    removals = defaultdict(list)
    notes = []
    for rule_index, rule in enumerate(rules):
        if not rule.get("eligible"):
            continue
        for segment in rule["segments"]:
            if segment["duplicate_in_rule"]:
                continue
            sig = segment["sig"]
            key = (rule["selector"], rule["ctx"], sig["name"])
            winners = [
                (later_index, later_important, later_segment)
                for later_index, later_important, later_segment in future[key]
                if later_index > rule_index and (not sig["important"] or later_important)
            ]
            if winners:
                removals[rule_index].append(segment)
                notes.append({
                    "file": path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else path.name,
                    "line": rule["line"],
                    "selector": rule["selector"],
                    "property": sig["raw_name"],
                    "value": sig["value"],
                    "shadowed_by_line": rules[winners[-1][0]]["line"],
                    "context": list(rule["ctx"]),
                })

    edits = []
    for rule_index, segments in removals.items():
        rule = rules[rule_index]
        if len(segments) == rule["declaration_count"] and not rule.get("has_comments"):
            # It is safe to remove an entire declaration-only rule when every
            # declaration is proven shadowed. Normally the full-rule pass caught
            # these already; keep this guard for future runs.
            edits.append((rule["start"], rule["close"] + 1, ""))
        else:
            edits.extend((segment["start"], segment["end"], "") for segment in segments)

    result = text
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result, notes


def plan_file(path: Path):
    return plan_content(path.read_text(encoding="utf-8"), path)


def audit_all():
    all_notes = []
    plans = []
    for path in sorted(CSS_ROOT.rglob("*.css")):
        if path.name not in TARGET_FILES:
            continue
        result, notes = plan_file(path)
        all_notes.extend(notes)
        if notes:
            plans.append((path, result, len(notes)))
    return plans, all_notes


def main():
    apply = "--apply" in sys.argv
    plans, notes = audit_all()
    counts = Counter(note["file"] for note in notes)
    print(("Applied" if apply else "Dry run") + f" conservative shadowed declarations: {len(notes)}")
    for filename, count in sorted(counts.items()):
        print(f"  {filename}: {count}")
    if "--json" in sys.argv:
        output = ROOT / "docs" / "design" / "CSS_SHADOWED_DECLARATIONS_v68.44.5.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"count": len(notes), "by_file": dict(counts), "removed": notes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Report: {output.relative_to(ROOT)}")
    if apply:
        for path, result, _ in plans:
            path.write_text(result, encoding="utf-8")
    if not notes:
        print("CSS_SHADOWED_DECLARATION_CLEANUP=NO_CANDIDATES")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
