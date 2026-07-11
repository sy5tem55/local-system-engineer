# bump gate: python3 bump_gate.py  (run from repo root)
import ast
COND = (ast.If, ast.For, ast.While)
src = open('tools/goethe.py').read()
cls = [n for n in ast.walk(ast.parse(src))
       if isinstance(n, ast.ClassDef) and n.name == 'Tools'][0]

def maxd(node, d=0):
    m = d
    for c in ast.iter_child_nodes(node):
        m = max(m, maxd(c, d + 1 if isinstance(c, COND) else d))
    return m

def bumps(fn):
    out = []
    def walk(node, in_cond):
        for c in ast.iter_child_nodes(node):
            if isinstance(c, COND) and not in_cond:
                if maxd(c, 1) >= 2:
                    out.append((c.lineno, c.end_lineno, maxd(c, 1)))
                walk(c, True)
            else:
                walk(c, in_cond or isinstance(c, COND))
    walk(fn, False)
    out.sort()
    merged = []
    for s in out:
        if merged and s[0] - merged[-1][1] <= 1:
            merged[-1] = (merged[-1][0], s[1], max(merged[-1][2], s[2]))
        else:
            merged.append(s)
    return merged

flagged = 0
for it in cls.body:
    if isinstance(it, (ast.FunctionDef, ast.AsyncFunctionDef)):
        b = bumps(it)
        if len(b) >= 2:
            flagged += 1
            spans = ' '.join(f'{a}-{e}@{d}' for a, e, d in b)
            print(f'{len(b):>2} bumps  {it.name:<28} {spans}')
print(f'--- {flagged} functions with >=2 bumps (detector approximates CodeScene; UI scan is authoritative)')
