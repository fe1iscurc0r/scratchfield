import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

P='LoRaCanary-底板-v0.6'
e=EasyEDAPCB(P)
NET='3V3'

print('reload'); e.reload()

# ---------- Step A: clean slate for 3V3 only ----------
print('rip-up 3V3'); e._ok(e._run('pcb','rip-up','--net',NET)); e.reload()
print('reauthorize'); e.reauthorize()
print('route-short --route-power (auto-route)')
e._ok(e._run('pcb','route-short','--route-power','--force-unsafe','auto-route 3V3 tree'))
e.reload()

# ---------- read fresh geometry ----------
tr = [t for t in e.tracks(NET)]
vs = e.vias(NET)
allc = e.tracks()   # everything
pads=[]
dmp=e.dump()
for c in dmp['components']:
    for p in c['pads']:
        if p.get('net')==NET:
            pads.append((c['designator'],p['padNumber'],p['x'],p['y']))
padmap={(d,n):(x,y) for d,n,x,y in pads}
print('auto-route produced:',len(tr),'tracks',len(vs),'vias')

# pad2 anchor point on copper
P2=(2804.55,2647.8)
def near_any(pt,tol=2.0):
    out=[]
    for t in tr:
        for end in ((t['startX'],t['startY']),(t['endX'],t['endY'])):
            if abs(end[0]-pt[0])<=tol and abs(end[1]-pt[1])<=tol:
                out.append((t['primitiveId'],end))
    for v in vs:
        if abs(v['x']-pt[0])<=tol and abs(v['y']-pt[1])<=tol:
            out.append((v['primitiveId'],(v['x'],v['y'])))
    return out
hits=near_any(P2,6)
print('copper near pad2:',hits[:4])
if not hits:
    raise SystemExit('route-short failed to even reach pad2; aborting surgical phase')

# lane y of that stub
lane_y=None
for eid,end in hits:
    t=[x for x in tr if x['primitiveId']==eid]
    if t: lane_y=end[1]; break
if lane_y is None:
    # via case: just use its y
    lane_y=P2[1]
print('lane_y=',round(lane_y,2))

# ---------- clearance helpers ----------
def pt_clear(px,py,rad,gap):
    for t in allc:
        if t.get('net')==NET: continue
        dx=t['endX']-t['startX']; dy=t['endY']-t['startY']
        L2=dx*dx+dy*dy
        tt=0 if L2==0 else max(0,min(1,((px-t['startX'])*dx+(py-t['startY'])*dy)/L2))
        qx,qy=t['startX']+tt*dx,t['startY']+tt*dy
        d=math.hypot(px-qx,py-qy)-rad-t['lineWidth']/2
        if d<gap: return False
    return True

def seg_clear(ax,ay,bx,by,w=10,gap=6,n=None):
    L=math.hypot(bx-ax,by-ay)
    n=n or max(2,int(L//3)+1)
    for i in range(n+1):
        px=ax+(bx-ax)*i/n; py=ay+(by-ay)*i/n
        if not pt_clear(px,py,w/2+0.01,gap): return False
    return True

# find VP west along same lane that is all-layer clear & segment to PA clear too
PAx=min(h[1][0] for h in hits) or P2[0]
PA=(min([h[1][0] for h in hits]), lane_y)
VP=None
x=PA[0]-8
while x>2620:
    cand=(x,lane_y)
    if pt_clear(*cand,rad=12,gap=6):
        VP=cand; break
    x-=2
assert VP, 'no clear via spot found on lane'
print('VP=',VP)

e.create_via(*VP,NET)

# wire along lane from VP to PA (may overlap existing stub partially - fine, same net merges)
if abs(VP[0]-PA[0])>1:
    assert seg_clear(VP[0],VP[1],PA[0],PA[1],w=10), 'lane wire blocked'
    e.create_track(VP[0],VP[1],PA[0],PA[1],NET,10,1)

# ---------- feed branch J & weave to pins 6/8 entirely on TOP ----------
J=(2732.6008,2605.0538)
diag=[(2715.4473,2622.2074)]
weave=[
  (2715.4473,2622.2074),(2705.4473,2622.2074),      # into pin 6
  (2705.4473,2622.2074),(2695.4474,2622.2074),
  (2695.4474,2622.2074),(2675.4474,2642.2073),
  (2675.4474,2642.2073),(2675.4474,2652.2073),
  (2675.4474,2652.2073),(2696.6285,2673.3884),
  (2696.6285,2673.3884),(2705.4473,2673.3884),      # into pin 8
]
path=[VP,J]+[p for p in weave]
# validate every segment before drawing anything
bad=[]
for a,b in zip(path,path[1:]):
    if not seg_clear(a[0],a[1],b[0],b[1],w=10,gap=6):
        bad.append((a,b))
print('blocked segments:',bad)
if bad:
    raise SystemExit('weave blocked by current obstacles; abort to avoid damage')

for a,b in zip(path,path[1:]):
    e.create_track(a[0],a[1],b[0],b[1],NET,10,1)

# also leg J->pad2 corner to tie branch into existing stub properly
leg=(J,(2775.3448,2647.7979))
if seg_clear(*leg[0],*leg[1],w=10):
    e.create_track(leg[0][0],leg[0][1],leg[1][0],leg[1][1],NET,10,1)
else:
    print('skip J->pad2 leg (blocked)')

print('pour-rebuild'); e._ok(e._run('pcb','pour-rebuild'))
e.reload()

f=e.check(); errs=[x for x in f if x.get('level')=='ERROR']
print('heur errors:',[(x['type'],x.get('at',{}).get('x'),x.get('at',{}).get('y')) for x in errs])

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
print('NoConn:',ncs if ncs else 'NONE ✔')
