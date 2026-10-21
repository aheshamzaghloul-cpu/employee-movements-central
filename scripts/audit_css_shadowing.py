"""Audit safely removable CSS rules that are fully shadowed later.

A candidate must have the same normalized selector and the same at-rule
context, and every declaration must be overridden by the same property in a
later rule. CSS blocks with comments, parse errors, duplicate properties or
!important precedence conflicts are intentionally skipped.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import re

import tinycss2

ROOT = Path(__file__).resolve().parents[1]
CSS_ROOT = ROOT / "employee_movements" / "static" / "css"


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _offset_for(text: str, line: int, column: int) -> int:
    lines = text.splitlines(keepends=True)
    return sum(len(part) for part in lines[: line - 1]) + column - 1


def _find_open_brace(text: str, start: int) -> int:
    quote = None
    escaped = False
    comment = False
    paren = bracket = 0
    for i in range(start, len(text)):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if comment:
            if char == "*" and nxt == "/":
                comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char == "/" and nxt == "*":
            comment = True
            continue
        if char in "'\"":
            quote = char
        elif char == "(":
            paren += 1
        elif char == ")":
            paren = max(0, paren - 1)
        elif char == "[":
            bracket += 1
        elif char == "]":
            bracket = max(0, bracket - 1)
        elif char == "{" and paren == 0 and bracket == 0:
            return i
    raise ValueError(f"Opening brace not found at offset {start}")


def _find_close_brace(text: str, open_index: int) -> int:
    depth = 0
    quote = None
    escaped = False
    comment = False
    i = open_index
    while i < len(text):
        char = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if comment:
            if char == "*" and nxt == "/":
                comment = False
                i += 2
                continue
            i += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            i += 1
            continue
        if char == "/" and nxt == "*":
            comment = True
            i += 2
            continue
        if char in "'\"":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError(f"Closing brace not found at offset {open_index}")


def _collect_rules(text: str) -> list[dict]:
    records = []

    def walk(nodes, context=()):
        for node in nodes:
            if node.type == "qualified-rule":
                start = _offset_for(text, node.source_line, node.source_column)
                open_index = _find_open_brace(text, start)
                close_index = _find_close_brace(text, open_index)
                selector = _normalise(text[start:open_index])
                records.append({
                    "selector": selector,
                    "context": context,
                    "start": start,
                    "open": open_index,
                    "close": close_index,
                    "line": node.source_line,
                })
            elif node.type == "at-rule" and node.content is not None:
                name = "@" + node.at_keyword.lower() + " " + _normalise(tinycss2.serialize(node.prelude))
                nested = tinycss2.parse_rule_list(
                    node.content, skip_whitespace=True, skip_comments=False
                )
                walk(nested, context + (name,))

    nodes = tinycss2.parse_stylesheet(text, skip_whitespace=True, skip_comments=False)
    walk(nodes)
    return records


def _declarations(text: str, rule: dict):
    body = text[rule["open"] + 1:rule["close"]]
    nodes = tinycss2.parse_declaration_list(body, skip_whitespace=True, skip_comments=False)
    output = []
    for node in nodes:
        if node.type == "whitespace":
            continue
        if node.type != "declaration":
            return None
        if any(token.type == "comment" for token in getattr(node, "value", [])):
            return None
        name = node.name if node.name.startswith("--") else node.name.lower()
        output.append((name, _normalise(tinycss2.serialize(node.value)), bool(node.important)))
    if not output:
        return None
    counts = Counter(name for name, _, _ in output)
    if any(count > 1 for count in counts.values()):
        return None
    return output


def find_fully_shadowed_rules(css_path: Path) -> list[dict]:
    """Return conservative candidates; does not modify the stylesheet."""
    text = css_path.read_text(encoding="utf-8")
    rules = _collect_rules(text)
    parsed = [_declarations(text, rule) for rule in rules]
    groups = defaultdict(list)
    for index, rule in enumerate(rules):
        if parsed[index] is not None:
            groups[(rule["selector"], rule["context"])].append(index)

    found = []
    for (selector, context), indexes in groups.items():
        for position, index in enumerate(indexes[:-1]):
            previous = parsed[index]
            for later_index in indexes[position + 1:]:
                later = {name: (value, important) for name, value, important in parsed[later_index]}
                if all(name in later and (not important or later[name][1])
                       for name, _, important in previous):
                    found.append({
                        "path": str(css_path.relative_to(ROOT)),
                        "line": rules[index]["line"],
                        "shadowed_by_line": rules[later_index]["line"],
                        "selector": selector,
                        "context": context,
                        "properties": [name for name, _, _ in previous],
                    })
                    break
    return found


def audit_tree() -> list[dict]:
    results = []
    for css_path in sorted(CSS_ROOT.rglob("*.css")):
        results.extend(find_fully_shadowed_rules(css_path))
    return results


def main() -> int:
    results = audit_tree()
    if not results:
        print("CSS_SHADOWING_AUDIT=OK: no fully-shadowed exact-selector rules found")
        return 0
    print(f"CSS_SHADOWING_AUDIT=NEEDS_REVIEW: {len(results)} candidate rule(s)")
    for item in results:
        print(f"{item['path']}:{item['line']} -> {item['shadowed_by_line']} | {item['selector']} | {','.join(item['properties'])}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
