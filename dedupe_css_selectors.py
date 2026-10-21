from pathlib import Path
import tinycss2
import re

ROOT = Path(__file__).resolve().parent / 'employee_movements/static/css'

def norm(s: str) -> str:
    return re.sub(r'\s+', ' ', s.strip())

def split_selectors(s: str) -> list[str]:
    out=[]; start=0; depth=0; quote=None; esc=False
    for i,ch in enumerate(s):
        if esc:
            esc=False; continue
        if ch=='\\':
            esc=True; continue
        if quote:
            if ch==quote: quote=None
            continue
        if ch in "'\"": quote=ch; continue
        if ch in '([': depth+=1
        elif ch in ')]': depth=max(0,depth-1)
        elif ch==',' and depth==0:
            out.append(norm(s[start:i])); start=i+1
    out.append(norm(s[start:]))
    return [x for x in out if x]

def offset_for(text: str, line: int, column: int) -> int:
    lines=text.splitlines(keepends=True)
    return sum(len(x) for x in lines[:line-1]) + column-1

def find_open_brace(text: str, start: int) -> int:
    quote=None; esc=False; comment=False; paren=0; bracket=0
    i=start
    while i<len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ''
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
        elif c=='{' and paren==0 and bracket==0: return i
        i+=1
    raise ValueError(f'Opening brace not found at {start}')

def find_close_brace(text: str, open_i: int) -> int:
    depth=0; quote=None; esc=False; comment=False; i=open_i
    while i<len(text):
        c=text[i]; n=text[i+1] if i+1<len(text) else ''
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
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return i
        i+=1
    raise ValueError(f'Closing brace not found at {open_i}')

def decl_signature(rule) -> tuple:
    vals=[]
    for d in tinycss2.parse_declaration_list(rule.content, skip_whitespace=True, skip_comments=True):
        if d.type=='declaration':
                name = d.name if d.name.startswith('--') else d.name.lower()
                vals.append((name, norm(tinycss2.serialize(d.value)), bool(d.important)))
    return tuple(vals)

def collect(text: str):
    records=[]
    def walk(rules, path, contexts=()):
        for r in rules:
            if r.type=='qualified-rule':
                start=offset_for(text,r.source_line,r.source_column)
                open_i=find_open_brace(text,start)
                close_i=find_close_brace(text,open_i)
                raw_sel=text[start:open_i].strip()
                selectors=split_selectors(raw_sel)
                records.append({'start':start,'open':open_i,'close':close_i,'selector_text':raw_sel,
                                'selectors':selectors,'ctx':contexts,'sig':decl_signature(r),
                                'line':r.source_line,'path':path})
            elif r.type=='at-rule' and r.content is not None:
                name='@'+r.at_keyword.lower()+' '+norm(tinycss2.serialize(r.prelude))
                walk(tinycss2.parse_rule_list(r.content,skip_whitespace=True,skip_comments=True),path,contexts+(name,))
    walk(tinycss2.parse_stylesheet(text,skip_whitespace=True,skip_comments=True),'')
    return records

def main(dry=False):
    total_removed=0; changed_files=[]; change_notes=[]
    for path in sorted(ROOT.rglob('*.css')):
        text=path.read_text(encoding='utf-8')
        recs=collect(text)
        # Mark earlier appearances of an identical selector/declaration in the same stylesheet context.
        last_index={}
        for ri,r in enumerate(recs):
            for sel in r['selectors']:
                last_index[(sel,r['ctx'],r['sig'])]=ri
        edits=[]; removed_in_file=0
        for ri,r in enumerate(recs):
            keep=[]; remove=[]
            for sel in r['selectors']:
                if last_index[(sel,r['ctx'],r['sig'])] > ri:
                    remove.append(sel)
                else:
                    keep.append(sel)
            if not remove: continue
            removed_in_file += len(remove)
            change_notes.append(f'{path.relative_to(ROOT)}:{r["line"]}: removed redundant selector(s) {", ".join(remove)} (same declarations and same media context remain later in this stylesheet)')
            if keep:
                edits.append((r['start'],r['open'],', '.join(keep)))
            else:
                edits.append((r['start'],r['close']+1,''))
        if edits:
            changed_files.append((path,removed_in_file))
            total_removed += removed_in_file
            if not dry:
                for start,end,repl in sorted(edits,reverse=True):
                    text=text[:start]+repl+text[end:]
                path.write_text(text,encoding='utf-8')
    print('Dry run' if dry else 'Applied', 'redundant selector removals:',total_removed)
    for path,n in changed_files: print(f'  {path.relative_to(ROOT)}: {n}')
    print('\n'.join(change_notes))
if __name__=='__main__':
    import sys; main('--dry' in sys.argv)
