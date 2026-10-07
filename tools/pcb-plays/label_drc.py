import json
import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')
e.reload()

# ---------- gather DRC leaves ----------
resp=e._run('pcb','drc','--timeout','180')['result']
leaves=[]
def walk(n):
    if isinstance(n,dict):
        if 'list' in n:
            for s in n['list']: walk(s)
        elif 'explanation' in n:
            d=dict(n['explanation'].get('errData',{}))
            d['_str']=n['explanation'].get('str','')
            leaves.append(d)
for g in resp['violations']: walk(g)
print('DRC leaves:',len(leaves))

# ---------- id resolver ----------
tracks={t['primitiveId']:t for t in e.tracks()}
track_by_prefix={}
for tid,t in tracks.items():
    for L in (16,12,8):
        track_by_prefix.setdefault(tid[:L],[]).append(t)

dmp=e.dump()
pad_by_comp={}
for c in dmp['components']:
    for p in c['pads']:
        pad_by_comp[(c['designator'],p['padNumber'])]=(c,p)

def resolve(l):
    """return (x,y,desc) in board mil coords"""
    oid=l.get('obj1',''); typ=l.get('obj1Type',''); suf=l.get('obj1Suffix','')
    if typ=='Track':
        t=tracks.get(oid)
        if t is None:
            cand=track_by_prefix.get(oid) or track_by_prefix.get(oid[-12:])
            t=cand[0] if cand else None
        if t:
            return ((t['startX']+t['endX'])/2,(t['startY']+t['endY'])/2,f"track L{t['layer']}")
    if typ=='Via':
        for v in e.vias():
            if v['primitiveId']==oid or v['primitiveId'].startswith(oid[:12]):
                return (v['x'],v['y'],'via')
    # pad via suffix like (GND): U6_1 / B1_2 / U1_1
    if '_' in suf:
        try:
            des,num=suf.split('):')[1].strip().split('_')
            hit=pad_by_comp.get((des,num))
            if hit:
                c,p=hit
                return (p['x'],p['y'],f'{des}.{num} pad')
        except Exception:
            pass
    pos=l.get('position')
    if pos:
        return (pos['x'],pos['y'],'drc-position(raw)')
    return None

rows=[]
labels=[]
for l in leaves:
    et=l.get('errorType')
    gi=l.get('globalIndex','')            # errN
    num=gi.replace('err','') if gi else '?'
    if et=='Safe Spacing':
        code=f'S{num}'
    elif et=='No Connection':
        code=f'N{num}'
    else:
        continue                           # netlist note: no position
    r=resolve(l)
    if r is None:
        rows.append((code,et,'?','?',l.get('obj1Suffix',''),l.get('obj2Suffix',''),l.get('minDistance',''),'NOT RESOLVED'))
        continue
    x,y,how=r
    rows.append((code,et,round(x,1),round(y,1),l.get('obj1Suffix',''),l.get('obj2Suffix',''),l.get('minDistance',''),how))
    labels.append((code,x,y,et))

print('resolved:',len(labels),'unresolved:',sum(1 for r in rows if r[7]=='NOT RESOLVED'))

# ---------- place silk labels ----------
e.reauthorize()
silk_ids=[]
for code,x,y,et in labels:
    txt=code
    try:
        r=e._run('pcb','silk-add','--text',txt,'--x',str(round(x,1)),'--y',str(round(y,1)),
                 '--font-size','32','--line-width','6')
        pid=r.get('result',{}).get('primitiveId') or r.get('result',{}).get('id')
        silk_ids.append(pid)
    except Exception as ex:
        print('silk fail',code,str(ex)[:120])
print('silk labels placed:',len(silk_ids))
json.dump({'ids':silk_ids,'rows':rows}, open('drc_labels.json','w'), indent=1)

# ---------- legend file ----------
with open('docs/DRC-legend.md','w',encoding='utf-8') as f:
    f.write('# DRC 标签对照表\n\n板上丝印编号 ↔ DRC 错误明细（生成时间见 git）。\n\n')
    f.write('| 编号 | 类型 | 位置 (x,y) mil | 对象1 | 对象2 | 间距(mil) | 备注 |\n|---|---|---|---|---|---|---|\n')
    for code,et,x,y,o1,o2,dist,how in rows:
        f.write(f'| {code} | {et} | {x},{y} | {o1} | {o2} | {dist} | {how} |\n')
print('legend written to docs/DRC-legend.md')
