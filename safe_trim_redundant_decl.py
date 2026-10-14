"""Safely remove a declaration only when a later, identical selector/context repeats the same value.

Guardrails:
- never remove declarations from grouped selectors;
- never touch a property duplicated within the same rule (preserves CSS fallbacks);
- require an identical selector, at-rule context, property and normalized value;
- respect !important priority;
- preserve comments and skip declaration segments containing comments or parse errors.
"""
from pathlib import Path
from collections import Counter, defaultdict
import re, sys, tinycss2
from dedupe_css_selectors import collect
ROOT=Path(__file__).resolve().parent/'employee_movements/static/css'

def normalized(v): return re.sub(r'\s+',' ',tinycss2.serialize(v).strip())

def split_segments(body):
    segs=[]; start=0; quote=None; esc=False; comment=False; paren=0; bracket=0; brace=0; i=0
    while i<len(body):
        c=body[i]; n=body[i+1] if i+1<len(body) else ''
        if comment:
            if c=='*' and n=='/': comment=False; i+=2; continue
            i+=1; continue
        if quote:
            if esc: esc=False
            elif c=='\\': esc=True
            elif c==quote: quote=None
            i+=1; continue
        if c=='/' and n=='*': comment=True; i+=2; continue
        if c in "'\"": quote=c; i+=1; continue
        if c=='(': paren+=1
        elif c==')': paren=max(0,paren-1)
        elif c=='[': bracket+=1
        elif c==']': bracket=max(0,bracket-1)
        elif c=='{': brace+=1
        elif c=='}': brace=max(0,brace-1)
        elif c==';' and paren==0 and bracket==0 and brace==0:
            segs.append((start,i+1,body[start:i+1])); start=i+1
        i+=1
    if start<len(body): segs.append((start,len(body),body[start:]))
    return segs

def parse_one_declaration(segment):
    nodes=tinycss2.parse_declaration_list(segment,skip_whitespace=True,skip_comments=False)
    bad=[x for x in nodes if x.type not in ('whitespace','comment')]
    if len(bad)!=1 or bad[0].type!='declaration': return None
    if any(x.type=='comment' for x in nodes): return None
    d=bad[0]
    name=d.name.lower()
    if name.startswith('*') or name.startswith('_'): return None
    return name, normalized(d.value), bool(d.important)

def collect_decls(text, records):
    byrule=[]
    for ri,r in enumerate(records):
        # Only single selectors; grouped rules are left unchanged.
        if len(r['selectors'])!=1: byrule.append([]); continue
        body=text[r['open']+1:r['close']]
        segs=split_segments(body)
        parsed=[]
        for start,end,chunk in segs:
            d=parse_one_declaration(chunk)
            if d: parsed.append({'start':r['open']+1+start,'end':r['open']+1+end,'sig':d,'chunk':chunk})
        local_counts=Counter(x['sig'][0] for x in parsed)
        # Any repeated property in one rule is protected, including browser fallback declarations.
        for x in parsed: x['protected']=local_counts[x['sig'][0]]>1
        byrule.append(parsed)
    return byrule

def plan_file(path, dry=True):
    text=path.read_text(encoding='utf-8'); records=collect(text); decls=collect_decls(text,records)
    later=defaultdict(list)
    for ri,(r,ds) in enumerate(zip(records,decls)):
        if len(r['selectors'])!=1: continue
        keybase=(r['selectors'][0],r['ctx'])
        for x in ds:
            if not x['protected']:
                name,val,imp=x['sig']; later[(keybase,name,val)].append((ri,imp))
    edits=[]; notes=[]
    for ri,(r,ds) in enumerate(zip(records,decls)):
        if len(r['selectors'])!=1: continue
        sel=r['selectors'][0]; ctx=r['ctx']
        for x in ds:
            if x['protected']: continue
            name,val,imp=x['sig']
            duplicates=[(j,later_imp) for j,later_imp in later.get(((sel,ctx),name,val),[]) if j>ri and (later_imp or not imp)]
            if duplicates:
                edits.append((x['start'],x['end'],''))
                notes.append((path.name,r['line'],sel,name,val,ri,max(j for j,_ in duplicates)))
    if not dry and edits:
        for start,end,repl in sorted(edits,reverse=True): text=text[:start]+repl+text[end:]
        path.write_text(text,encoding='utf-8')
    return notes

def main():
    dry='--apply' not in sys.argv
    total=0
    for p in sorted(ROOT.rglob('*.css')):
        notes=plan_file(p,dry=dry)
        if notes:
            total+=len(notes); print(f'{p.relative_to(ROOT)}: {len(notes)}')
            for note in notes[:4]: print(' ',note[1],note[2],note[3],note[4])
    print(('Dry run' if dry else 'Applied')+f' safe shadowed same-value declarations: {total}')
if __name__=='__main__': main()
