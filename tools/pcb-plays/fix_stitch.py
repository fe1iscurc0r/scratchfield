import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')
NET='3V3'
TOL=8.0

tracks=[{'pid':t['primitiveId'],'x1':t['startX'],'y1':t['startY'],
         'x2':t['endX'],'y2':t['endY'],'layer':t['layer']} for t in e.tracks(NET)]
vias=[{'pid':v['primitiveId'],'x':v['x'],'y':v['y']} for v in e.vias(NET)]

parent={}
def find(a):
    parent.setdefault(a,a)
    while parent[a]!=a:
        parent[a]=parent[parent[a]]; a=parent[a]
    return a
def uni(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[ra]=rb

for i,t in enumerate(tracks):
    ka=('e',i,'a'); kb=('e',i,'b')
    find(ka); find(kb); uni(ka,kb)

def join_via(pt, k):
    for j,v in enumerate(vias):
        kk=('v',j); find(kk)
        if abs(v['x']-pt[0])<=TOL and abs(v['y']-pt[1])<=TOL:
            uni(k,kk)

for i,t in enumerate(tracks):
    for k,p in ((('e',i,'a'),(t['x1'],t['y1'])),
                (('e',i,'b'),(t['x2'],t['y2']))):
        join_via(p,k)

pads=[]
dmp=e.dump()
for c in dmp['components']:
    for p in c['pads']:
        if p.get('net')==NET:
            kp=('p',c['designator'],p['padNumber'])
            find(kp)
            pads.append((kp,(p['x'],p['y'])))
            for i,t in enumerate(tracks):
                for kk,(cx,cy) in ((('e',i,'a'),(t['x1'],t['y1'])),
                                 (('e',i,'b'),(t['x2'],t['y2']))):
                    if abs(cx-p['x'])<=TOL and abs(cy-p['y'])<=TOL:
                        uni(kp,kk)
            for j,v in enumerate(vias):
                if abs(v['x']-p['x'])<=TOL and abs(v['y']-p['y'])<=TOL:
                    uni(kp,('v',j))

padroots={find(t[0]) for t in pads}
print('components:',len({find(k) for k in list(parent)}))
print('pad-covered roots:',len(padroots))

allc=[]
for t in e.tracks():
    allc.append({'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
                 'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth']})
def pt_clear(px,py,rad,gap):
    for t in allc:
        if t.get('net')==NET:
            continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap:
            return False
    return True

verts=[]
for i,t in enumerate(tracks):
    verts += [(('e',i,'a'),t['x1'],t['y1']), (('e',i,'b'),t['x2'],t['y2'])]
for j,v in enumerate(vias):
    verts += [(('v',j),v['x'],v['y'])]

rounds=0
done=False
while not done:
    comps={}
    for k,x,y in verts:
        r=find(k)
        comps.setdefault(r,[x,y])
    roots=list(comps.keys())
    others=[r for r in roots if r not in padroots]
    targets=[r for r in roots if r in padroots]
    if len(roots)<=1:
        print('single component reached'); break
    # priority: orphan -> nearest any comp
    best=None
    for rr in others:
        op=comps[rr]
        for r2 in roots:
            if r2==rr: continue
            pp=comps[r2]
            d=math.hypot(op[0]-pp[0],op[1]-pp[1])
            prio=0 if r2 in padroots else 40
            score=d+prio
            if best is None or score<best[0]:
                best=(score,d,rr,r2,op,pp)
    if best is None:
        # multiple pad islands, connect two nearest comps generally
        cand=[]
        for i,r1 in enumerate(roots):
            for r2 in roots[i+1:]:
                d=math.hypot(comps[r1][0]-comps[r2][0],comps[r1][1]-comps[r2][1])
                cand.append((d,r1,r2))
        cand.sort()
        if not cand or cand[0][0]>60:
            print('no candidates under 60mil; manual needed'); done=True; break
        d,rr,r2=cand[0]; op,pp=comps[rr],comps[r2]
        best=(d,d,rr,r2,op,pp)

    score,d,rr,r2,op,pp=best
    print(f'join {str(rr)[:8]} -> {str(r2)[:8]} gap={round(d,1)} at {tuple(round(v) for v in op)}->{tuple(round(v) for v in pp)}')
    if d>60:
        print('gap too large; manual'); done=True; break
    w=6 if d<15 else 10
    lay=1 if w==6 else 15
    n=max(3,int(d//3)+1); midok=True
    for i in range(n+1):
        px=op[0]+(pp[0]-op[0])*i/n; py=op[1]+(pp[1]-op[1])*i/n
        if not pt_clear(px,py,w/2+0.01,6): midok=False; break
    if not midok or not pt_clear(op[0],op[1],w/2+.01,6) or not pt_clear(pp[0],pp[1],w/2+.01,6):
        print('   blocked; abort this round, manual review')
        done=True; break
    e.create_track(op[0],op[1],pp[0],pp[1],NET,w,lay)
    uni(rr,r2); rounds+=1
    if rounds>8:
        break

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
        elif 'explanation' in n:
            leaves.append(n['explanation'].get('errData',{}))
for g in resp['violations']: walk(g)
from collections import Counter

print('DRC leaf:',len(leaves),dict(Counter(l.get('errorType') for l in leaves)))
ncs=sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'})
print('NoConn:', ncs if ncs else 'NONE ✔')
