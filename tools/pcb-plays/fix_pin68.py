import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P='LoRaCanary-底板-v0.6'; NET='3V3'
e=EasyEDAPCB(P)

# ---- step 1: nudge the buried SCL run out of the pin column ----
print('reload'); e.reload()
target=None
for t in e.tracks('SCL'):
    if t['layer']==2 and abs(t['startY']-2619.5)<0.6 and abs(t['endY']-2619.5)<0.6 \
       and abs(t['startX']-1681.3)<1.5 and abs(t['endX']-2774.5)<1.5:
        target=t
assert target, 'SCL l2 run not found'
print('delete SCL l2 run', target['primitiveId'])
e._ok(e._run('pcb','track-delete','--ids',target['primitiveId']))
e.reload()

# re-authorize stage after delete
e.reauthorize()

# replacement polyline on L2 keeps both endpoints identical
segs=[(1681.3,2619.5,1700.0,2650.0),
      (1700.0,2650.0,2755.0,2650.0),
      (2755.0,2650.0,2774.5,2619.5)]
for a,b,c,d in segs:
    e.create_track(a,b,c,d,'SCL',10,2)
    print('SCL repl',(a,b,c,d))

# ---- step 2: verify & drop pad-centre vias for pins 6/8 ----
e.reload()
allc=e.tracks()
def pt_clear(px,py,rad,gap):
    for t in allc:
        if t.get('net')==NET: continue
        dx=t['endX']-t['startX']; dy=t['endY']-t['startY']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['startX'])*dx+(py-t['startY'])*dy)/L2)) if L2 else 0
        qx,qy=t['startX']+tt*dx,t['startY']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['lineWidth']/2<gap: return False,(t['net'],t['layer'])
    return True,None

P6=(2705.5,2622.2074); P8=(2705.5,2673.398); ANCH=(2774.5,2647.8)
ok6,w6=pt_clear(*P6,12,6); ok8,w8=pt_clear(*P8,12,6)
print('pin6 via ok:',ok6,w6,'| pin8 via ok:',ok8,w8)

ok_anchor=False
for v in e.vias(NET):
    if abs(v['x']-ANCH[0])<1 and abs(v['y']-ANCH[1])<1: ok_anchor=True
if not ok_anchor:
    raise SystemExit(f'anchor via missing at {ANCH}; abort')

if ok6 and ok8:
    e.create_via(*P6,NET)
    e.create_via(*P8,NET)
    e.create_track(P6[0],P6[1],P8[0],P8[1],NET,10,15)
    e.create_track(P8[0],P8[1],ANCH[0],ANCH[1],NET,10,15)
    print('created pin vias + l15 links')
else:
    raise SystemExit('vias still unsafe; nothing created')

print('pour-rebuild'); e._ok(e._run('pcb','pour-rebuild'))
e.reload()

f=e.check(); errs=[x for x in f if x.get('level')=='ERROR']
print('heur errors:',[(x['type'],round(x.get('at',{}).get('x',0)),round(x.get('at',{}).get('y',0))) for x in errs])

resp=e._run('pcb','drc','--timeout','180')['result']
leaves=[]
def walk(n):
    if isinstance(n,dict):
        if 'list' in n:
            for s in n['list']: walk(s)
        elif 'explanation' in n: leaves.append(n['explanation'].get('errData',{}))
for g in resp['violations']: walk(g)
from collections import Counter

cnt=Counter(l.get('errorType') for l in leaves)
print('DRC leaf:',len(leaves),dict(cnt))
ncs=sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'})
print('NoConn:', ncs if ncs else 'NONE ✔')
