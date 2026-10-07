import sys

sys.path.insert(0, 'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P='LoRaCanary-底板-v0.6'
e=EasyEDAPCB(P)

print('reload'); e.reload()
print('rip 3V3'); e._ok(e._run('pcb','rip-up','--net','3V3')); e.reload()
print('reauthorize'); e.reauthorize()
print('route-short --route-power')
e._ok(e._run('pcb','route-short','--route-power','--force-unsafe','reroute 3V3 tree'))
e.reload()

# ---------------- reads (fresh) ----------------
thre = e.tracks('3V3')
scl_existing={(round(t['startX'],1),round(t['startY'],1),round(t['endX'],1),round(t['endY'],1)) for t in e.tracks('SCL')}

def T(a,b,c,d,w=10,l=15):
    e.create_track(a,b,c,d,'3V3',w,l)

PIN6=(2705.5,2622.2074); PIN8=(2705.5,2673.398)

cands=[]
for t in thre:
    cands += [(t['startX'],t['startY']),(t['endX'],t['endY'])]
for v in e.vias('3V3'):
    cands.append((v['x'],v['y']))
anchor=None
for p in cands:
    if abs(p[1]-2640)<200 and abs(p[0]-2705)>40:
        anchor=p; break
if anchor is None:
    anchor=max(cands,key=lambda p:-abs(p[0]-2705)-abs(p[1]-2640))
anchor=(round(anchor[0],2),round(anchor[1],2))
print('anchor=',anchor)

# ---------------- batched creates ----------------
e.create_via(*PIN6,'3V3')
e.create_via(*PIN8,'3V3')
T(PIN6[0],PIN6[1],PIN8[0],PIN8[1])

WESTX=2640.0
T(PIN6[0],PIN6[1],WESTX,PIN6[1])
T(WESTX,PIN6[1],WESTX,anchor[1])
T(WESTX,anchor[1],anchor[0],anchor[1])

need=[
 (1681.3,2619.5,1685.6,2619.5),
 (1685.6,2619.5,1705.6,2639.5),
 (1705.6,2639.5,1705.6,2789.5),
 (1705.6,2789.5,1695.6,2799.5),
 (1695.6,2799.5,1605.6,2799.5),
 (1605.6,2799.5,1555.6,2749.5),
 (1555.6,2749.5,955.6,2749.5),
 (955.6,2749.5,875.6,2669.5),
 (875.6,2669.5,586.6,2669.5),
 (586.6,2669.5,576.2,2679.9),
]
for a,b,c,d in need:
    if (a,b,c,d) not in scl_existing and (c,d,a,b) not in scl_existing:
        e.create_track(a,b,c,d,'SCL',10,1)
        print('SCL add',(a,b))

print('pour-rebuild'); e._ok(e._run('pcb','pour-rebuild'))
e.reload()
f=e.check(); print('heur errors:',[(x['type'],x.get('at')) for x in f if x.get('level')=='ERROR'])
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
print('NoConn:',sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'}))
