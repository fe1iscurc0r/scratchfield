import math
import sys

sys.path.insert(0,'scripts/easyeda')
from clearance_fix import EasyEDAPCB

e=EasyEDAPCB('LoRaCanary-底板-v0.6')
e.reload(); e.reauthorize()
dmp=e.dump()

# collect SMD pad rects (layer 1, size <= 60mil)
def pad_rect(p):
    w,h=p['width'],p['height']
    if int(p.get('rotation',0))%180==90: w,h=h,w
    return (p['x']-w/2,p['y']-h/2,p['x']+w/2,p['y']+h/2)

pads=[]
for c in dmp['components']:
    for p in c['pads']:
        if p.get('layer')==1:
            r=pad_rect(p)
            pads.append((c['designator'],p['padNumber'],p.get('net'),r,p))

# find vias inside pads
vias=[]
for v in e.vias():
    x,y=v['x'],v['y']
    for des,num,net,r,p in pads:
        if r[0]<=x<=r[2] and r[1]<=y<=r[3]:
            vias.append((v,des,num,net,r))
            break

print('vias inside SMD pads:',len(vias))
for v,des,num,net,r in vias:
    print(' ',des,num,net,v['primitiveId'],v['x'],v['y'])

# clearance helpers using current board state
allc=[{'net':t.get('net'),'x1':t['startX'],'y1':t['startY'],
       'x2':t['endX'],'y2':t['endY'],'w':t['lineWidth'],'layer':t['layer']} for t in e.tracks()]

def pt_clear(px,py,rad,gap,net):
    for t in allc:
        if t['net']==net: continue
        dx=t['x2']-t['x1']; dy=t['y2']-t['y1']
        L2=dx*dx+dy*dy
        tt=max(0,min(1,((px-t['x1'])*dx+(py-t['y1'])*dy)/L2)) if L2 else 0
        qx=t['x1']+tt*dx; qy=t['y1']+tt*dy
        if math.hypot(px-qx,py-qy)-rad-t['w']/2 < gap: return False
    return True

def seg_clear(ax,ay,bx,by,w,gap,net):
    n=max(4,int(math.hypot(bx-ax,by-ay)//3)+1)
    for i in range(n+1):
        px=ax+(bx-ax)*i/n; py=ay+(by-ay)*i/n
        if not pt_clear(px,py,w/2+.01,gap,net): return False
    return True

moved=0
failed=[]
for v,des,num,net,r in vias:
    vx,vy=v['x'],v['y']
    padcx=(r[0]+r[2])/2; padcy=(r[1]+r[3])/2
    # search outward in 8 directions for a spot 25-50mil outside pad, plus stub clearance
    candidates=[]
    for dist in range(25,60,5):
        for ang in range(0,360,45):
            ax=padcx+dist*math.cos(math.radians(ang))
            ay=padcy+dist*math.sin(math.radians(ang))
            # ensure outside pad
            if r[0]<=ax<=r[2] and r[1]<=ay<=r[3]: continue
            # check via spot and stub from pad edge to new via
            if not pt_clear(ax,ay,12,6,net): continue
            if not seg_clear(vx,vy,ax,ay,6,6,net): continue
            candidates.append((dist,ax,ay,ang))
    if not candidates:
        failed.append((des,num,v['primitiveId']))
        continue
    # prefer direction roughly perpendicular outward from pad center to via
    best=None
    for dist,ax,ay,ang in candidates:
        # score: smaller distance, and angle aligned with vector from pad center to old via
        ang0=math.degrees(math.atan2(vy-padcy,vx-padcx))
        da=min(abs(ang-ang0),360-abs(ang-ang0))
        score=dist+da*0.5
        if best is None or score<best[0]: best=(score,dist,ax,ay)
    _,_,nx,ny=best
    # delete old via, create new via + stub
    e._ok(e._run('pcb','via-delete','--ids',v['primitiveId']))
    e.create_via(nx,ny,net)
    e.create_track(vx,vy,nx,ny,net,6,1)
    moved+=1
    print(f'moved {des}.{num} via to ({round(nx)},{round(ny)})')

print('moved',moved,'failed',len(failed))
if failed: print('failed:',failed)

print('pour-rebuild')
e._ok(e._run('pcb','pour-rebuild'))
e.reload()
f=e.check()
errs=[x for x in f if x.get('level')=='ERROR']
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
print('NoConn:', ncs if ncs else 'NONE ')
