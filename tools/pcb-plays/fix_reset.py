import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')

print('== reload =='); e.reload()
for net in ['3V3','LED_CHRG_A','LED_STDBY_A']:
    print(f'rip-up {net}'); e._ok(e._run('pcb','rip-up','--net',net)); e.reload()

print('== reauthorize =='); e.reauthorize()
print('== route-short ==')
e._ok(e._run('pcb','route-short','--route-power','--force-unsafe','reroute 3V3/LED nets'))
e.reload()

# gather current same-net nodes for each net
nodes={}
for net in ['3V3','LED_CHRG_A','LED_STDBY_A']:
    lst=[]
    for t in e.tracks(net):
        lst += [(t['startX'],t['startY']),(t['endX'],t['endY'])]
    for v in e.vias(net):
        lst.append((v['x'],v['y']))
    nodes[net]=lst

allc=[{'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
       'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth'],'layer':t['layer']} for t in e.tracks()]

def pt_all(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def pt_top(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net or t['layer']!=1: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def seg(fn,ax,ay,bx,by,w,gap,net):
    n=max(4,int(math.hypot(bx-ax,by-ay)//3)+1)
    for i in range(n+1):
        px=ax+(bx-ax)*i/n; py=ay+(by-ay)*i/n
        if not fn(px,py,w/2+.01,gap,net): return False
    return True

def nearest_node(px,py,net,limit=250):
    best=None
    for x,y in nodes[net]:
        d=math.hypot(x-px,y-py)
        if 1<d<limit and (best is None or d<best[0]): best=(d,x,y)
    return best

# pads to heal
dmp=e.dump()
targets=[]
for c in dmp['components']:
    for p in c['pads']:
        net=p.get('net')
        if net in ['3V3','LED_CHRG_A','LED_STDBY_A']:
            targets.append((c['designator'],p['padNumber'],net,p['x'],p['y']))

print('targets:',[(d,n,net) for d,n,net,x,y in targets])

def dogbone(des,pn,px,py,net):
    best=nearest_node(px,py,net)
    if not best:
        print(f'{des}.{pn}: no net node found'); return False
    d,tx,ty=best
    print(f'{des}.{pn} nearest node @ {(round(tx),round(ty))} gap {round(d,1)}')
    # first try direct top trace
    if seg(pt_top,px,py,tx,ty,6,6,net):
        e.create_track(px,py,tx,ty,net,6,1)
        print('  -> direct top OK'); return True
    # try offset via (dog-bone)
    for dist in range(20,70,5):
        for ang in range(0,360,20):
            ax=px+dist*math.cos(math.radians(ang)); ay=py+dist*math.sin(math.radians(ang))
            if not pt_all(ax,ay,12,6,net): continue
            if not seg(pt_top,px,py,ax,ay,6,6,net): continue
            # check via can reach node on inner layer
            ok=True; s=max(4,int(d//3)+1)
            for i in range(s+1):
                mx=ax+(tx-ax)*i/s; my=ay+(ty-ay)*i/s
                if not pt_all(mx,my,5,6,net): ok=False; break
            if ok:
                e.create_via(ax,ay,net)
                e.create_track(px,py,ax,ay,net,6,1)
                e.create_track(ax,ay,tx,ty,net,10,15)
                print(f'  -> dogbone via @({round(ax)},{round(ay)}) OK'); return True
    print('  -> FAILED'); return False

for des,pn,net,px,py in targets:
    dogbone(des,pn,px,py,net)

print('== pour-rebuild =='); e._ok(e._run('pcb','pour-rebuild'))
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
