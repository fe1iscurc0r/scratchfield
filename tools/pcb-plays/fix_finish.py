import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')
e.reload()

# helpers
allc=[{'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
       'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth'],'layer':t['layer']} for t in e.tracks()]

def pt_clear_all(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def pt_clear_top(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net or t['layer']!=1: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def seg_clear(fn, ax,ay,bx,by,w,gap,net):
    n=max(4,int(math.hypot(bx-ax,by-ay)//3)+1)
    for i in range(n+1):
        px=ax+(bx-ax)*i/n; py=ay+(by-ay)*i/n
        if not fn(px,py,w/2+.01,gap,net): return False
    return True

# collect 3V3 main tree endpoints for U3
net3='3V3'
main_verts=[('via',v['x'],v['y']) for v in e.vias() if v['net']==net3]
for t in e.tracks(net3):
    main_verts+=[('e',t['startX'],t['startY']),( 'e',t['endX'],t['endY'])]

def nearest_main(px,py,net,exclude_self=None,limit=250):
    best=None
    for kind,x,y in main_verts:
        if kind=='e' and abs(x-px)<1 and abs(y-py)<1: continue
        d=math.hypot(x-px,y-py)
        if d>limit or d<1: continue
        if best is None or d<best[0]: best=(d,x,y)
    return best

# ---------- U3_6 / U3_8 direct top-layer connection ----------
pads=[('U3','6',2705.5,2622.2074,net3),('U3','8',2705.5,2673.398,net3),
      ('R4','2',None,None,'LED_CHRG_A'),('R5','2',None,None,'LED_STDBY_A')]

# get R4_2/R5_2 coords from dump
dmp=e.dump()
for c in dmp['components']:
    for p in c['pads']:
        for i,(des,pn,_,_,nt) in enumerate(pads):
            if c['designator']==des and p['padNumber']==pn:
                pads[i]=(des,pn,p['x'],p['y'],nt)

print('targets:',[(des,pn,round(x,1),round(y,1),nt) for des,pn,x,y,nt in pads])

def try_connect_top(des,pn,px,py,net):
    tgt=nearest_main(px,py,net)
    if not tgt: return False
    d,tx,ty=tgt
    if d<4:
        # already touching
        return True
    # verify top trace
    ok=seg_clear(pt_clear_top, px,py,tx,ty, 6, 6, net)
    if ok:
        e.create_track(px,py,tx,ty,net,6,1)
        print(f' {des}.{pn}: direct top -> ({round(tx)},{round(ty)})')
        return True
    return False

def try_dogbone(des,pn,px,py,net, max_dist=70, max_target=220):
    # search via spot around pad with all-layer clearance; if found, link to nearest net node
    for dist in range(24, max_dist+1, 6):
        for ang in range(0,360,15):
            ax=px+dist*math.cos(math.radians(ang)); ay=py+dist*math.sin(math.radians(ang))
            if not pt_clear_all(ax,ay,12,6,net): continue
            if not seg_clear(pt_clear_top, px,py,ax,ay,6,6,net): continue
            # find nearest same-net node within max_target
            best=None
            for kind,x,y in main_verts:
                if x==ax and y==ay: continue
                d=math.hypot(x-ax,y-ay)
                if d>max_target: continue
                # route from via to target on L15 (inner) - check all layers
                s=max(4,int(d//3)+1)
                ok=True
                for i in range(s+1):
                    mx=ax+(x-ax)*i/s; my=ay+(y-ay)*i/s
                    if not pt_clear_all(mx,my,5,6,net): ok=False;break
                if ok and (best is None or d<best[0]): best=(d,x,y)
            if best:
                d,tx,ty=best
                e.create_via(ax,ay,net)
                e.create_track(px,py,ax,ay,net,6,1)
                e.create_track(ax,ay,tx,ty,net,10,15)
                print(f' {des}.{pn}: dogbone via@({round(ax)},{round(ay)}) -> ({round(tx)},{round(ty)})')
                return True
    return False

for des,pn,px,py,net in pads:
    if px is None: continue
    print(f'Trying {des}.{pn} ...')
    if try_connect_top(des,pn,px,py,net): continue
    print('  direct blocked, trying dogbone')
    if try_dogbone(des,pn,px,py,net): continue
    print('  !! failed')

# ---------- generic stitcher for remaining orphan fragments ----------
# import logic inline
TOL=8.0
tracks=[{'x1':t['startX'],'y1':t['startY'],'x2':t['endX'],'y2':t['endY']} for t in e.tracks(net3)]
vias=[{'x':v['x'],'y':v['y']} for v in e.vias() if v['net']==net3]
parent={}
def find(a):
    parent.setdefault(a,a)
    while parent[a]!=a: parent[a]=parent[parent[a]]; a=parent[a]
    return a
def uni(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[ra]=rb
for i,t in enumerate(tracks):
    ka=('e',i,'a'); kb=('e',i,'b'); find(ka); find(kb); uni(ka,kb)
for j,v in enumerate(vias):
    kk=('v',j); find(kk)
    for i,t in enumerate(tracks):
        for k,p in ((('e',i,'a'),(t['x1'],t['y1'])),(('e',i,'b'),(t['x2'],t['y2']))):
            if abs(p[0]-v['x'])<=TOL and abs(p[1]-v['y'])<=TOL: uni(k,kk)
pads=[]
for c in dmp['components']:
    for p in c['pads']:
        if p.get('net')==net3:
            kp=('p',c['designator'],p['padNumber']); find(kp)
            pads.append((kp,(p['x'],p['y'])))
            for i,t in enumerate(tracks):
                for kk,cx,cy in ((('e',i,'a'),(t['x1'],t['y1'])),(('e',i,'b'),(t['x2'],t['y2']))):
                    if abs(cx-p['x'])<=TOL and abs(cy-p['y'])<=TOL: uni(kp,kk)
            for j,v in enumerate(vias):
                if abs(v['x']-p['x'])<=TOL and abs(v['y']-p['y'])<=TOL: uni(kp,('v',j))
padroots={find(kp) for kp,_ in pads}

verts=[]
for i,t in enumerate(tracks):
    verts+=[(('e',i,'a'),t['x1'],t['y1']),(('e',i,'b'),t['x2'],t['y2'])]
for j,v in enumerate(vias):
    verts+=[(('v',j),v['x'],v['y'])]

def pt_clear2(px,py,rad,gap):
    for t in allc:
        if t['net']==net3: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

for _ in range(8):
    comps={}
    for k,x,y in verts:
        r=find(k); comps.setdefault(r,[x,y])
    roots=list(comps.keys())
    if len(roots)<=1: break
    proots={r for r in roots if r in padroots}
    others=[r for r in roots if r not in padroots]
    if not others: others=roots
    # find nearest pair across groups
    best=None
    for rr in others:
        for r2 in roots:
            if r2==rr: continue
            d=math.hypot(comps[rr][0]-comps[r2][0],comps[rr][1]-comps[r2][1])
            if d>60: continue
            if best is None or d<best[0]: best=(d,rr,r2,comps[rr],comps[r2])
    if not best: break
    d,rr,r2,op,pp=best
    if d>60: break
    # verify
    n=max(4,int(d//3)+1); ok=True
    for i in range(n+1):
        px=op[0]+(pp[0]-op[0])*i/n; py=op[1]+(pp[1]-op[1])*i/n
        if not pt_clear2(px,py,3,6): ok=False;break
    if not ok: continue
    lay=1 if d<15 else 15
    e.create_track(op[0],op[1],pp[0],pp[1],net3,6,lay)
    uni(rr,r2)

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

print('DRC leaf:',len(leaves),dict(Counter(l.get('errorType') for l in leaves)))
ncs=sorted({l.get('obj1Suffix') for l in leaves if l.get('errorType')=='No Connection'})
print('NoConn:', ncs if ncs else 'NONE ✔')
