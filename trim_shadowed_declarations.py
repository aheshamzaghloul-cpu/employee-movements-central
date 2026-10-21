"""Remove only declarations guaranteed to be overridden by a later identical selector.

Safety constraints:
- Restrict each edit to a single selector (never alter a grouped rule's other selectors).
- Match exact stylesheet nesting/media/supports context.
- Remove only a declaration when a later declaration for the same property and selector
  has equal or higher importance. Responsive/print variants are not crossed.
- Duplicate properties inside a rule are protected on both the source and target sides;
  they may be browser fallbacks/progressive enhancement, not obsolete overrides.
- CSS custom property names remain case-sensitive.
- Leave nested CSS, parse-error rules and keyframes untouched.
"""
from pathlib import Path
import collections
import tinycss2
from dedupe_css_selectors import find_open_brace, find_close_brace, offset_for, split_selectors, norm

ROOT = Path(__file__).resolve().parent / "employee_movements/static/css"

def prop_name(name):
    # CSS custom property names are case-sensitive; other property names are not.
    return name if name.startswith("--") else name.lower()

def declarations(nodes):
    return [(i, n) for i,n in enumerate(nodes) if n.type == 'declaration']

def records_for(text, path):
    result=[]
    top=tinycss2.parse_stylesheet(text,skip_whitespace=False,skip_comments=False)
    def walk(rules, contexts=()):
        for r in rules:
            if r.type == 'qualified-rule':
                start=offset_for(text,r.source_line,r.source_column)
                try:
                    op=find_open_brace(text,start); cl=find_close_brace(text,op)
                except Exception:
                    continue
                sel=split_selectors(text[start:op].strip())
                if len(sel)!=1: continue
                # Nested rules / parse errors aren't simplified by this pass.
                nodes=tinycss2.parse_declaration_list(r.content,skip_whitespace=False,skip_comments=False)
                if any(n.type in ('error','qualified-rule','at-rule') for n in nodes): continue
                property_counts=collections.Counter(
                    prop_name(n.name) for n in nodes if n.type=='declaration'
                )
                duplicate_properties={name for name,count in property_counts.items() if count>1}
                result.append({'start':start,'open':op,'close':cl,'selector':sel[0],'ctx':contexts,'line':r.source_line,'nodes':nodes,'path':path,'duplicate_properties':duplicate_properties})
            elif r.type == 'at-rule' and r.content is not None:
                name='@'+r.at_keyword.lower()+' '+norm(tinycss2.serialize(r.prelude))
                if r.at_keyword.lower() in ('keyframes','-webkit-keyframes'):
                    continue
                walk(tinycss2.parse_rule_list(r.content,skip_whitespace=False,skip_comments=False),contexts+(name,))
    walk(top)
    return result

def plan(text, path):
    recs=records_for(text,path)
    # Index every declaration by selector + exact media/supports/layer context + property.
    future=collections.defaultdict(list)
    flat=[]
    for ri,r in enumerate(recs):
        for ni,n in declarations(r['nodes']):
            name=prop_name(n.name)
            # Do not use duplicated declarations as shadowing evidence: they may
            # be progressive enhancement or browser-fallback declarations.
            if name in r.get('duplicate_properties', set()):
                continue
            key=(r['selector'],r['ctx'],name)
            flat.append((ri,ni,key,bool(n.important),r,n))
            future[key].append((ri,ni,bool(n.important)))
    remove=collections.defaultdict(set)
    for ri,ni,key,important,r,n in flat:
        for rj,nj,imp2 in future[key]:
            if (rj, nj) <= (ri,ni): continue
            # Important declarations cannot be defeated by later normal declarations.
            if (not important) or imp2:
                remove[ri].add(ni)
                break
    edits=[];notes=[];num=0
    for ri,indices in remove.items():
        r=recs[ri]
        kept=[node for idx,node in enumerate(r['nodes']) if idx not in indices]
        if not any(n.type=='declaration' for n in kept):
            # Preserve an otherwise empty rule if it contains comments; this is safer for hand annotations.
            if not any(n.type=='comment' for n in kept):
                replacement=''
            else:
                replacement=tinycss2.serialize(kept)
        else:
            replacement=tinycss2.serialize(kept)
        edits.append((r['open']+1,r['close'],replacement))
        num += sum(1 for idx in indices if r['nodes'][idx].type=='declaration')
        removedprops=[r['nodes'][i].name for i in sorted(indices) if r['nodes'][i].type=='declaration']
        notes.append(f"{path.relative_to(ROOT)}:{r['line']}: removed shadowed declaration(s) from {r['selector']}: {', '.join(removedprops)}")
    return edits,num,notes

def main(dry=False):
    total=0; files=0; allnotes=[]; perfile=[]
    for p in sorted(ROOT.rglob('*.css')):
        text=p.read_text(encoding='utf-8')
        edits,n,notes=plan(text,p)
        if not edits: continue
        files+=1; total+=n; allnotes.extend(notes); perfile.append((p.relative_to(ROOT),n))
        if not dry:
            for a,b,repl in sorted(edits,reverse=True): text=text[:a]+repl+text[b:]
            p.write_text(text,encoding='utf-8')
    print(('Dry run' if dry else 'Applied')+f': {total} shadowed declarations removed across {files} CSS files')
    for name,n in perfile:print(f'  {name}: {n}')
    print('\n'.join(allnotes[:200]))
    if len(allnotes)>200:print(f'... plus {len(allnotes)-200} more entries')
if __name__=='__main__':
    import sys;main('--dry' in sys.argv)
