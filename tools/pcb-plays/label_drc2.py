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
            leaves.append(d)
for g in resp['violations']: walk(g)

# ---------- resolver ----------
tracks={t['primitiveId']:t for t in e.tracks()}
def track_by(oid):
    if not oid: return None
    t=tracks.get(oid)
    if t: return t
    for L in (16,12):
        cand=[tt for tid,tt in tracks.items() if tid.startswith(oid[:L])]
        if cand: return cand[0]
    return None
dmp=e.dump()
pad_by_comp={}
for c in dmp['components']:
    for p in c['pads']:
        pad_by_comp[(c['designator'],p['padNumber'])]=(c,p)
def pad_by_suffix(suf):
    if '_' not in suf: return None
    try:
        des,num=suf.split('):')[1].strip().split('_')
        hit=pad_by_comp.get((des,num))
        if hit:
            c,p=hit
            return (p['x'],p['y'],f'{des}.{num} pad')
    except Exception: pass
    return None
def obj_resolve(oid,typ,suf):
    if typ=='Track':
        t=track_by(oid)
        if t: return ((t['startX']+t['endX'])/2,(t['startY']+t['endY'])/2,f'track L{t["layer"]}')
    if typ=='Via':
        for v in e.vias():
            if v['primitiveId']==oid or v['primitiveId'].startswith(oid[:12]):
                return (v['x'],v['y'],'via')
    return pad_by_suffix(suf)

def resolve(l):
    for oid,typ,suf in ((l.get('obj1',''),l.get('obj1Type',''),l.get('obj1Suffix','')),
                        (l.get('obj2',''),l.get('obj2Type',''),l.get('obj2Suffix',''))):
        r=obj_resolve(oid,typ,suf)
        if r: return r
    pos=l.get('position')
    if pos:
        # plugin DRC position unit: x10 => mil
        return (pos['x']*10,pos['y']*10,'drc-raw*10')
    return None

rows=[]; labels=[]
for l in leaves:
    et=l.get('errorType'); gi=l.get('globalIndex','')
    num=gi.replace('err','') if gi else '?'
    if et=='Safe Spacing': code=f'S{num}'
    elif et=='No Connection': code=f'N{num}'
    else: continue
    r=resolve(l)
    if r is None:
        rows.append((code,et,'?','?',l.get('obj1Suffix',''),l.get('obj2Suffix',''),l.get('minDistance',''),'NOT RESOLVED'))
        continue
    x,y,how=r
    rows.append((code,et,round(x,1),round(y,1),l.get('obj1Suffix',''),l.get('obj2Suffix',''),l.get('minDistance',''),how))
    labels.append((code,x,y,et))
print('resolved:',len(labels),'unresolved:',sum(1 for r in rows if r[7]=='NOT RESOLVED'))
from collections import Counter

print('methods:',Counter(r[7] for r in rows))

# ---------- place ----------
e.reauthorize()
silk_ids=[]
for code,x,y,et in labels:
    try:
        r=e._run('pcb','silk-add','--text',code,'--x',str(round(x,1)),'--y',str(round(y,1)),
                 '--font-size','32','--line-width','6')
        pid=(r.get('result') or {}).get('primitiveId')
        silk_ids.append(pid)
    except Exception as ex:
        print('silk fail',code,str(ex)[:120])
print('placed:',len(silk_ids))

# ---------- save / legend ----------
json.dump({'ids':[i for i in silk_ids if i],'rows':rows}, open('drc_labels.json','w'), indent=1)
with open('docs/DRC-legend.md','w',encoding='utf-8') as f:
    f.write('# DRC 标签对照表\n\n板上丝印编号 ↔ DRC 错误明细。S=Safe Spacing（间距警示），N=No Connection（开路）。\n\n')
    f.write('| 编号 | 类型 | 位置(x,y) mil | 对象1 | 对象2 | 间距 | 定位方式 |\n|---|---|---|---|---|---|---|\n')
    for code,et,x,y,o1,o2,dist,how in rows:
        f.write(f'| {code} | {et} | {x},{y} | {o1} | {o2} | {dist} | {how} |\n')
print('legend -> docs/DRC-legend.md')
